# 테마 적용. Fusion 스타일 위에 Design System 토큰으로 QPalette·QSS·글꼴을 만들고 런타임 전환을 알린다.
from __future__ import annotations

import sys

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle

from . import design_tokens as T

STYLE = "Fusion"
DEFAULT = "dark"
THEMES = tuple(T.THEMES)

# Design System README "가독성 규칙" 표. (바탕, 허용 글자). tests가 두 테마 모두 4.5:1 이상인지 확인한다.
# 닫기 hover 글리프의 흰색은 용도 토큰이 없어 팔레트 neutral-0(#ffffff)을 쓴다.
READABILITY: list[tuple[str, tuple[str, ...]]] = [
    ("bg-100", ("ink", "ink-muted")),
    ("bg-200", ("ink", "ink-muted", "ink-faint", "accent", "danger", "warning")),
    ("bg-300", ("ink", "ink-muted")),
    ("bg-400", ("ink",)),
    ("selection", ("ink",)),
    ("selection-inactive", ("ink",)),
    ("search-match", ("ink",)),
    ("hex-header", ("ink",)),
    ("hex-value", ("ink",)),
    ("danger-bg", ("ink", "danger")),
    ("accent", ("accent-ink",)),
    ("caption-close-hover", ("neutral-0",)),
]

_current = DEFAULT


class _Notifier(QObject):
    changed = Signal(str)


_notifier: _Notifier | None = None


def notifier() -> _Notifier:
    """테마가 바뀌면 changed(name). 아이콘을 가진 위젯이 받아 아이콘을 다시 설정한다."""
    global _notifier
    if _notifier is None:
        _notifier = _Notifier()
    return _notifier


def current() -> str:
    return _current


def hex_(name: str, theme: str | None = None) -> str:
    """토큰의 hex 문자열. 없는 토큰은 KeyError."""
    return T.COLORS[theme or _current][name]


def color(name: str, theme: str | None = None) -> QColor:
    return QColor(hex_(name, theme))


def px(name: str) -> int:
    """space-* / radius-* / size-* 값(논리 픽셀)."""
    for table in (T.SIZE, T.SPACE, T.RADIUS):
        if name in table:
            return table[name]
    raise KeyError(name)


def font(style: str) -> QFont:
    s = T.FONT_STYLES[style]
    f = QFont()
    f.setFamilies(T.FONT_FAMILIES[s["family"]])
    f.setPixelSize(s["size"])
    f.setWeight(QFont.Weight(s["weight"]))
    if s["family"] == "mono":
        f.setStyleHint(QFont.StyleHint.Monospace)
        f.setFixedPitch(True)
    return f


def font_line(style: str) -> int:
    """글꼴 스타일의 줄 높이(논리 픽셀)."""
    return T.FONT_STYLES[style]["line"]


def palette(theme: str) -> QPalette:
    """Design System README '가독성 규칙'의 Qt 적용 문단 + Fusion 보조 역할(Spec 2.8.1)."""
    c = lambda n: color(n, theme)  # noqa: E731
    p = QPalette()
    R = QPalette.ColorRole
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive, QPalette.ColorGroup.Disabled):
        p.setColor(group, R.Window, c("bg-100"))
        p.setColor(group, R.Base, c("bg-200"))
        p.setColor(group, R.AlternateBase, c("bg-300"))
        for role in (R.Text, R.WindowText, R.ButtonText):
            p.setColor(group, role, c("ink"))
        p.setColor(group, R.PlaceholderText, c("ink-faint"))
        p.setColor(group, R.HighlightedText, c("ink"))
        p.setColor(group, R.Link, c("accent"))
        p.setColor(group, R.ToolTipBase, c("bg-300"))
        p.setColor(group, R.ToolTipText, c("ink"))
        p.setColor(group, R.Button, c("bg-300"))
        p.setColor(group, R.Light, c("bg-400"))
        p.setColor(group, R.Midlight, c("bg-400"))
        p.setColor(group, R.Mid, c("line-strong"))
        p.setColor(group, R.Dark, c("line-strong"))
        p.setColor(group, R.Shadow, c("bg-000"))
        p.setColor(group, R.BrightText, c("ink"))
    p.setColor(QPalette.ColorGroup.Active, R.Highlight, c("selection"))
    p.setColor(QPalette.ColorGroup.Inactive, R.Highlight, c("selection-inactive"))
    p.setColor(QPalette.ColorGroup.Disabled, R.Highlight, c("selection-inactive"))
    for role in (R.Text, R.WindowText, R.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, c("ink-faint"))
    return p


