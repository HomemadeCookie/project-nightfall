"""HTTP with a polite default: identifying User-Agent, retries, per-host spacing."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

import httpx

USER_AGENT = "nightfall/0.1 (+https://github.com/HomemadeCookie/project-nightfall; open data research)"
RETRY_STATUS = {429, 500, 502, 503, 504}


class Http:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 45.0,
        retries: int = 3,
        min_interval: dict[str, float] | None = None,
        sleep=time.sleep,
        clock=time.monotonic,
    ):
        self._client = httpx.Client(
            transport=transport,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        self._retries = retries
        self._min_interval = min_interval or {}
        self._last: dict[str, float] = {}
        self._sleep = sleep
        self._clock = clock

    def _space(self, host: str) -> None:
        gap = self._min_interval.get(host, 0.0)
        if gap <= 0:
            return
        wait = self._last.get(host, float("-inf")) + gap - self._clock()
        if wait > 0:
            self._sleep(wait)
        self._last[host] = self._clock()

    @staticmethod
    def _backoff(attempt: int, resp: httpx.Response | None) -> float:
        """Seconds to wait before retrying. Rate-limited calls wait much longer."""
        if resp is not None and resp.status_code == 429:
            retry_after = resp.headers.get("retry-after", "")
            if retry_after.isdigit():
                return min(float(retry_after), 60.0)
            return min(8.0 * (attempt + 1), 60.0)
        return min(2.0**attempt, 20.0)

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        host = urlparse(url).netloc
        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            self._space(host)
            try:
                resp = self._client.get(url, **kwargs)
            except httpx.TransportError as exc:
                last_exc = exc
            else:
                if resp.status_code not in RETRY_STATUS:
                    resp.raise_for_status()
                    return resp
                last_exc = httpx.HTTPStatusError(
                    f"{resp.status_code} from {host}", request=resp.request, response=resp
                )
            if attempt < self._retries:
                self._sleep(
                    self._backoff(attempt, resp if isinstance(last_exc, httpx.HTTPStatusError) else None)
                )
        assert last_exc is not None
        raise last_exc

    def get_json(self, url: str, **kwargs: Any) -> Any:
        return self.get(url, **kwargs).json()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Http:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
