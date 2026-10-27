# icons.json 기준으로 자체 제작 SVG 아이콘을 불러오고, 라이트 테마는 recolor.light로 색을 바꿔 렌더링한다.
from __future__ import annotations

import json
import re
import sys
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# 16px·32px 논리 크기를 100%~200% 배율에서 선명하게 쓰도록 여러 픽셀 크기로 렌더링한다
PIXEL_SIZES = (16, 20, 24, 32, 40, 48, 64)
_HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
_cache: dict[tuple, QIcon] = {}


def resources_dir() -> Path:
    """소스 실행은 패키지 폴더, PyInstaller 빌드는 _MEIPASS 아래 같은 상대 경로."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "dicom_tag_explorer" / "ui" / "resources"
    return Path(__file__).resolve().parent / "resources"


def icons_dir() -> Path:
    return resources_dir() / "icons"


@lru_cache(maxsize=1)
def manifest() -> dict:
    return json.loads((icons_dir() / "icons.json").read_text(encoding="utf-8"))


def names() -> list[str]:
    return list(manifest()["icons"])


def recolor(svg: str, table: dict[str, str]) -> str:
    """색 문자열을 표대로 바꾼다. 비교는 대소문자를 구분하지 않는다."""
    low = {k.lower(): v for k, v in table.items()}
    return _HEX.sub(lambda m: low.get(m.group(0).lower(), m.group(0)), svg)


def svg_text(name: str, theme_name: str, tint: str | None = None) -> str:
    """없는 이름은 KeyError. tint(hex)를 주면 모든 색을 그 색으로 칠한다(닫기 hover 흰 글리프 등)."""
    entry = manifest()["icons"][name]
    svg = (icons_dir() / entry["file"]).read_text(encoding="utf-8")
    if tint:
        return _HEX.sub(tint, svg)
    if theme_name != "dark":
        svg = recolor(svg, manifest()["recolor"][theme_name])
    return svg


def render(svg: str, px: int) -> QPixmap:
    r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r.render(p, QRectF(0, 0, px, px))
    p.end()
    return pm


def icon(name: str, tint_token: str | None = None) -> QIcon:
    """현재 테마의 아이콘. 없는 이름은 KeyError (오타 방지)."""
    from . import theme
    th = theme.current()
    key = (name, th, tint_token)
    ic = _cache.get(key)
    if ic is None:
        tint = theme.hex_(tint_token) if tint_token else None
        svg = svg_text(name, th, tint)
        ic = QIcon()
        for s in PIXEL_SIZES:
            ic.addPixmap(render(svg, s))
        _cache[key] = ic
    return ic


def app_icon() -> QIcon:
    """앱 아이콘 (resources/app.svg). 테마와 무관하다."""
    key = ("@app", "", None)
    ic = _cache.get(key)
    if ic is None:
        svg = (resources_dir() / "app.svg").read_text(encoding="utf-8")
        ic = QIcon()
        for s in PIXEL_SIZES + (128, 256):
            ic.addPixmap(render(svg, s))
        _cache[key] = ic
    return ic


def clear_cache() -> None:
    """theme.apply()가 부른다. 다음 icon() 호출에서 새 테마로 다시 렌더링된다."""
    _cache.clear()