_QSS = """
QToolTip {{ background: {bg_300}; color: {ink}; border: 1px solid {line_strong}; padding: 2px 4px; }}
QLabel {{ color: {ink}; background: transparent; }}
QLabel[role="muted"] {{ color: {ink_muted}; }}
QLabel[role="danger"] {{ color: {danger}; }}
QLabel[role="info"] {{ background: {bg_300}; color: {ink}; padding: 2px 6px; }}
QLabel[role="page"] {{ background: {bg_200}; color: {ink}; padding: 12px; }}
QLabel:disabled {{ color: {ink_faint}; }}
QLineEdit, QComboBox {{
    background: {bg_300}; color: {ink}; border: 1px solid {line_strong}; border-radius: {radius_sm}px;
    padding: 2px 5px; selection-background-color: {selection}; selection-color: {ink};
}}
QLineEdit:focus, QComboBox:focus {{ border: 2px solid {focus}; padding: 1px 4px; }}
QLineEdit:disabled, QComboBox:disabled {{ color: {ink_faint}; }}
QLineEdit[invalid="true"], QComboBox[invalid="true"] {{ border: 1px solid {danger}; }}
QLineEdit[zero="true"] {{ background: {danger_bg}; color: {ink}; border: 1px solid {danger}; }}
QComboBox QAbstractItemView {{ background: {bg_300}; color: {ink}; selection-background-color: {selection};
    selection-color: {ink}; border: 1px solid {line_strong}; }}
QHeaderView::section {{
    background: {bg_300}; color: {ink_muted}; border: none; border-right: 1px solid {line};
    border-bottom: 1px solid {line}; padding: 0 6px; min-height: {size_row}px; font-weight: 600;
}}
QTreeView, QTableView, QTableWidget, QListWidget, QListView {{
    background: {bg_200}; color: {ink}; border: none; outline: 0;
    selection-background-color: {selection}; selection-color: {ink};
}}
QTreeView::item:hover, QTableView::item:hover, QListView::item:hover {{ background: {bg_400}; color: {ink}; }}
QTreeView::item:selected:active, QTableView::item:selected:active, QListView::item:selected:active {{
    background: {selection}; color: {ink}; }}
QTreeView::item:selected:!active, QTableView::item:selected:!active, QListView::item:selected:!active {{
    background: {selection_inactive}; color: {ink}; }}
QPlainTextEdit, QTextEdit {{ background: {bg_200}; color: {ink}; border: 1px solid {line};
    selection-background-color: {selection}; selection-color: {ink}; }}
QScrollBar:vertical {{ background: {bg_200}; width: 12px; margin: 0; border: none; }}
QScrollBar:horizontal {{ background: {bg_200}; height: 12px; margin: 0; border: none; }}
QScrollBar::handle:vertical {{ background: {line_strong}; min-height: 24px; border-radius: {radius_sm}px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {line_strong}; min-width: 24px; border-radius: {radius_sm}px; margin: 2px; }}
QScrollBar::handle:hover {{ background: {ink_faint}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QTabWidget::pane {{ border: none; border-top: 1px solid {line}; }}
QTabBar::tab {{ background: {bg_100}; color: {ink_muted}; padding: 4px 10px; border: none;
    border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {ink}; border-bottom: 2px solid {accent}; font-weight: 600; }}
QTabBar::tab:hover:!selected {{ background: {bg_400}; color: {ink}; }}
QDockWidget {{ color: {ink}; }}
QDockWidget::title {{ background: {bg_300}; color: {ink}; padding: 4px 6px 4px {edge}px; }}
QStatusBar {{ background: {bg_100}; color: {ink_muted}; font-size: {caption_px}px; }}
QStatusBar QLabel {{ color: {ink_muted}; }}
QStatusBar::item {{ border: none; }}
QMenu {{ background: {bg_300}; color: {ink}; border: 1px solid {line_strong}; border-radius: {radius_md}px; padding: 4px; }}
QMenu::item {{ padding: 4px 16px 4px 8px; border-radius: {radius_sm}px; }}
QMenu::item:selected {{ background: {selection}; color: {ink}; }}
QMenu::item:disabled {{ color: {ink_faint}; }}
QMenu::separator {{ height: 1px; background: {line}; margin: 4px 0; }}
QPushButton {{ background: {bg_300}; color: {ink}; border: 1px solid {line_strong}; border-radius: {radius_sm}px;
    padding: 3px 12px; }}
QPushButton:hover {{ background: {bg_400}; color: {ink}; }}
QPushButton:pressed {{ background: {bg_400}; color: {ink}; }}
QPushButton:focus {{ border: 2px solid {focus}; padding: 2px 11px; }}
QPushButton:disabled {{ color: {ink_faint}; }}
QToolButton {{ background: transparent; color: {ink}; border: none; border-radius: {radius_sm}px; padding: 2px; }}
QToolButton:hover {{ background: {bg_400}; color: {ink}; }}
QToolButton:pressed, QToolButton:checked {{ background: {bg_400}; color: {ink}; }}
QToolButton:disabled {{ color: {ink_faint}; }}
QToolButton:focus {{ border: 2px solid {focus}; }}
QCheckBox, QRadioButton {{ color: {ink}; spacing: 6px; background: transparent; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {ink_faint}; }}
QSplitter::handle {{ background: {line}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QProgressBar {{ background: {bg_300}; color: {ink}; border: 1px solid {line_strong}; border-radius: {radius_sm}px;
    max-height: 10px; }}
QProgressBar::chunk {{ background: {accent}; }}
QFrame[role="panel"] {{ background: {bg_200}; color: {ink}; }}
QFrame[role="bar"] {{ background: {bg_100}; color: {ink}; }}
QFrame[role="header"] {{ background: {bg_300}; color: {ink}; }}
"""


