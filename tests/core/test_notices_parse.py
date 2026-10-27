# 정보 창용 고지 파일 파싱 테스트 (SPEC-029).
from __future__ import annotations

from dicom_tag_explorer.core import notices


def test_parse_sections():
    text = "HEAD\nline\n\n===== pydicom 3.0.1 (MIT) =====\n\nMIT text\n\n===== PySide6-Essentials / Qt 6.11.0 (LGPL-3.0-only) =====\nLGPL\n"
    head, secs = notices.parse(text)
    assert head == "HEAD\nline"
    assert [(s.name, s.version, s.license) for s in secs] == [
        ("pydicom", "3.0.1", "MIT"), ("PySide6-Essentials / Qt", "6.11.0", "LGPL-3.0-only")]
    assert secs[0].text == "MIT text"


def test_dev_run_has_no_notices():
    assert notices.notices_path() is None
    assert notices.load() is None
