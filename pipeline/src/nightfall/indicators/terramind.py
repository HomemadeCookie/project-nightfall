"""TerraMind flood head. Weights are optional; the default pipeline does not download them.

Input layout matches TerraMind-base-Flood: four dates, Sentinel-2 (12 bands),
Sentinel-1 RTC (2 bands), and a DEM repeated across the four dates. The returned
mask uses class 2 for flood water.
"""

from __future__ import annotations

import numpy as np

TIME_STEPS = 4
BANDS = {"S2L2A": 12, "S1RTC": 2, "DEM": 1}


class TerraMindUnavailable(RuntimeError):
    pass


def _as_model(array: np.ndarray, bands: int, name: str) -> np.ndarray:
    """(time, bands, height, width) -> (1, bands, time, height, width)."""
    if array.ndim != 4:
        raise ValueError(f"{name} must have shape (time, bands, height, width)")
    time, got, height, width = array.shape
    if time != TIME_STEPS or got != bands:
        raise ValueError(f"{name} must be ({TIME_STEPS}, {bands}, H, W), got {array.shape}")
    if height < 1 or width < 1:
        raise ValueError(f"{name} is empty")
    return np.transpose(array, (1, 0, 2, 3))[None, ...]


def build_input(s2: np.ndarray, s1: np.ndarray, dem: np.ndarray) -> dict[str, np.ndarray]:
    """Stack four dates. ``dem`` is (H, W) or (1, H, W) and is repeated across time.

    A missing date is not filled in here. Pass four real dates, or do not call this.
    """
    if dem.ndim == 2:
        dem_t = np.stack([dem] * TIME_STEPS)[:, None, :, :]
    elif dem.ndim == 3 and dem.shape[0] == 1:
        dem_t = np.stack([dem[0]] * TIME_STEPS)[:, None, :, :]
    elif dem.ndim == 4:
        dem_t = dem
    else:
        raise ValueError("dem must be (H, W), (1, H, W), or (4, 1, H, W)")
    return {
        "S2L2A": _as_model(s2, BANDS["S2L2A"], "s2"),
        "S1RTC": _as_model(s1, BANDS["S1RTC"], "s1"),
        "DEM": _as_model(dem_t, BANDS["DEM"], "dem"),
    }


def predict(stack: dict[str, np.ndarray], config: str, checkpoint: str) -> np.ndarray:
    """Run the flood checkpoint. Returns a uint8 (H, W) mask. Raises if torch is absent."""
    for name in BANDS:
        if name not in stack:
            raise ValueError(f"stack is missing {name}")
    try:
        import torch
        from terratorch.cli_tools import LightningInferenceModel
    except ImportError as exc:
        raise TerraMindUnavailable(
            "TerraMind weights need the optional flood extra (torch and terratorch). "
            "The rest of the pipeline runs without them."
        ) from exc
    task = LightningInferenceModel.from_config(config, checkpoint)
    model = task.model.model
    model.eval()
    tensors = {name: torch.as_tensor(stack[name]) for name in BANDS}
    with torch.no_grad():
        pred = model(tensors).output
    mask = pred.argmax(dim=1).squeeze(0).detach().cpu().numpy().astype(np.uint8)
    if mask.ndim != 2:
        raise RuntimeError(f"TerraMind returned shape {mask.shape}, expected (H, W)")
    return mask
