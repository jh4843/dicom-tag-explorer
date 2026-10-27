# QCheckBox·QRadioButton 표시 상자가 두 테마에서 보이는지(꺼짐: bg-300 + line-strong, 켜짐: accent) 렌더링으로 확인한다.
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QFrame, QRadioButton, QStyle, QStyleOptionButton, QVBoxLayout

from dicom_tag_explorer.ui import theme


def _dist(a: QColor, b: QColor) -> int:
    return abs(a.red() - b.red()) + abs(a.green() - b.green()) + abs(a.blue() - b.blue())


def _render(qapp, cls, checked: bool, th: str, focus: bool = False):
    theme.apply(qapp, th)
    host = QFrame()
    host.setProperty("role", "bar")  # 검색 바와 같은 bg-100 바탕
    lay = QVBoxLayout(host)
    w = cls("label")
    w.setChecked(checked)
    if not focus:
        w.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # 창의 유일한 위젯이라 포커스를 받지 않게 한다
    lay.addWidget(w)
    host.resize(120, 40)
    host.show()
    if focus:
        host.activateWindow()
        w.setFocus(Qt.FocusReason.TabFocusReason)
    qapp.processEvents()
    opt = QStyleOptionButton()
    w.initStyleOption(opt)
    se = QStyle.SubElement.SE_CheckBoxIndicator if cls is QCheckBox else QStyle.SubElement.SE_RadioButtonIndicator
    r = w.style().subElementRect(se, opt, w).translated(w.pos())
    img = host.grab().toImage()
    host.close()
    return img, r


@pytest.mark.parametrize("th", ["dark", "light"])
@pytest.mark.parametrize("cls", [QCheckBox, QRadioButton])
def test_unchecked_indicator_visible(qapp, th, cls):
    img, r = _render(qapp, cls, False, th)
    bg = theme.color("bg-100", th)
    border = theme.color("line-strong", th)
    cy = r.center().y()
    # 왼쪽 가장자리에서 안쪽으로 2px 안에 바탕과 확실히 다른 테두리 픽셀이 있다
    edge = [img.pixelColor(r.left() + dx, cy) for dx in range(3)]
    assert max(_dist(c, bg) for c in edge) > 60, (th, [c.name() for c in edge], bg.name())
    assert min(_dist(c, border) for c in edge) < 60, (th, [c.name() for c in edge], border.name())
    # 상자 안쪽은 bg-300
    inner = img.pixelColor(r.center().x() - 2 if cls is QRadioButton else r.left() + 4, cy - 3 if cls is QRadioButton else cy)
    assert _dist(inner, theme.color("bg-300", th)) < 30, (th, inner.name())


@pytest.mark.parametrize("th", ["dark", "light"])
@pytest.mark.parametrize("cls", [QCheckBox, QRadioButton])
def test_checked_indicator_accent(qapp, th, cls):
    img, r = _render(qapp, cls, True, th)
    accent = theme.color("accent", th)
    px = img.pixelColor(r.left() + 3, r.top() + 3) if cls is QCheckBox else img.pixelColor(r.left() + 2, r.center().y())
    assert _dist(px, accent) < 40, (th, px.name(), accent.name())


@pytest.mark.parametrize("th", ["dark", "light"])
def test_focus_indicator_uses_focus_color(qapp, th):
    img, r = _render(qapp, QCheckBox, False, th, focus=True)
    edge = img.pixelColor(r.left(), r.center().y())
    if _dist(edge, theme.color("line-strong", th)) < 30:
        pytest.skip("이 플랫폼에서는 창이 포커스를 받지 못한다")
    assert _dist(edge, theme.color("focus", th)) < 40, (th, edge.name())
