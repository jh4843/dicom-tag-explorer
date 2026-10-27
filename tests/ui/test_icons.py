# 아이콘 매니페스트·SVG·로더 검사 (TC-044).
from __future__ import annotations

import re
from pathlib import Path

import pytest
from PySide6.QtCore import QByteArray
from PySide6.QtSvg import QSvgRenderer

from dicom_tag_explorer.ui import icons, theme

SRC = Path(__file__).resolve().parents[2] / "src"


def test_manifest_has_52_files():
    m = icons.manifest()
    assert len(m["icons"]) == 52
    for name, e in m["icons"].items():
        assert (icons.icons_dir() / e["file"]).is_file(), name


@pytest.mark.parametrize("th", ["dark", "light"])
def test_all_svgs_valid(th):
    for name in icons.names():
        r = QSvgRenderer(QByteArray(icons.svg_text(name, th).encode()))
        assert r.isValid(), (th, name)


def test_light_recolor_removes_dark_colors():
    src_colors = [c.lower() for c in icons.manifest()["recolor"]["light"]]
    for name in icons.names():
        svg = icons.svg_text(name, "light").lower()
        for c in src_colors:
            assert c not in svg, (name, c)


@pytest.mark.parametrize("th", ["dark", "light"])
def test_icon_not_null_in_both_themes(qapp, th):
    theme.apply(qapp, th)
    for name in icons.names():
        assert not icons.icon(name).isNull(), name
    assert not icons.icon("window-close", "neutral-0").isNull()
    assert not icons.app_icon().isNull()
    theme.apply(qapp, "dark")


def test_unknown_name_raises(qapp):
    with pytest.raises(KeyError):
        icons.icon("no-such-icon")


def test_source_icon_literals_are_in_manifest():
    pat = re.compile(r"""\bicon\(\s*["']([a-z0-9-]+)["']|\bicon\s*=\s*["']([a-z0-9-]+)["']""")
    found = set()
    for p in SRC.rglob("*.py"):
        for m in pat.finditer(p.read_text(encoding="utf-8")):
            found.add(m.group(1) or m.group(2))
    assert found, "아이콘 리터럴을 찾지 못했다"
    assert found <= set(icons.names()), found - set(icons.names())
