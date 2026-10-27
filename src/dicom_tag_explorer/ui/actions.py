# 명령(QAction)을 이름으로 한 곳에 정의하는 레지스트리, 명령 정적 정보 COMMANDS, 리본 배치 RIBBON_LAYOUT.
"""리본·타이틀바·우클릭 메뉴·단축키 목록(UI-07)은 이 레지스트리를 소비만 한다 (Spec 2.8.5).
표시 텍스트는 MainWindow.command_texts()가 tr()로 만들어 넘기고, 언어가 바뀌면 다시 넘긴다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QT_TRANSLATE_NOOP, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMenu, QWidget

from . import icons


@dataclass(frozen=True)
class Command:
    icon: str | None = None
    shortcuts: tuple[str, ...] = ()
    checkable: bool = False
    scope: str = "window"  # window | image (Image 영역 안에서만, 5.3.2)
    menu: bool = False  # 하위 목록(드롭다운) 명령


# 5.3.2 단축키, 5.3.3 아이콘. 단축키는 서로 겹치지 않는다 (SPEC-040, TC-049)
COMMANDS: dict[str, Command] = {
    "file.open": Command("open-file", ("Ctrl+O",)),
    "file.open_folder": Command("open-folder", ("Ctrl+Shift+O",)),
    "file.open_dicomdir": Command("dicomdir"),
    "file.recent": Command("recent", menu=True),
    "file.close": Command("close-file", ("Ctrl+W",)),
    "file.close_all": Command("close-all", ("Ctrl+Shift+W",)),
    "app.settings": Command("settings", ("Ctrl+,",)),
    "edit.copy": Command("copy", ("Ctrl+C",)),
    "edit.copy_tag": Command("copy"),
    "edit.copy_row": Command("copy"),
    "edit.find": Command("search", ("Ctrl+F",)),
    "edit.advanced": Command("search-advanced", ("Ctrl+Shift+F",)),
    "edit.find_prev": Command("prev", ("Shift+F3",)),
    "edit.find_next": Command("next", ("F3",)),
    "edit.goto_offset": Command("goto-offset", ("Ctrl+G",)),
    "view.explorer": Command("dock-float", ("Ctrl+Shift+E",), checkable=True),
    "view.tab_files": Command("folder", ("Ctrl+1",), checkable=True),
    "view.tab_wsi": Command("wsi-slide", ("Ctrl+2",), checkable=True),
    "view.tab_dicomdir": Command("dicomdir", ("Ctrl+3",), checkable=True),
    "view.image_fit": Command("zoom-fit", ("Ctrl+0",), scope="image"),
    "view.image_actual": Command("zoom-actual", ("Ctrl+Alt+0",), scope="image"),
    "view.zoom_in": Command("zoom-in", ("Ctrl+=", "Ctrl++"), scope="image"),
    "view.zoom_out": Command("zoom-out", ("Ctrl+-",), scope="image"),
    "view.rotate_left": Command("rotate-left", ("Ctrl+Shift+R",), scope="image"),
    "view.rotate_right": Command("rotate-right", ("Ctrl+R",), scope="image"),
    "window.maximize_area": Command("maximize", ("F11",)),
    "view.reset_layout": Command("restore"),
    "help.shortcuts": Command("help", ("F1",)),
    "help.about": Command("about"),
    "help.license": Command("license"),
    "ribbon.toggle": Command("ribbon-collapse", ("Ctrl+F1",)),
    "window.cycle_focus": Command(None, ("F6",)),
    "window.escape": Command("stop", ("Esc",)),
}

# [(탭 원문, [(그룹 원문, [(명령 이름, "L" | "S"), ...]), ...]), ...]  (5.3.3, Ribbon README "탭별 명령")
RIBBON_LAYOUT: list[tuple[str, list[tuple[str, list[tuple[str, str]]]]]] = [
    (QT_TRANSLATE_NOOP("Ribbon", "File"), [
        (QT_TRANSLATE_NOOP("Ribbon", "Open"), [("file.open", "L"), ("file.open_folder", "L"), ("file.open_dicomdir", "L")]),
        (QT_TRANSLATE_NOOP("Ribbon", "Files"), [("file.recent", "L"), ("file.close", "S"), ("file.close_all", "S")]),
        (QT_TRANSLATE_NOOP("Ribbon", "App"), [("app.settings", "L")]),
    ]),
    (QT_TRANSLATE_NOOP("Ribbon", "Edit"), [
        (QT_TRANSLATE_NOOP("Ribbon", "Copy"), [("edit.copy", "L"), ("edit.copy_tag", "S"), ("edit.copy_row", "S")]),
        (QT_TRANSLATE_NOOP("Ribbon", "Find"), [("edit.find", "L"), ("edit.advanced", "L"), ("edit.find_prev", "S"),
                                               ("edit.find_next", "S")]),
        (QT_TRANSLATE_NOOP("Ribbon", "Go To"), [("edit.goto_offset", "L")]),
    ]),
    (QT_TRANSLATE_NOOP("Ribbon", "View"), [
        (QT_TRANSLATE_NOOP("Ribbon", "Explorer"), [("view.explorer", "L"), ("view.tab_files", "S"),
                                                   ("view.tab_wsi", "S"), ("view.tab_dicomdir", "S")]),
        (QT_TRANSLATE_NOOP("Ribbon", "Image"), [("view.image_fit", "L"), ("view.image_actual", "L"),
                                                ("view.zoom_in", "S"), ("view.zoom_out", "S"),
                                                ("view.rotate_left", "S"), ("view.rotate_right", "S")]),
        (QT_TRANSLATE_NOOP("Ribbon", "Layout"), [("window.maximize_area", "L"), ("view.reset_layout", "L")]),
    ]),
    (QT_TRANSLATE_NOOP("Ribbon", "Help"), [
        (QT_TRANSLATE_NOOP("Ribbon", "Help"), [("help.shortcuts", "L"), ("help.about", "L"), ("help.license", "L")]),
    ]),
]


class ActionRegistry:
    def __init__(self, owner: QWidget):
        self.owner = owner
        self._actions: dict[str, QAction] = {}
        self._menus: dict[str, QMenu] = {}
        self._icons: dict[str, str | None] = {}

    def define(self, name: str, slot: Callable | None = None, scope_widget: QWidget | None = None) -> QAction:
        """COMMANDS[name]의 정적 정보로 QAction을 만든다.
        scope=image 명령은 scope_widget(Image 영역)에 붙어 그 안에서만 단축키가 동작한다."""
        if name in self._actions:
            raise KeyError(f"중복 명령 이름: {name}")
        cmd = COMMANDS[name]
        if cmd.menu:
            m = QMenu(self.owner)
            m.setObjectName(name)
            self._menus[name] = m
            a = m.menuAction()
        else:
            a = QAction(self.owner)
            if cmd.shortcuts:
                a.setShortcuts([QKeySequence(k) for k in cmd.shortcuts])
            if cmd.checkable:
                a.setCheckable(True)
            target = scope_widget if cmd.scope == "image" and scope_widget is not None else self.owner
            if cmd.scope == "image":
                a.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            target.addAction(a)
            if slot is not None:
                a.triggered.connect(slot)
        a.setObjectName(name)
        self._actions[name] = a
        self._icons[name] = cmd.icon
        return a

    def __getitem__(self, name: str) -> QAction:
        return self._actions[name]  # 없는 이름은 KeyError

    def menu(self, name: str) -> QMenu:
        return self._menus[name]

    def is_menu(self, name: str) -> bool:
        return name in self._menus

    def names(self) -> list[str]:
        return list(self._actions)

    def set_texts(self, texts: dict[str, str]) -> None:
        """언어가 바뀔 때 다시 호출한다. 툴팁은 '명령 이름 (단축키)' (5.3.3)."""
        for name, text in texts.items():
            a = self._actions[name]
            a.setText(text)
            if name in self._menus:
                self._menus[name].setTitle(text)
            keys = a.shortcuts()
            plain = text.replace("&", "").rstrip("…")
            tip = f"{plain} ({keys[0].toString(QKeySequence.SequenceFormat.NativeText)})" if keys else plain
            a.setToolTip(tip)

    def set_icon_name(self, name: str, icon_name: str | None) -> None:
        self._icons[name] = icon_name
        if icon_name:
            self._actions[name].setIcon(icons.icon(icon_name))

    def refresh_icons(self) -> None:
        """테마 변경 시 theme.notifier().changed에서 호출한다."""
        for name, icon_name in self._icons.items():
            if icon_name:
                self._actions[name].setIcon(icons.icon(icon_name))

    def shortcut_table(self) -> list[tuple[str, str]]:
        """(명령 이름, 단축키) — 단축키 목록 창(UI-07)용."""
        out = []
        for name, a in self._actions.items():
            for k in a.shortcuts():
                out.append((a.text().replace("&", ""), k.toString(QKeySequence.SequenceFormat.NativeText)))
        return out
