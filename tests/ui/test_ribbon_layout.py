# 리본 배치 데이터(RIBBON_LAYOUT)와 명령 정적 정보(COMMANDS) 검사 (TC-048, TC-049 단축키 중복).
from __future__ import annotations

from collections import Counter

from PySide6.QtGui import QKeySequence

from dicom_tag_explorer.ui import icons
from dicom_tag_explorer.ui.actions import COMMANDS, RIBBON_LAYOUT


def all_cmds():
    return [(n, s) for _, groups in RIBBON_LAYOUT for _, cmds in groups for n, s in cmds]


def test_tabs_and_groups_order():
    assert [t for t, _ in RIBBON_LAYOUT] == ["File", "Edit", "View", "Help"]
    assert [[g for g, _ in groups] for _, groups in RIBBON_LAYOUT] == [
        ["Open", "Files", "App"], ["Copy", "Find", "Go To"], ["Explorer", "Image", "Layout"], ["Help"]]


def test_commands_unique_sizes_and_known():
    names = [n for n, _ in all_cmds()]
    assert len(names) == len(set(names))
    assert {s for _, s in all_cmds()} <= {"L", "S"}
    assert set(names) <= set(COMMANDS)


def test_command_icons_exist():
    for name, c in COMMANDS.items():
        if c.icon:
            assert c.icon in icons.names(), name


def test_shortcuts_do_not_overlap():
    keys = [QKeySequence(k).toString() for c in COMMANDS.values() for k in c.shortcuts]
    dup = [k for k, n in Counter(keys).items() if n > 1]
    assert dup == []
    for k in ("Ctrl+,", "Ctrl+F1", "F1"):
        assert QKeySequence(k).toString() in keys


def _ko_ribbon() -> dict[str, str]:
    import xml.etree.ElementTree as ET
    from pathlib import Path
    ts = Path(__file__).resolve().parents[2] / "src/dicom_tag_explorer/ui/resources/i18n/dicom_tag_explorer_ko.ts"
    for ctx in ET.parse(ts).getroot().iter("context"):
        if ctx.findtext("name") == "Ribbon":
            return {m.findtext("source"): m.findtext("translation") for m in ctx.iter("message")}
    return {}


def test_korean_names_match_ribbon_readme():
    """Ribbon README '탭별 명령'의 탭·그룹 순서와 한국어 번역이 같다 (TC-048)."""
    import re
    from pathlib import Path
    readme = (Path(__file__).resolve().parents[2] / "docs/design-system/components/Ribbon/README.md").read_text(
        encoding="utf-8")
    expected = []
    for line in readme.splitlines():
        m = re.match(r"\s+- (\S+): (.+)$", line)
        if m and m.group(1) in ("파일", "편집", "보기", "도움말"):
            groups = re.findall(r"(?:^|·\s*)([^()·,]+?)\(", m.group(2))
            expected.append((m.group(1), [g.strip() for g in groups]))
    ko = _ko_ribbon()
    actual = [(ko[t], [ko[g] for g, _ in groups]) for t, groups in RIBBON_LAYOUT]
    assert actual == expected
