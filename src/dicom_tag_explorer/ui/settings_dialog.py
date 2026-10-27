# UI-06 설정 창. 언어·테마(즉시 적용·저장), 라이선스(FreeType 크레딧, 목록, 원문, 고지 파일 열기), 정보.
from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QListWidget,
    QListWidgetItem, QPlainTextEdit, QPushButton, QRadioButton, QSplitter, QStackedWidget, QTableWidget,
    QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from .. import __version__
from ..core import notices
from . import i18n, theme
from .common import install_ink_delegate, tr_core
from .icons import app_icon, icon, resources_dir

PAGE_LANGUAGE, PAGE_THEME, PAGE_LICENSE, PAGE_ABOUT = range(4)
_ITEM_ICONS = ("language", "theme", "license", "about")


def build_info() -> dict:
    """빌드가 넣은 build_info.json (날짜, 커밋). 소스 실행이면 dev."""
    p = resources_dir() / "build_info.json"
    if getattr(sys, "frozen", False) and p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {"date": "dev", "commit": "dev"}


def notices_file_beside_exe() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    p = Path(sys.executable).resolve().parent / notices.FILE_NAME
    return p if p.is_file() else None


class SettingsDialog(QDialog):
    languageChosen = Signal(str)
    themeChosen = Signal(str)

    def __init__(self, page: int = PAGE_LANGUAGE, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("SettingsDialog")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.resize(720, 480)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)

        # 제목 줄 (드래그 이동, 닫기)
        self.titlebar = QFrame()
        self.titlebar.setObjectName("SettingsTitle")
        self.titlebar.setFixedHeight(theme.px("size-titlebar"))
        tl = QHBoxLayout(self.titlebar)
        tl.setContentsMargins(theme.px("space-5"), 0, 0, 0)
        self.title = QLabel()
        self.title.setFont(theme.font("title"))
        tl.addWidget(self.title, 1)
        self.close_btn = QToolButton()
        self.close_btn.setObjectName("SettingsClose")
        self.close_btn.setFixedSize(46, theme.px("size-titlebar"))
        self.close_btn.clicked.connect(self.reject)
        tl.addWidget(self.close_btn)
        outer.addWidget(self.titlebar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName("SettingsNav")
        self.nav.setFixedWidth(168)
        self.nav.setIconSize(QSize(theme.px("size-icon-sm"), theme.px("size-icon-sm")))
        install_ink_delegate(self.nav)
        for _ in range(4):
            self.nav.addItem(QListWidgetItem())
        body.addWidget(self.nav)
        self.pages = QStackedWidget()
        self.pages.setObjectName("SettingsPages")
        body.addWidget(self.pages, 1)
        outer.addLayout(body, 1)

        # 언어
        self.lang_page, lay = self._page()
        self.lang_head = QLabel()
        self.lang_head.setFont(theme.font("body-strong"))
        lay.addWidget(self.lang_head)
        self.lang_group = QButtonGroup(self)
        self.lang_radios = {}
        for code in i18n.LANGUAGES:
            r = QRadioButton(i18n.LABELS[code])
            self.lang_group.addButton(r)
            self.lang_radios[code] = r
            lay.addWidget(r)
            r.toggled.connect(lambda on, c=code: on and self._lang(c))
        lay.addStretch(1)

        # 테마
        self.theme_page, lay = self._page()
        self.theme_head = QLabel()
        self.theme_head.setFont(theme.font("body-strong"))
        lay.addWidget(self.theme_head)
        self.theme_group = QButtonGroup(self)
        self.theme_radios = {}
        for code in theme.THEMES:
            r = QRadioButton()
            self.theme_group.addButton(r)
            self.theme_radios[code] = r
            lay.addWidget(r)
            r.toggled.connect(lambda on, c=code: on and self._theme(c))
        lay.addStretch(1)

        # 라이선스
        self.lic_page, lay = self._page()
        self.lic_head = QLabel()
        self.lic_head.setFont(theme.font("body-strong"))
        lay.addWidget(self.lic_head)
        self.credit = QLabel()
        self.credit.setWordWrap(True)
        lay.addWidget(self.credit)
        self.lic_dev = QLabel()
        self.lic_dev.setWordWrap(True)
        lay.addWidget(self.lic_dev)
        split = QSplitter(Qt.Orientation.Vertical)
        self.lic_table = QTableWidget(0, 3)
        self.lic_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.lic_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.lic_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.lic_table.verticalHeader().hide()
        self.lic_table.horizontalHeader().setStretchLastSection(True)
        install_ink_delegate(self.lic_table)
        self.lic_text = QPlainTextEdit()
        self.lic_text.setReadOnly(True)
        self.lic_text.setFont(theme.font("mono-sm"))
        split.addWidget(self.lic_table)
        split.addWidget(self.lic_text)
        split.setSizes([160, 200])
        lay.addWidget(split, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.open_notices = QPushButton()
        self.open_notices.clicked.connect(self._open_notices)
        row.addWidget(self.open_notices)
        lay.addLayout(row)
        self.sections = []
        self._load_notices()

        # 정보
        self.about_page, lay = self._page()
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(64, 64))
        lay.addWidget(logo)
        self.app_name = QLabel("DICOM Tag Explorer")
        self.app_name.setFont(theme.font("title"))
        lay.addWidget(self.app_name)
        self.about_info = QLabel()
        self.about_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.about_info)
        lay.addStretch(1)

        for w in (self.lang_page, self.theme_page, self.lic_page, self.about_page):
            self.pages.addWidget(w)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self._sync = True
        self.lang_radios[i18n.current()].setChecked(True)
        self.theme_radios[theme.current()].setChecked(True)
        self._sync = False
        theme.notifier().changed.connect(self.apply_theme)
        self.apply_theme()
        self.retranslate()
        self.nav.setCurrentRow(page)

    def _page(self) -> tuple[QWidget, QVBoxLayout]:
        w = QWidget()
        lay = QVBoxLayout(w)
        m = theme.px("space-5")
        lay.setContentsMargins(m, m, m, m)
        lay.setSpacing(theme.px("space-4"))
        return w, lay

    # ---- 동작 ----
    def _lang(self, code: str) -> None:
        if not self._sync:
            self.languageChosen.emit(code)

    def _theme(self, code: str) -> None:
        if not self._sync:
            self.themeChosen.emit(code)

    def _load_notices(self) -> None:
        data = notices.load()
        has = data is not None
        self.lic_table.setVisible(has)
        self.lic_text.setVisible(has)
        self.lic_dev.setVisible(not has)
        if has:
            head, self.sections = data
            self.lic_table.setRowCount(len(self.sections))
            for r, s in enumerate(self.sections):
                for c, v in enumerate((s.name, s.version, s.license)):
                    it = QTableWidgetItem(v)
                    if c == 1:
                        it.setFont(theme.font("mono-sm"))
                    self.lic_table.setItem(r, c, it)
            self.lic_table.resizeColumnsToContents()
            self.lic_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
            self.lic_table.currentCellChanged.connect(self._show_license)
            self.lic_text.setPlainText(head)
        self.open_notices.setEnabled(notices_file_beside_exe() is not None)

    def _show_license(self, row, *_):
        if 0 <= row < len(self.sections):
            self.lic_text.setPlainText(self.sections[row].text)

    def _open_notices(self) -> None:
        p = notices_file_beside_exe()
        if p is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    # ---- 표시 ----
    def apply_theme(self, *_):
        c = theme.hex_
        self.setStyleSheet(
            f"#SettingsDialog {{ background: {c('bg-200')}; border: 1px solid {c('line-strong')}; }}"
            f"#SettingsTitle {{ background: {c('bg-100')}; }}"
            f"#SettingsNav {{ background: {c('bg-100')}; border: none; border-right: 1px solid {c('line')}; }}"
            f"#SettingsPages {{ background: {c('bg-200')}; }}"
            f"#SettingsClose {{ border: none; border-radius: 0; }}"
            f"#SettingsClose:hover {{ background: {c('caption-close-hover')}; }}")
        self.close_btn.setIcon(icon("close"))
        for i, name in enumerate(_ITEM_ICONS):
            self.nav.item(i).setIcon(icon(name))

    def retranslate(self) -> None:
        self.setWindowTitle(self.tr("Settings"))
        self.title.setText(self.tr("Settings"))
        self.close_btn.setToolTip(self.tr("Close (Esc)"))
        self.close_btn.setAccessibleName(self.tr("Close"))
        # 언어 항목 이름은 두 언어를 함께 써서 잘못 고른 사람도 찾을 수 있게 고정한다 (5.2.5)
        texts = ["언어 · Language", self.tr("Theme"), self.tr("License"), self.tr("About")]
        for i, t in enumerate(texts):
            self.nav.item(i).setText(t)
        self.lang_head.setText("언어 · Language")
        self.theme_head.setText(self.tr("Theme"))
        self.theme_radios["dark"].setText(self.tr("Dark (default)"))
        self.theme_radios["light"].setText(self.tr("Light"))
        self.lic_head.setText(self.tr("Third-party licenses"))
        self.credit.setText(_freetype_credit(self.sections))
        self.lic_dev.setText(tr_core(notices.MSG_DEV))
        self.lic_table.setHorizontalHeaderLabels([self.tr("Name"), self.tr("Version"), self.tr("License")])
        self.open_notices.setText(self.tr("Open Notices File"))
        info = build_info()
        self.about_info.setText(
            self.tr("Version {0}").format(__version__) + "\n"
            + self.tr("Copyright © 2026 VIEWORKS. All rights reserved.") + "\n"
            + self.tr("Build {0} · commit {1}").format(info.get("date", "dev"), info.get("commit", "dev")))

    def changeEvent(self, e):
        if e.type() == QEvent.Type.LanguageChange:
            self.retranslate()
        super().changeEvent(e)

    # ---- 프레임 없는 대화상자 이동 ----
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.titlebar.geometry().contains(e.position().toPoint()):
            self.windowHandle().startSystemMove()
            return
        super().mousePressEvent(e)


def _freetype_credit(sections) -> str:
    """고지 파일 머리말의 FreeType 크레딧 문구 (LIC-02). 소스 실행이면 대장 값."""
    data = notices.load()
    if data is not None:
        for line in data[0].splitlines():
            if "FreeType" in line:
                return line.strip()
    try:
        import tomllib
        root = Path(__file__).resolve().parents[3]
        with open(root / "packaging" / "license_policy.toml", "rb") as fh:
            return tomllib.load(fh)["policy"]["freetype_credit"]
    except (OSError, KeyError, ValueError):
        return ""
