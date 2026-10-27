# 단일 Instance의 첫 프레임을 승인된 디코더(pydicom native/RLE, Pillow)로 풀어 8bit 배열로 만든다.
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pydicom import dcmread
from pydicom.dataset import Dataset
from pydicom.pixels import apply_modality_lut, apply_voi_lut, pixel_array
from pydicom.uid import UID

# Spec 1.3에서 이미지 열이 O인 Transfer Syntax
SUPPORTED = {
    "1.2.840.10008.1.2",
    "1.2.840.10008.1.2.1",
    "1.2.840.10008.1.2.1.99",
    "1.2.840.10008.1.2.2",
    "1.2.840.10008.1.2.4.50",
    "1.2.840.10008.1.2.4.51",
    "1.2.840.10008.1.2.4.90",
    "1.2.840.10008.1.2.4.91",
    "1.2.840.10008.1.2.5",
}
DEFLATE = "1.2.840.10008.1.2.1.99"
OK, NO_IMAGE, NO_DECODER, FAILED = "ok", "no_image", "no_decoder", "failed"
MSG_NO_IMAGE = "This file has no image to display."
MSG_CANNOT_DISPLAY = "Cannot display the image. (Transfer Syntax: {0})"


def ts_name(uid: str) -> str:
    if not uid:
        return "(none)"
    u = UID(uid)
    return u.name if u.is_transfer_syntax else uid


def msg_cannot_display(uid: str) -> str:
    return MSG_CANNOT_DISPLAY.format(ts_name(uid))


@dataclass
class DecodeResult:
    status: str
    array: np.ndarray | None = None  # uint8, (H, W) 또는 (H, W, 3)
    detail: str = ""


def decode_first_frame(path: Path | str, transfer_syntax: str, has_pixel_data: bool = True) -> DecodeResult:
    if not has_pixel_data:
        return DecodeResult(NO_IMAGE, detail=MSG_NO_IMAGE)
    if transfer_syntax not in SUPPORTED:
        return DecodeResult(NO_DECODER, detail=f"No approved decoder ({transfer_syntax})")
    ds = Dataset()
    try:
        if transfer_syntax == DEFLATE:
            # 경로 기반 읽기는 Deflate 본문을 풀지 않으므로 Dataset으로 읽는다 (본문은 어차피 메모리에 풀린다)
            ds = dcmread(str(path))
            arr = pixel_array(ds, index=0)
        else:
            # 경로 기반 읽기는 첫 프레임만 읽어 대용량 파일 메모리를 제한한다
            arr = pixel_array(str(path), ds_out=ds, index=0)
    except Exception as e:
        return DecodeResult(FAILED, detail=f"{type(e).__name__}: {e}")
    try:
        return DecodeResult(OK, to_display(arr, ds))
    except Exception as e:
        return DecodeResult(FAILED, detail=f"{type(e).__name__}: {e}")


def to_display(arr: np.ndarray, ds: Dataset) -> np.ndarray:
    """SPEC-003: 흑백은 Modality LUT + 첫 VOI Window(없으면 최소·최대) → 8bit, MONOCHROME1은 반전. 컬러는 RGB 8bit."""
    spp = int(ds.get("SamplesPerPixel", 1) or 1)
    if spp == 1:
        a = apply_modality_lut(arr, ds).astype(np.float64)
        rng = None
        if "WindowCenter" in ds and "WindowWidth" in ds:
            a = apply_voi_lut(a, ds, index=0, prefer_lut=False).astype(np.float64)
            rng = _window_range(ds)
        elif ds.get("VOILUTSequence"):
            a = apply_voi_lut(a, ds, index=0).astype(np.float64)
            rng = (0.0, float(2 ** int(ds.VOILUTSequence[0].LUTDescriptor[2]) - 1))
        if rng is None or rng[1] <= rng[0]:
            rng = (float(a.min()), float(a.max()))
        out = _scale(a, *rng)
        if str(ds.get("PhotometricInterpretation", "")).strip() == "MONOCHROME1":
            out = 255 - out  # MONOCHROME1은 최소값이 흰색이다 (PS3.3 C.7.6.3.1.2)
        return out
    # 컬러: pydicom이 YBR → RGB로 변환해 준다 (as_rgb 기본값)
    if arr.ndim == 3 and arr.shape[-1] >= 3:
        arr = arr[..., :3]
    if arr.dtype == np.uint8:
        return np.ascontiguousarray(arr)
    bits = int(ds.get("BitsStored", 8) or 8)
    return _scale(arr.astype(np.float64), 0.0, float(2 ** bits - 1))


def _window_range(ds: Dataset) -> tuple[float, float]:
    bits = int(ds.BitsStored)
    if ds.get("ModalityLUTSequence"):
        lo, hi = 0.0, float(2 ** int(ds.ModalityLUTSequence[0].LUTDescriptor[2]) - 1)
    elif int(ds.get("PixelRepresentation", 0)) == 0:
        lo, hi = 0.0, float(2 ** bits - 1)
    else:
        lo, hi = float(-(2 ** (bits - 1))), float(2 ** (bits - 1) - 1)
    slope, inter = ds.get("RescaleSlope"), ds.get("RescaleIntercept")
    if slope is not None and inter is not None:
        lo, hi = lo * float(slope) + float(inter), hi * float(slope) + float(inter)
    return (min(lo, hi), max(lo, hi))


def _scale(a: np.ndarray, lo: float, hi: float) -> np.ndarray:
    if hi <= lo:
        return np.zeros(a.shape, dtype=np.uint8)
    out = (np.clip(a, lo, hi) - lo) * (255.0 / (hi - lo))
    return np.ascontiguousarray(out.round().astype(np.uint8))
