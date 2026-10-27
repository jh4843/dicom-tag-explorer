# core 고정 메시지와 번역 추출 목록(ui/core_messages.py)이 어긋나지 않는지 확인한다.
from __future__ import annotations

import inspect
import re

from dicom_tag_explorer.core import classify, dicomdir, image_decode, indexer, notices, scan, search, wsi
from dicom_tag_explorer.ui.core_messages import MESSAGES


def test_fixed_core_messages_are_listed():
    expected = {indexer.MSG_NOT_DICOM, scan.MSG_NOT_FOUND, "Cancelled", image_decode.MSG_NO_IMAGE,
                image_decode.MSG_CANNOT_DISPLAY, notices.MSG_DEV, *search.HINTS.values()}
    expected |= set(re.findall(r'ParseError\([a-z]+, "([^"]+)"\)', inspect.getsource(indexer)))
    for mod, lit in ((classify, "Open failed"), (dicomdir, "File not found"), (wsi, "No VOLUME level")):
        assert f'"{lit}"' in inspect.getsource(mod)
        expected.add(lit)
    assert expected <= set(MESSAGES), expected - set(MESSAGES)
