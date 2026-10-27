# 단일 프레임 디코딩 단위 테스트 (TC-002).
from __future__ import annotations

import numpy as np
import pytest
from pydicom.data import get_testdata_file

from dicom_tag_explorer.core.dicom_file import DicomFile
from dicom_tag_explorer.core.image_decode import (
    NO_DECODER, NO_IMAGE, OK, decode_first_frame, msg_cannot_display,
)


def decode(path):
    f = DicomFile(path).load()
    return decode_first_frame(f.path, f.transfer_syntax, f.summary.has_pixel_data)


@pytest.mark.parametrize("name", ["MR_small_implicit.dcm", "CT_small.dcm", "image_dfl.dcm",
                                  "MR_small_bigendian.dcm", "MR_small_RLE.dcm", "JPEG2000.dcm"])
def test_tc002_decodes_to_8bit(name):
    r = decode(get_testdata_file(name))
    assert r.status == OK, r.detail
    assert r.array.dtype == np.uint8 and r.array.ndim in (2, 3)
    assert r.array.max() > r.array.min()


def test_tc002_jpeg_ls_no_decoder():
    r = decode(get_testdata_file("MR_small_jpeg_ls_lossless.dcm"))
    assert r.status == NO_DECODER
    assert "JPEG-LS" in msg_cannot_display("1.2.840.10008.1.2.4.80")


def test_color_rgb():
    r = decode(get_testdata_file("SC_rgb_jpeg_dcmtk.dcm"))
    assert r.status == OK and r.array.shape[-1] == 3


def test_no_pixel_data():
    r = decode(get_testdata_file("DICOMDIR"))
    assert r.status == NO_IMAGE


def test_tc002_sample_label(s_v_label):
    r = decode(s_v_label)
    assert r.status == OK, r.detail
    assert r.array.dtype == np.uint8 and r.array.shape[-1] == 3


def test_tc051_monochrome1_inverted(tmp_path):
    from dicom_factory import mono_file
    r1 = decode(mono_file(tmp_path / "m1.dcm", "MONOCHROME1"))
    r2 = decode(mono_file(tmp_path / "m2.dcm", "MONOCHROME2"))
    assert r1.status == OK and r2.status == OK
    assert r1.array[0, 0] == 255 and r1.array[1, 1] == 0  # 가장 작은 값 → 흰색
    assert r2.array[0, 0] == 0 and r2.array[1, 1] == 255
