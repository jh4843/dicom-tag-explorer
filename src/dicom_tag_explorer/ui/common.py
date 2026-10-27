# UI 영역들이 함께 쓰는 영역 툴바(최대화 토글), 고정폭 폰트, 선택 행 ink delegate, core 메시지 번역.
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QCoreApplication, QEvent, QSize, Qt, Signal
from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import QHBoxLayout, QLabel, QStyle, QStyledItemDelegate, QToolButton, QWidget

from . import theme
from .icons import icon


def tr_core(text: str) -> str:
    """core(Qt 비의존)가 만든 영어 메시지를 표시할 때 번역한다. 고정 문구만 번역된다 (core_messages.py)."""
    return QCoreApplication.translate("core", text) if text else text


def mono_font(style: str = "mono") -> QFont:
    return theme.font(style)


class SelectionInkDelegate(QStyledItemDelegate):
    """선택된 행은 ForegroundRole 색(ink-muted, danger 등)을 무시하고 HighlightedText(ink)로 그린다.
    행 높이는 size-row이다 (Design System)."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if option.state & QStyle.StateFlag.State_Selected:
            ink = theme.color("ink")
            for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
                option.palette.setColor(group, QPalette.ColorRole.Text, ink)
                option.palette.setColor(group, QPalette.ColorRole.WindowText, ink)

    def sizeHint(self, option, index):
        s = super().sizeHint(option, index)
        return QSize(s.width(), theme.px("size-row"))


def install_ink_delegate(view) -> None:
    view.setItemDelegate(SelectionInkDelegate(view))
    vh = getattr(view, "verticalHeader", None)
    if vh is not None:  # 표는 세로 헤더의 기본 높이를 쓰므로 행 높이를 size-row로 맞춘다
        vh().setDefaultSectionSize(theme.px("size-row"))


class ElideLabel(QLabel):
    """긴 텍스트를 가운데 말줄임(…)으로 그린다. 최소 폭이 텍스트 폭으로 커지지 않아 창 폭을 밀어내지 않고,
    상태 표시줄에서 오른쪽 상태(레벨·배율·Transfer Syntax)가 잘리지 않게 이 라벨이 먼저 줄어든다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._full = ""

    def setText(self, text: str) -> None:
        self._full = text
        self.updateGeometry()
        self._elide()

    def text(self) -> str:
        return self._full

    def sizeHint(self) -> QSize:
        return QSize(self.fontMetrics().horizontalAdvance(self._full) + 2, super().sizeHint().height())

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide()

    def _elide(self) -> None:
        super().setText(self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideMiddle, self.width()))


class AreaToolbar(QWidget):
    """영역 툴바. 더블클릭과 최대화 버튼으로 영역 최대화를 토글한다. 제목은 언어가 바뀌면 다시 읽는다."""
    maximizeToggled = Signal()

    def __init__(self, title: Callable[[], str] | None = None, parent=None, edge_right: bool = False):
        """edge_right: 창 오른쪽 끝에 닿는 영역(Tag, Image)은 오른쪽에 창 가장자리 여백(size-edge)을 둔다."""
        super().__init__(parent)
        self.setObjectName("AreaToolbar")
        self.lay = QHBoxLayout(self)
        right = theme.px("size-edge") if edge_right else theme.px("space-2")
        self.lay.setContentsMargins(theme.px("space-2"), theme.px("space-1"), right, theme.px("space-1"))
        self.lay.setSpacing(theme.px("space-2"))
        self._title_fn = title
        self.title = QLabel()
        self.title.setProperty("role", "muted")
        if title is not None:
            self.lay.addWidget(self.title)
        self.max_btn = QToolButton()
        self.max_btn.setAutoRaise(True)
        self.max_btn.setIconSize(QSize(theme.px("size-icon-sm"), theme.px("size-icon-sm")))
        self._maximized = False
        self.max_btn.clicked.connect(self.maximizeToggled.emit)
        theme.notifier().changed.connect(self.apply_theme)
        self.apply_theme()

    def finish(self) -> None:
        self.lay.addWidget(self.max_btn)

    def set_maximized(self, on: bool) -> None:
        self._maximized = on
        self.apply_theme()

    def apply_theme(self, *_) -> None:
        self.max_btn.setIcon(icon("restore" if self._maximized else "maximize"))
        self.retranslate()

    def retranslate(self) -> None:
        if self._title_fn is not None:
            self.title.setText(self._title_fn())
        tip = (QCoreApplication.translate("AreaToolbar", "Restore (F11, Esc)") if self._maximized
               else QCoreApplication.translate("AreaToolbar", "Maximize (F11)"))
        self.max_btn.setToolTip(tip)
        self.max_btn.setAccessibleName(tip)

    def changeEvent(self, e):
        if e.type() == QEvent.Type.LanguageChange:
            self.retranslate()
        super().changeEvent(e)

    def mouseDoubleClickEvent(self, e):
        self.maximizeToggled.emit()