def qss(theme: str) -> str:
    vals = {k.replace("-", "_"): v for k, v in T.COLORS[theme].items()}
    vals.update({k.replace("-", "_"): v for k, v in T.RADIUS.items()})
    vals.update(size_row=T.SIZE["size-row"], caption_px=T.FONT_STYLES["caption"]["size"], edge=T.SIZE["size-edge"])
    return _QSS.format(**vals)


class TokenStyle(QProxyStyle):
    """Fusion 위에서 체크 상자와 라디오 표시만 토큰 색으로 그린다.
    Fusion은 표시 상자를 팔레트 Base로 채우고 Window.darker(140)로 테두리를 그리는데, 앱 QSS의
    `QCheckBox, QRadioButton { background: transparent; }`가 위젯 팔레트의 Window·Base를 투명으로 바꿔 꺼진 상자가
    보이지 않았다. 팔레트만으로는 테두리(line-strong)와 켜진 채움(accent)을 정할 수 없어 여기서 직접 그린다.
    체크 표시는 경로로 그리므로 이미지 자산이 필요 없다."""

    def drawPrimitive(self, pe, opt, p, w=None):
        if pe in (QStyle.PrimitiveElement.PE_IndicatorCheckBox, QStyle.PrimitiveElement.PE_IndicatorRadioButton):
            _draw_indicator(pe == QStyle.PrimitiveElement.PE_IndicatorRadioButton, opt, p)
            return
        super().drawPrimitive(pe, opt, p, w)


_style: TokenStyle | None = None


def _draw_indicator(radio: bool, opt, p: QPainter) -> None:
    """꺼짐: bg-300 바탕 + line-strong 테두리. 켜짐: accent 바탕 + accent-ink 표시. 포커스: focus 테두리.
    비활성: bg-200 바탕 + line 테두리, 표시는 ink-faint (가독성 규칙: accent 위 글자는 accent-ink)."""
    St = QStyle.StateFlag
    on = bool(opt.state & (St.State_On | St.State_NoChange))
    enabled = bool(opt.state & St.State_Enabled)
    focus = bool(opt.state & St.State_HasFocus) and enabled
    if not enabled:
        fill, edge, mark = color("bg-200"), color("line"), color("ink-faint")
    elif on:
        fill, edge, mark = color("accent"), color("accent"), color("accent-ink")
    else:
        fill, edge, mark = color("bg-300"), color("line-strong"), None
    if focus:
        edge = color("focus")
    pw = 2.0 if focus else 1.0
    r = QRectF(opt.rect).adjusted(pw / 2, pw / 2, -pw / 2, -pw / 2)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(edge, pw))
    p.setBrush(fill)
    if radio:
        p.drawEllipse(r)
        if on:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(mark)
            d = r.width() * 0.4
            p.drawEllipse(QRectF(r.center().x() - d / 2, r.center().y() - d / 2, d, d))
    else:
        rad = min(px("radius-sm"), r.width() / 4)
        p.drawRoundedRect(r, rad, rad)
        if on:
            pen = QPen(mark, max(1.5, r.width() / 8))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            x, y, w_, h = r.x(), r.y(), r.width(), r.height()
            if opt.state & St.State_NoChange:  # 부분 선택: 가로선
                p.drawLine(QPointF(x + w_ * 0.25, y + h / 2), QPointF(x + w_ * 0.75, y + h / 2))
            else:
                path = QPainterPath(QPointF(x + w_ * 0.24, y + h * 0.52))
                path.lineTo(QPointF(x + w_ * 0.43, y + h * 0.71))
                path.lineTo(QPointF(x + w_ * 0.77, y + h * 0.31))
                p.drawPath(path)
    p.restore()


def apply(app: QApplication, name: str = DEFAULT) -> None:
    """QPalette → QSS → 아이콘 캐시 비우기 → changed 발신 (Spec 2.8.1). 실행 중에 다시 호출할 수 있다."""
    global _current
    if name not in THEMES:
        raise KeyError(name)
    _current = name
    global _style
    if not isinstance(app.style(), TokenStyle):
        _style = TokenStyle(STYLE)
        app.setStyle(_style)
    app.setFont(font("body"))
    app.setPalette(palette(name))
    app.setStyleSheet(qss(name))
    from .icons import clear_cache
    clear_cache()
    from PySide6.QtCore import Qt
    for w in app.topLevelWidgets():
        if w.isVisible() and not (w.windowFlags() & Qt.WindowType.FramelessWindowHint):
            set_native_dark(w)
    notifier().changed.emit(name)


def set_native_dark(widget) -> None:
    """네이티브 테두리 창의 제목 표시줄을 테마에 맞춘다 (DWMWA_USE_IMMERSIVE_DARK_MODE=20)."""
    if sys.platform != "win32" or not widget.isWindow():
        return
    try:
        import ctypes
        hwnd = int(widget.winId())
        val = ctypes.c_int(1 if _current == "dark" else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
    except Exception:
        pass
