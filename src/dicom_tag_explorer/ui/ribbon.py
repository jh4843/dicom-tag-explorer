# 리본 위젯. 명령 레지스트리와 RIBBON_LAYOUT을 소비해 탭·그룹·버튼을 만들고 폭에 맞춰 줄이며 접고 편다.
from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMenu, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from . import theme
from .actions import RIBBON_LAYOUT, ActionRegistry
from .icons import icon

LARGE_W = 58
GROUP_LABEL_H = 14  # caption 줄 높이
SMALL_H = 20
MODES = ("design", "small", "dropdown")  # 축소 단계 (Ribbon README)


def tr_ribbon(text: str) -> str:
    return QCoreApplication.translate("Ribbon", text)


def two_lines(text: str, font, width: int) -> str:
    """큰 버튼 라벨을 폭에 맞춰 최대 두 줄로 나눈다 (리본 라벨은 두 줄까지 허용)."""
    fm = QFontMetrics(font)
    if fm.horizontalAdvance(text) <= width or " " not in text:
        return text
    words = text.split(" ")
    best = text
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        if fm.horizontalAdvance(a) <= width and fm.horizontalAdvance(b) <= width:
            return f"{a}\n{b}"
        best = f"{a}\n{b}"
    return best


class RibbonButton(QToolButton):
    """리본 버튼. 일반 명령은 defaultAction을 쓰고, 드롭다운 명령은 setMenu만 쓴다.
    - Qt는 setDefaultAction(메뉴의 menuAction) 뒤 setMenu(같은 메뉴)를 하면 둘 다 지운다. 그래서 드롭다운은
      액션의 changed를 받아 아이콘·텍스트·툴팁을 직접 맞춘다.
    - 큰 버튼은 QAction이 바뀌면(아이콘·텍스트 재설정) Qt가 라벨을 한 줄로 덮어쓰므로 두 줄 라벨을 다시 계산한다 (R-01)."""

    def __init__(self, large: bool, parent=None):
        super().__init__(parent)
        self.large = large
        self.command = None  # 드롭다운 명령의 QAction (menuAction)
        self.dropdown = None  # 붙인 메뉴. PySide6에서 QToolButton.menu()를 부르면 소유권이 바뀌어 메뉴가 지워지므로 직접 보관한다
        self.setObjectName("RibbonLarge" if large else "RibbonSmall")
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon if large
                                else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

    def bind(self, action, menu=None) -> None:
        if menu is None:
            self.setDefaultAction(action)
        else:
            self.command = action
            self.dropdown = menu
            self.setMenu(menu)
            self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            action.changed.connect(self.sync)
        self.sync()

    def action_(self):
        return self.command or self.defaultAction()

    def sync(self) -> None:
        a = self.action_()
        if a is None:
            return
        plain = a.text().replace("&", "")
        if self.command is not None:
            self.setIcon(a.icon())
            self.setToolTip(a.toolTip())
            self.setEnabled(a.isEnabled())
        self.setText(two_lines(plain, theme.font("caption"), LARGE_W - 4) if self.large else plain)
        self.setAccessibleName(plain)  # 라벨의 줄바꿈 없이 명령 이름 그대로 (스크린 리더·UIA)

    def actionEvent(self, e):
        super().actionEvent(e)
        if e.type() == QEvent.Type.ActionChanged and e.action() is self.defaultAction():
            self.sync()


LargeButton = RibbonButton  # 테스트·호환용 이름


