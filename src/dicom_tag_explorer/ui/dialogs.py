# UI-04 열기 오류 목록과 UI-07 단축키 목록 대화상자.
from __future__ import annotations

from PySide6.QtCore import QEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from . import theme
from .common import install_ink_delegate, mono_font, tr_core


class _NativeDialog(QDialog):
    """네이티브 테두리 대화상자. 다크 테마면 제목 표시줄도 어둡게 맞춘다 (Spec 2.8.1)."""

    def showEvent(self, e):
        super().showEvent(e)
        theme.set_native_dark(self)

    def changeEvent(self, e):
        if e.type() == QEvent.Type.LanguageChange:
            self.retranslate()
        super().changeEvent(e)

    def retranslate(self) -> None:
        pass


def _table(rows: int, cols: int) -> QTableWidget:
    t = QTableWidget(rows, cols)
    install_ink_delegate(t)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.verticalHeader().hide()
    t.horizontalHeader().setStretchLastSection(True)
    return t


class OpenErrorsDialog(_NativeDialog):
    """파일 경로 | 원인 표와 [경로 복사] [닫기]."""

    def __init__(self, errors: list[tuple], parent=None):
        super().__init__(parent)
        self.resize(760, 360)
        lay = QVBoxLayout(self)
        self.table = _table(len(errors), 2)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        for r, (path, reason) in enumerate(errors):
            self.table.setItem(r, 0, QTableWidgetItem(str(path)))
            self.table.setItem(r, 1, QTableWidgetItem(tr_core(str(reason))))
        self.table.resizeColumnToContents(0)
        lay.addWidget(self.table)
        bl = QHBoxLayout()
        bl.addStretch(1)
        self.copy_btn = QPushButton()
        self.copy_btn.clicked.connect(self.copy_paths)
        self.close_btn = QPushButton()
        self.close_btn.clicked.connect(self.accept)
        bl.addWidget(self.copy_btn)
        bl.addWidget(self.close_btn)
        lay.addLayout(bl)
        self.retranslate()

    def retranslate(self) -> None:
        self.setWindowTitle(self.tr("Open Errors"))
        self.table.setHorizontalHeaderLabels([self.tr("File Path"), self.tr("Reason")])
        self.copy_btn.setText(self.tr("Copy Paths"))
        self.close_btn.setText(self.tr("Close"))

    def copy_paths(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}) or range(self.table.rowCount())
        QGuiApplication.clipboard().setText("\n".join(self.table.item(r, 0).text() for r in rows))


class ShortcutsDialog(_NativeDialog):
    """UI-07. 레지스트리의 명령·단축키와 5.3.2의 범위 한정 키를 표로 보여준다."""

    def __init__(self, reg, parent=None):
        super().__init__(parent)
        self.reg = reg
        self.resize(620, 560)
        lay = QVBoxLayout(self)
        self.table = _table(0, 2)
        lay.addWidget(self.table)
        bl = QHBoxLayout()
        bl.addStretch(1)
        self.close_btn = QPushButton()
        self.close_btn.clicked.connect(self.accept)
        bl.addWidget(self.close_btn)
        lay.addLayout(bl)
        self.retranslate()

    def scoped_keys(self) -> list[tuple[str, str]]:
        """레지스트리 밖의 범위 한정 키 (5.3.2)."""
        return [
            (self.tr("Next match (search box)"), "Enter"),
            (self.tr("Previous match (search box)"), "Shift+Enter"),
            (self.tr("Move cursor by 1 byte (Hex)"), "← / →"),
            (self.tr("Move cursor by 1 line (Hex)"), "↑ / ↓"),
            (self.tr("Move cursor by 1 page (Hex)"), "PgUp / PgDn"),
            (self.tr("Start / end of line (Hex)"), "Home / End"),
            (self.tr("Start / end of file (Hex)"), "Ctrl+Home / Ctrl+End"),
            (self.tr("Select a range (Hex)"), "Shift + " + self.tr("move keys")),
            (self.tr("Exit"), "Alt+F4"),
        ]

    def retranslate(self) -> None:
        self.setWindowTitle(self.tr("Keyboard Shortcuts"))
        self.table.setHorizontalHeaderLabels([self.tr("Command"), self.tr("Shortcut")])
        rows = self.reg.shortcut_table() + self.scoped_keys()
        self.table.setRowCount(len(rows))
        for r, (name, key) in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(name))
            it = QTableWidgetItem(key)
            it.setFont(mono_font("mono-sm"))
            self.table.setItem(r, 1, it)
        self.table.resizeColumnToContents(0)
        self.close_btn.setText(self.tr("Close"))
