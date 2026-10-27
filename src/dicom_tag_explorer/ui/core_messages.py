# core(Qt 비의존)의 고정 영어 메시지를 lupdate가 "core" 문맥으로 추출하도록 나열한다.
"""core는 Qt에 의존하지 않으므로 tr()을 쓸 수 없다. UI는 표시할 때 common.tr_core()로 번역한다.
동적 값이 붙는 메시지(예: "Cannot open file: …")는 고정 부분이 달라 번역되지 않고 영어로 표시된다.
core 상수가 바뀌면 tests/core/test_core_messages.py가 실패한다.
"""
from PySide6.QtCore import QT_TRANSLATE_NOOP

MESSAGES = [
    QT_TRANSLATE_NOOP("core", "Not a DICOM file (no 'DICM' at offset 128)"),
    QT_TRANSLATE_NOOP("core", "Path not found"),
    QT_TRANSLATE_NOOP("core", "Cancelled"),
    QT_TRANSLATE_NOOP("core", "Open failed"),
    QT_TRANSLATE_NOOP("core", "File not found"),
    QT_TRANSLATE_NOOP("core", "This file has no image to display."),
    QT_TRANSLATE_NOOP("core", "Cannot display the image. (Transfer Syntax: {0})"),
    QT_TRANSLATE_NOOP("core", "The notices file is not available when running from source. Check it in the build output."),
    QT_TRANSLATE_NOOP("core", "Element header runs past end of file"),
    QT_TRANSLATE_NOOP("core", "Fragment header runs past end of file"),
    QT_TRANSLATE_NOOP("core", "Fragment length runs past end of file"),
    QT_TRANSLATE_NOOP("core", "Invalid Item in encapsulated value"),
    QT_TRANSLATE_NOOP("core", "Item length exceeds the enclosing range"),
    QT_TRANSLATE_NOOP("core", "Missing Item Delimitation"),
    QT_TRANSLATE_NOOP("core", "Missing Sequence Delimitation"),
    QT_TRANSLATE_NOOP("core", "Value length exceeds the enclosing range"),
    QT_TRANSLATE_NOOP("core", "Format: 0010,0010 / 00100010 / (0010,0010). A prefix is allowed (e.g. 0010)"),
    QT_TRANSLATE_NOOP("core", "Format: two-letter VR (e.g. PN)"),
    QT_TRANSLATE_NOOP("core", "Format: decimal number"),
    QT_TRANSLATE_NOOP("core", "Format: hex (0x optional)"),
    QT_TRANSLATE_NOOP("core", "No VOLUME level"),
]
