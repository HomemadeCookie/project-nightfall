"""DA Bantay Presyo: weekly average retail prices in NCR markets (PDF).

Only NCR is published at this granularity. We store the extracted text, not the PDF, so parser
fixes can be re-applied to history without re-downloading. The licence is UNCLEAR: the IP Code
(RA 8293 s.176) leaves government works uncopyrighted but requires the agency's prior approval to
exploit them for profit.
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterator
from datetime import datetime

import pdfplumber

from nightfall.core.envelope import Envelope
from nightfall.core.license import License
from nightfall.sources.base import Source
from nightfall.sources.registry import register

PAGE = "https://www.da.gov.ph/price-monitoring/"
_WEEKLY = re.compile(r"https://[^\"'\s]*/(?:Revised-)?Weekly-Average-Price[s]?-[^\"'\s]*\.pdf")


def weekly_links(html: str) -> list[str]:
    """Weekly-average PDF links on the listing page (revised editions included)."""
    return sorted(set(_WEEKLY.findall(html)))


def pdf_text(content: bytes) -> str:
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


class OcrUnavailable(RuntimeError):
    pass


def group_lines(boxes: list[tuple[float, float, float, str]]) -> list[str]:
    """Rebuild text lines from OCR boxes ``(y_centre, x_left, height, text)``.

    Boxes whose vertical centres are within half a line height are one line, ordered left to right.
    """
    if not boxes:
        return []
    boxes = sorted(boxes)
    tol = 0.5 * sorted(b[2] for b in boxes)[len(boxes) // 2]
    lines: list[list[tuple[float, str]]] = []
    cy = None
    for y, x, _h, txt in boxes:
        if cy is not None and abs(y - cy) <= tol:
            lines[-1].append((x, txt))
            cy = (cy + y) / 2
        else:
            lines.append([(x, txt)])
            cy = y
    return [" ".join(t for _, t in sorted(line)) for line in lines]


def ocr_text(content: bytes, dpi: int = 200) -> str:
    """OCR for scanned PDFs (about half of DA's weekly files have no text layer).

    Needs the optional ``ocr`` extra (RapidOCR, free and offline). Slow: ~50 s per file. At 200 dpi it matched the text layer exactly on every staple we track.
    """
    try:
        import numpy as np
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        raise OcrUnavailable("install the `ocr` extra: uv sync --extra ocr") from exc
    engine = RapidOCR()
    out: list[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            image = np.array(page.to_image(resolution=dpi).original.convert("RGB"))
            result, _ = engine(image)
            boxes = [
                (
                    sum(pt[1] for pt in box) / 4,
                    min(pt[0] for pt in box),
                    max(pt[1] for pt in box) - min(pt[1] for pt in box),
                    txt,
                )
                for box, txt, _score in (result or [])
            ]
            out.extend(group_lines(boxes))
    return "\n".join(out)


@register
class DaWeeklyPrices(Source):
    name = "da_prices"
    license = [License.UNCLEAR]
    cadence = "weekly"
    attribution = "Department of Agriculture - Bantay Presyo (DA-AMAS)"
    max_new_per_run = 400
    incremental = ("weekly_ncr", "url")

    def __init__(self, http, **kw):
        super().__init__(http, **kw)
        http._min_interval["www.da.gov.ph"] = 1.0

    def fetch(self, now: datetime) -> Iterator[Envelope]:
        html = self.http.get(PAGE).text
        todo = [u for u in weekly_links(html) if u not in self.known][-self.max_new_per_run :]
        for url in todo:
            content = self.http.get(url).content
            text, method = pdf_text(content), "text"
            if len(text.strip()) < 200:  # scanned image: no text layer
                try:
                    text, method = ocr_text(content), "ocr"
                except OcrUnavailable:
                    continue  # not stored, so a later run with OCR installed picks it up
            yield self.envelope("weekly_ncr", {"text": text, "method": method}, now=now, request={"url": url})