class Ribbon(QWidget):
    collapsedChanged = Signal(bool)

    def __init__(self, reg: ActionRegistry, parent=None):
        super().__init__(parent)
        self.reg = reg
        self.setObjectName("Ribbon")
        self.collapsed = False
        self.current = 0
        self.modes: dict[int, list[str]] = {i: ["design"] * len(groups) for i, (_, groups) in enumerate(RIBBON_LAYOUT)}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        # 리본 내용이 창의 최소 폭을 밀어 올리지 않게 한다. 폭이 모자라면 _fit()이 그룹을 줄인다 (R-02)
        lay.setSizeConstraint(QVBoxLayout.SizeConstraint.SetNoConstraint)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

        self.tabbar = QFrame()
        self.tabbar.setObjectName("RibbonTabs")
        self.tabbar.setFixedHeight(theme.px("size-ribbon-tabs"))
        tl = QHBoxLayout(self.tabbar)
        tl.setContentsMargins(theme.px("size-edge"), 0, theme.px("size-edge"), 0)  # 창 가장자리 여백
        tl.setSpacing(theme.px("space-1"))
        self.tab_buttons: list[QToolButton] = []
        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)
        for i in range(len(RIBBON_LAYOUT)):
            b = QToolButton()
            b.setObjectName("RibbonTab")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=i: self._on_tab(k))
            self.tab_group.addButton(b, i)
            tl.addWidget(b)
            self.tab_buttons.append(b)
        tl.addStretch(1)
        self.collapse_btn = QToolButton()
        self.collapse_btn.setObjectName("RibbonCollapse")
        self.collapse_btn.setDefaultAction(reg["ribbon.toggle"])
        self.collapse_btn.setIconSize(QSize(theme.px("size-icon-sm"), theme.px("size-icon-sm")))
        tl.addWidget(self.collapse_btn)
        lay.addWidget(self.tabbar)

        self.body = QFrame()
        self.body.setObjectName("RibbonBody")
        self.body.setFixedHeight(theme.px("size-ribbon-body"))
        self.body.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.body_lay = QHBoxLayout(self.body)
        self.body_lay.setContentsMargins(theme.px("size-edge"), theme.px("space-1"), theme.px("size-edge"), 0)
        self.body_lay.setSizeConstraint(QHBoxLayout.SizeConstraint.SetNoConstraint)
        self.body_lay.setSpacing(0)
        lay.addWidget(self.body)
        self.popup: QFrame | None = None
        self.tab_buttons[0].setChecked(True)
        reg["ribbon.toggle"].triggered.connect(self.toggle_collapsed)
        theme.notifier().changed.connect(self.apply_theme)
        for a in (reg[n] for n in reg.names()):
            a.triggered.connect(self._close_popup)
        self.apply_theme()
        self.retranslate()

    # ---- 표시 ----
    def apply_theme(self, *_):
        c = theme.hex_
        self.setStyleSheet(
            f"#RibbonTabs {{ background: {c('bg-100')}; }}"
            f"#RibbonBody, #RibbonPopup {{ background: {c('bg-200')}; border-bottom: 1px solid {c('line')}; }}"
            f"#RibbonTab {{ color: {c('ink-muted')}; background: transparent; border: none; border-radius: 0;"
            f" border-bottom: 2px solid transparent; padding: 0 10px; min-height: {theme.px('size-ribbon-tabs') - 2}px; }}"
            f"#RibbonTab:checked {{ color: {c('ink')}; font-weight: 600; border-bottom: 2px solid {c('accent')}; }}"
            f"#RibbonTab:hover:!checked {{ color: {c('ink')}; background: {c('bg-400')}; }}"
            f"#RibbonGroupName {{ color: {c('ink-muted')}; font-size: {theme.font('caption').pixelSize()}px; }}"
            f"#RibbonSep {{ background: {c('line')}; }}"
            # 포커스 테두리가 글자 영역을 줄여 라벨이 말줄임되지 않게, 테두리는 늘 2px로 두고 포커스 때 색만 바꾼다 (QA-03).
            # 큰 버튼 글자 폭은 LARGE_W - 4 (two_lines 기준)
            f"#RibbonLarge {{ font-size: {theme.font('caption').pixelSize()}px; border: 2px solid transparent;"
            f" padding: 0; }}"
            f"#RibbonSmall {{ border: 2px solid transparent; padding: 0 2px; }}"
            f"#RibbonLarge:focus, #RibbonSmall:focus {{ border-color: {c('focus')}; }}")
        self.reg.refresh_icons()
        self._rebuild()

    def retranslate(self) -> None:
        for b, (tab, _) in zip(self.tab_buttons, RIBBON_LAYOUT):
            b.setText(tr_ribbon(tab))
        self._update_toggle()
        self.modes = {i: ["design"] * len(g) for i, (_, g) in enumerate(RIBBON_LAYOUT)}
        self._rebuild()

    def changeEvent(self, e):
        if e.type() == QEvent.Type.LanguageChange:
            self.retranslate()
        super().changeEvent(e)

    def _update_toggle(self) -> None:
        a = self.reg["ribbon.toggle"]
        name = "ribbon-expand" if self.collapsed else "ribbon-collapse"
        self.reg.set_icon_name("ribbon.toggle", name)
        a.setText(QCoreApplication.translate("Ribbon", "Expand Ribbon") if self.collapsed
                  else QCoreApplication.translate("Ribbon", "Collapse Ribbon"))
        a.setToolTip(f"{a.text()} (Ctrl+F1)")

    # ---- 버튼 ----
    @staticmethod
    def _large_h() -> int:
        """본문 높이에서 그룹 이름 줄과 위 여백을 뺀 큰 버튼 높이 (32px 아이콘 + 라벨 두 줄)."""
        return theme.px("size-ribbon-body") - GROUP_LABEL_H - theme.px("space-1")

    def _large(self, name: str) -> QToolButton:
        b = RibbonButton(True)
        b.setIconSize(QSize(theme.px("size-icon-lg"), theme.px("size-icon-lg")))
        b.setFixedWidth(LARGE_W)
        b.setFixedHeight(self._large_h())
        b.bind(self.reg[name], self.reg.menu(name) if self.reg.is_menu(name) else None)
        return b

    def _small(self, name: str) -> QToolButton:
        b = RibbonButton(False)
        b.setIconSize(QSize(theme.px("size-icon-sm"), theme.px("size-icon-sm")))
        b.setFixedHeight(SMALL_H)
        b.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        b.bind(self.reg[name], self.reg.menu(name) if self.reg.is_menu(name) else None)
        return b

    def _group(self, title: str, cmds: list[tuple[str, str]], mode: str) -> QWidget:
        g = QWidget()
        v = QVBoxLayout(g)
        v.setContentsMargins(theme.px("space-2"), 0, theme.px("space-2"), 0)
        v.setSpacing(0)
        row = QHBoxLayout()
        row.setSpacing(theme.px("space-1"))
        if mode == "dropdown":
            first = cmds[0][0]
            b = QToolButton()
            b.setObjectName("RibbonLarge")
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            b.setIconSize(QSize(theme.px("size-icon-lg"), theme.px("size-icon-lg")))
            b.setFixedSize(LARGE_W, self._large_h())
            b.setIcon(self.reg[first].icon())
            b.setText(two_lines(tr_ribbon(title) + " ▾", theme.font("caption"), LARGE_W - 4))
            b.setAccessibleName(tr_ribbon(title))
            m = QMenu(b)
            for n, _ in cmds:
                # 하위 메뉴(최근 파일)도 menuAction으로 넣는다. PySide6의 addMenu는 하위 메뉴 소유권을 이 메뉴로
                # 옮겨, 이 드롭다운이 삭제될 때 레지스트리의 메뉴까지 지운다
                m.addAction(self.reg[n])
            b.setMenu(m)
            b.dropdown = m
            b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            row.addWidget(b)
        else:
            stack: QVBoxLayout | None = None
            for n, size in cmds:
                if size == "L" and mode == "design":
                    stack = None
                    row.addWidget(self._large(n), 0, Qt.AlignmentFlag.AlignTop)
                    continue
                if stack is None or stack.count() >= 3:
                    stack = QVBoxLayout()
                    stack.setSpacing(1)
                    col = QWidget()
                    col.setLayout(stack)
                    row.addWidget(col, 0, Qt.AlignmentFlag.AlignTop)
                stack.addWidget(self._small(n))
        v.addLayout(row, 1)
        lab = QLabel(tr_ribbon(title))
        lab.setObjectName("RibbonGroupName")
        lab.setFixedHeight(GROUP_LABEL_H)
        lab.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        v.addWidget(lab)
        return g

    def _clear_body(self) -> None:
        while self.body_lay.count():
            it = self.body_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide()  # 삭제 전까지 남아 그려지지 않게 바로 숨기고 떼어낸다
                w.setParent(None)
                w.deleteLater()

    def _build_page(self, idx: int) -> list[QWidget]:
        out = []
        _, groups = RIBBON_LAYOUT[idx]
        for gi, (title, cmds) in enumerate(groups):
            if gi:
                sep = QFrame()
                sep.setObjectName("RibbonSep")
                sep.setFixedWidth(1)
                out.append(sep)
            out.append(self._group(title, cmds, self.modes[idx][gi]))
        return out

    def _rebuild(self) -> None:
        self._clear_body()
        for w in self._build_page(self.current):
            self.body_lay.addWidget(w)
        self.body_lay.addStretch(1)
        self._fit()

    def _needed(self) -> int:
        w = self.body_lay.contentsMargins().left() + self.body_lay.contentsMargins().right()
        for i in range(self.body_lay.count()):
            it = self.body_lay.itemAt(i)
            if it.widget() is not None:
                w += it.widget().sizeHint().width()
        return w

    def _fit(self) -> None:
        """오른쪽 그룹부터 큰 버튼 → 작은 버튼 → 드롭다운 순으로 줄인다."""
        avail = self.width() if self.width() > 0 else 10_000
        modes = self.modes[self.current]
        changed = False
        while self._needed() > avail:
            gi = next((k for k in range(len(modes) - 1, -1, -1) if modes[k] != "dropdown"), None)
            if gi is None:
                break
            modes[gi] = MODES[MODES.index(modes[gi]) + 1]
            changed = True
            self._clear_body()
            for w in self._build_page(self.current):
                self.body_lay.addWidget(w)
            self.body_lay.addStretch(1)
        return changed

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if e.oldSize().width() != e.size().width():
            self.modes[self.current] = ["design"] * len(RIBBON_LAYOUT[self.current][1])
            self._rebuild()

    def group_modes(self) -> list[str]:
        return list(self.modes[self.current])

    # ---- 탭·접기 ----
    def _on_tab(self, k: int) -> None:
        self.current = k
        self.modes[k] = ["design"] * len(RIBBON_LAYOUT[k][1])
        self._rebuild()
        if self.collapsed:
            self._show_popup()

    def set_tab(self, k: int) -> None:
        self.tab_buttons[k].setChecked(True)
        self._on_tab(k)

    def set_collapsed(self, on: bool) -> None:
        self.collapsed = on
        self._close_popup()
        self.body.setVisible(not on)
        self._update_toggle()
        self.collapsedChanged.emit(on)

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self.collapsed)

    def _show_popup(self) -> None:
        """접힌 상태에서 탭을 누르면 본문을 팝업으로 잠시 펼친다. 바깥을 누르거나 명령을 실행하면 닫힌다."""
        self._close_popup()
        pop = _Popup(self)
        pop.setStyleSheet(self.styleSheet())
        pop.layout().addWidget(self.body)
        self.body.setVisible(True)
        g = self.mapToGlobal(QPoint(0, self.tabbar.height()))
        pop.setGeometry(g.x(), g.y(), self.width(), self.body.height())
        self.popup = pop
        pop.show()

    def restore_body(self) -> None:
        """팝업이 닫힐 때 본문을 리본으로 되돌린다 (팝업과 함께 삭제되지 않게)."""
        if self.body.parent() is not self:
            self.body.setParent(self)
            self.layout().addWidget(self.body)
        self.body.setVisible(not self.collapsed)
        self.popup = None

    def _close_popup(self, *_):
        if self.popup is not None:
            self.popup.close()


class _Popup(QFrame):
    def __init__(self, ribbon: Ribbon):
        super().__init__(ribbon, Qt.WindowType.Popup)
        self.ribbon = ribbon
        self.setObjectName("RibbonPopup")
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)

    def hideEvent(self, e):
        self.ribbon.restore_body()
        super().hideEvent(e)
        self.deleteLater()
