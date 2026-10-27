# 메인 창. 프레임 없는 창에 타이틀바·리본을 두고 명령 정의, 드래그 앤 드롭, 상태바, 열기/선택/동기화 흐름을 조정한다.
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QEvent, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QLabel, QLineEdit, QMainWindow, QProgressBar, QSplitter, QToolButton,
    QVBoxLayout, QWidget,
)

from ..appdata import app_settings
from ..core.classify import group_files
from ..core.dicom_file import DicomFile, FileState, normalize_path
from ..core.dicomdir import DirRecord, build_records
from ..core.element_index import K_ELEMENT
from ..core.image_decode import MSG_CANNOT_DISPLAY, MSG_NO_IMAGE, NO_IMAGE, OK, ts_name
from ..core.indexer import TS_DEFLATE
from ..core.scan import expand_paths
from ..core.search import Criteria, compile_criteria, search
from ..core.values import C_NAME, C_TAG, format_offset
from ..core.wsi import Slide
from ..workers.tasks import CancelToken, Generation, global_pool, submit, take
from . import i18n, theme
from .actions import ActionRegistry
from .common import ElideLabel, tr_core
from .dialogs import OpenErrorsDialog, ShortcutsDialog
from .explorer_dock import TAB_FILES, TAB_WSI, ExplorerDock
from .explorer_models import KIND_DIRROOT, KIND_FILE, KIND_GROUP, KIND_RECORD
from .hex_view import RawPanel
from .icons import app_icon
from .image_view import ZOOM_STEP, ImagePanel, decode_job
from .ribbon import Ribbon
from .settings_dialog import PAGE_ABOUT, PAGE_LANGUAGE, PAGE_LICENSE, SettingsDialog
from .tag_panel import TagPanel
from .titlebar import NativeFrame, TitleBar

APP_NAME = "DICOM Tag Explorer"
log = logging.getLogger("vw.ui")
MAX_RECENT = 10
KEY_LANGUAGE, KEY_THEME, KEY_RIBBON = "ui/language", "ui/theme", "ui/ribbonCollapsed"
KEY_SHOW_ONLY = "ui/searchShowOnly"
KEY_DOCK_MAX = "ui/explorerMaximized"


@dataclass
class Batch:
    token: CancelToken = field(default_factory=CancelToken)
    total: int = 0
    done: int = 0
    errors: list = field(default_factory=list)
    tasks: dict = field(default_factory=dict)  # key → Task
    scanning: int = 0
    finished: bool = False
    added: int = 0


def load_job(f: DicomFile, token) -> tuple[DicomFile, list[DirRecord] | None]:
    """워커: 헤더 색인 + 요약 + (DICOMDIR면) 레코드 트리."""
    f.load(token, keep_open=True)
    recs = None
    try:
        if f.loaded and f.is_dicomdir:
            recs = build_records(f)
    finally:
        f.release()
    return f, recs


def saved_language_and_theme(settings: QSettings) -> tuple[str, str]:
    """메인 창을 만들기 전에 적용할 저장값 (Spec 2.8.6). 첫 실행은 영어·다크."""
    lang = str(settings.value(KEY_LANGUAGE, i18n.DEFAULT))
    th = str(settings.value(KEY_THEME, theme.DEFAULT))
    return (lang if lang in i18n.LANGUAGES else i18n.DEFAULT, th if th in theme.THEMES else theme.DEFAULT)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setObjectName("MainWindow")
        # 프레임 없는 창. Win32 스타일은 NativeFrame.install()이 다시 켠다 (Spec 2.8.4)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setWindowIcon(app_icon())
        self.setMinimumSize(QSize(1280, 720))
        self.setAcceptDrops(True)
        self.settings = app_settings()  # 위치는 app.main의 init_settings_path가 정한다
        self.pool = global_pool()
        self.files: dict[Path, DicomFile] = {}
        self.seq: dict[Path, int] = {}
        self._seq_next = 0
        self.dir_records: dict[Path, list[DirRecord]] = {}
        self.groups = []
        self.cur_kind: str | None = None
        self.cur_key = None
        self.cur_file: DicomFile | None = None
        self.batch: Batch | None = None
        self.last_errors: list = []
        self.file_token: CancelToken | None = None
        self.file_gen = Generation()
        self.image_gen = Generation()
        self.maximized: str | None = None
        self._saved_sizes = None
        self._layout_applied = False
        self._title_file = ""
        self._err_count = 0

        self._build_ui()
        self._init_search()
        self._define_actions()
        self._build_chrome()
        self._build_status()
        self._wsi_timer = QTimer(self)
        self._wsi_timer.setSingleShot(True)
        self._wsi_timer.setInterval(150)
        self._wsi_timer.timeout.connect(self._rebuild_wsi)
        self._restore_settings()
        theme.notifier().changed.connect(self.apply_theme)
        self.retranslate()
        self.set_title("")  # 작업 표시줄·Alt+Tab에 보이는 창 제목 (Spec 2.8.4)

    # ================= UI 구성 =================
    def _build_ui(self) -> None:
        self.dock = ExplorerDock(self)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dock)
        self.dock.nodeSelected.connect(self._on_node_selected)
        self.dock.openFilesRequested.connect(self.open_files_dialog)
        self.dock.openDicomdirRequested.connect(self.open_dicomdir_dialog)
        self.dock.tabs.currentChanged.connect(self._on_tab_changed)

        self.tag = TagPanel()
        self.raw = RawPanel()
        self.image = ImagePanel()
        self.hsplit = QSplitter(Qt.Orientation.Horizontal)
        self.hsplit.setObjectName("BottomSplitter")
        self.hsplit.addWidget(self.raw)
        self.hsplit.addWidget(self.image)
        self.hsplit.setChildrenCollapsible(False)
        self.hsplit.setStretchFactor(0, 0)
        self.hsplit.setStretchFactor(1, 1)
        self.vsplit = QSplitter(Qt.Orientation.Vertical)
        self.vsplit.setObjectName("MainSplitter")
        self.vsplit.addWidget(self.tag)
        self.vsplit.addWidget(self.hsplit)
        self.vsplit.setChildrenCollapsible(False)
        self.setCentralWidget(self.vsplit)
        self.raw.setMinimumWidth(self.raw.min_width())

        # 드래그 앤 드롭 안내: 가운데 상자 bg-300 + focus 2px + ink. 그 밖은 덮지 않는다 (5.3.6)
        self.overlay = QLabel(self.vsplit)
        self.overlay.setObjectName("DropOverlay")
        self.overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overlay.hide()

        self.tag.nodeSelected.connect(self._on_tag_node)
        self.tag.instanceRequested.connect(self._select_instance_from_summary)
        self.tag.cancelRequested.connect(self.cancel_file_job)
        self.tag.model.fragmentsRequested.connect(self._request_fragments)
        self.raw.hex.cursorMoved.connect(self._on_hex_cursor)
        for name, panel in (("tag", self.tag), ("raw", self.raw), ("image", self.image)):
            panel.toolbar.maximizeToggled.connect(lambda n=name: self.toggle_maximize(n))

        self.tag.show_message(self._msg_select)
        self.raw.show_message("")
        self.image.show_message("")

    def _msg_select(self) -> str:
        return self.tr("Select an item in the Explorer.")

    def _define_actions(self) -> None:
        """모든 명령을 레지스트리 한 곳에 정의한다. 리본·타이틀바·우클릭 메뉴·UI-07은 소비만 한다."""
        r = self.actions = ActionRegistry(self)
        v = self.image.view
        slots = {
            "file.open": self.open_files_dialog,
            "file.open_folder": self.open_folder_dialog,
            "file.open_dicomdir": self.open_dicomdir_dialog,
            "file.recent": None,
            "file.close": self.close_current,
            "file.close_all": self.close_all,
            "app.settings": lambda: self.open_settings(PAGE_LANGUAGE),
            "edit.copy": self.copy_focused,
            "edit.copy_tag": self.tag.copy_tag,
            "edit.copy_row": self.tag.copy_row,
            "edit.find": self.focus_search,
            "edit.advanced": self.toggle_advanced,
            "edit.find_prev": lambda: self.search_step(-1),
            "edit.find_next": lambda: self.search_step(1),
            "edit.goto_offset": self.raw.hex.goto_dialog,
            "view.image_fit": v.fit,
            "view.image_actual": v.one_to_one,
            "view.zoom_in": lambda: v.zoom(ZOOM_STEP),
            "view.zoom_out": lambda: v.zoom(1 / ZOOM_STEP),
            "view.rotate_left": lambda: v.rotate_by(-90),
            "view.rotate_right": lambda: v.rotate_by(90),
            "window.maximize_area": self.toggle_maximize_focused,
            "view.reset_layout": self.reset_layout,
            "help.shortcuts": self.show_shortcuts,
            "help.about": lambda: self.open_settings(PAGE_ABOUT),
            "help.license": lambda: self.open_settings(PAGE_LICENSE),
            "ribbon.toggle": None,  # 리본이 연결한다
            "window.cycle_focus": self.cycle_focus,
            "window.escape": self.escape,
        }
        for name, slot in slots.items():
            r.define(name, slot, scope_widget=self.image)
        # Dock의 toggleViewAction()을 리본 버튼에 직접 넘기면, PySide6가 그 래퍼를 버튼의 자식으로 기록해 버튼이
        # 지워질 때(모달 창의 중첩 이벤트 루프가 지연 삭제를 처리할 때) 래퍼를 무효화한다 (QA-02).
        # 그래서 레지스트리에는 Python이 만든 QAction을 두고 Dock 토글 액션과 상태만 잇는다
        dock_toggle = self.dock.toggleViewAction()
        explorer = r.define("view.explorer", lambda _=False: self._toggle_explorer(dock_toggle))
        explorer.setChecked(dock_toggle.isChecked())
        dock_toggle.toggled.connect(explorer.setChecked)
        grp = QActionGroup(self)
        self.tab_actions = []
        for i, key in enumerate(("files", "wsi", "dicomdir")):
            a = r.define(f"view.tab_{key}", lambda _=False, k=i: self.set_tab(k))
            grp.addAction(a)
            self.tab_actions.append(a)
        self.tab_actions[0].setChecked(True)
        self.recent_menu = r.menu("file.recent")
        self.tag.set_registry(r)
        self.image.bind_actions(r)

    def _toggle_explorer(self, dock_toggle) -> None:
        # 최소화한 Floating 창은 Qt가 숨김으로 보므로 토글 대신 최소화 전 상태(최대화 포함)로 되돌린다
        if self.dock.isFloating() and self.dock.isMinimized():
            self.dock.setWindowState(self.dock.windowState() & ~Qt.WindowState.WindowMinimized)
            self.dock.activateWindow()
        else:
            dock_toggle.trigger()

    def command_texts(self) -> dict[str, str]:
        """명령 표시 텍스트 (영어 원문, tr). 언어가 바뀌면 다시 호출한다 (Spec 2.8.5)."""
        return {
            "file.open": self.tr("Open File"), "file.open_folder": self.tr("Open Folder"),
            "file.open_dicomdir": self.tr("Open DICOMDIR"), "file.recent": self.tr("Recent Files"),
            "file.close": self.tr("Close"), "file.close_all": self.tr("Close All"), "app.settings": self.tr("Settings"),
            "edit.copy": self.tr("Copy"), "edit.copy_tag": self.tr("Copy TAG"), "edit.copy_row": self.tr("Copy Row"),
            "edit.find": self.tr("Find"), "edit.advanced": self.tr("Advanced Search"), "edit.find_prev": self.tr("Previous"),
            "edit.find_next": self.tr("Next"), "edit.goto_offset": self.tr("Go to Offset"),
            "view.explorer": self.tr("Explorer Pane"), "view.tab_files": self.tr("Files"), "view.tab_wsi": "WSI",
            "view.tab_dicomdir": "DICOMDIR", "view.image_fit": self.tr("Fit"), "view.image_actual": "1:1",
            "view.zoom_in": self.tr("Zoom In"), "view.zoom_out": self.tr("Zoom Out"), "view.rotate_left": self.tr("Rotate Left"),
            "view.rotate_right": self.tr("Rotate Right"), "window.maximize_area": self.tr("Maximize Area"),
            "view.reset_layout": self.tr("Reset Layout"), "help.shortcuts": self.tr("Keyboard Shortcuts"),
            "help.about": self.tr("About"), "help.license": self.tr("License"), "window.cycle_focus": self.tr("Next Area"),
            "window.escape": self.tr("Cancel / Restore"),
        }

    def _build_chrome(self) -> None:
        """타이틀바 + 리본을 menuWidget으로 둔다 (5.3.1)."""
        self.titlebar = TitleBar(self)
        self.titlebar.settingsClicked.connect(lambda: self.open_settings(PAGE_LANGUAGE))
        self.ribbon = Ribbon(self.actions)
        top = QWidget()
        lay = QVBoxLayout(top)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.titlebar)
        lay.addWidget(self.ribbon)
        self.setMenuWidget(top)
        self.native = NativeFrame(self, self.titlebar)
        self.actions.set_texts(self.command_texts())
        self.ribbon.retranslate()
        collapsed = str(self.settings.value(KEY_RIBBON, "false")).lower() == "true"
        self.ribbon.set_collapsed(collapsed)
        # 초기 상태를 적용한 뒤에 연결해 시작할 때마다 저장값을 다시 쓰지 않는다
        self.ribbon.collapsedChanged.connect(lambda on: self.settings.setValue(KEY_RIBBON, on))
        self._rebuild_recent()

    def _build_status(self) -> None:
        sb = self.statusBar()
        sb.setContentsMargins(theme.px("size-edge"), 0, theme.px("size-edge"), 0)  # 창 가장자리 여백
        self.err_label = QLabel()
        self.err_label.setTextFormat(Qt.TextFormat.RichText)
        self.err_label.linkActivated.connect(lambda _: self.show_open_errors())
        self.err_label.hide()
        self._err_count = 0
        sb.addWidget(self.err_label)
        self.path_label = ElideLabel()  # 긴 경로는 가운데 말줄임. 오른쪽 상태가 잘리지 않게 먼저 줄어든다
        self.ts_label = QLabel()
        self.zoom_label = QLabel()
        self.zoom_label.setFont(theme.font("mono-sm"))
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(160)
        self.progress.setTextVisible(False)
        self.progress_label = QLabel()
        self.cancel_btn = QToolButton()
        self.cancel_btn.clicked.connect(self.cancel_batch)
        for w in (self.path_label, self.ts_label, self.zoom_label, self.progress_label, self.progress,
                  self.cancel_btn):
            sb.addPermanentWidget(w)
        self._set_progress(None)
        self.image.statusChanged.connect(self.zoom_label.setText)
        self.image.tilesPending.connect(self._on_tiles_pending)

    # ================= 프레임 없는 창 (Win32) =================
    def nativeEvent(self, event_type, message):
        if sys.platform == "win32" and event_type == b"windows_generic_MSG":
            handled, result = self.native.handle(message)
            if handled:
                return True, result
        return super().nativeEvent(event_type, message)

    def changeEvent(self, e):
        if e.type() == QEvent.Type.WindowStateChange:
            self.titlebar.update_maximized()
        elif e.type() == QEvent.Type.LanguageChange:
            self.retranslate()
        super().changeEvent(e)

    def set_title(self, name: str = "") -> None:
        """창 제목(작업 표시줄·Alt+Tab)과 타이틀바를 함께 바꾼다."""
        self._title_file = name
        self.setWindowTitle(f"{APP_NAME} - {name}" if name else APP_NAME)
        self.titlebar.set_file(name)

    # ================= 번역·테마·설정 창 =================
    def retranslate(self) -> None:
        """LanguageChange 때 명령 텍스트, 고정 라벨, 모델 문자열, 현재 정보 줄을 다시 만든다 (Spec 2.8.3)."""
        self.actions.set_texts(self.command_texts())
        self.overlay.setText(self.tr("Drop here to open"))
        self.cancel_btn.setText(self.tr("Cancel"))
        self.cancel_btn.setToolTip(self.tr("Cancel (Esc)"))
        if self._err_count:
            self._show_err_label()
        self._rebuild_recent()
        self._refresh_models()
        if self.cur_file is not None and self.cur_file.loaded and self.tag.current_node() >= 0:
            self._on_tag_node(self.tag.current_node(), scroll=False)

    def apply_theme(self, _name: str = "") -> None:
        """theme.apply()가 알릴 때 인라인 스타일과 모델의 아이콘·색을 다시 적용한다."""
        c = theme.hex_
        self.overlay.setStyleSheet(f"#DropOverlay {{ background: {c('bg-300')}; color: {c('ink')};"
                                   f" border: 2px solid {c('focus')}; border-radius: {theme.px('radius-md')}px;"
                                   f" font-size: {theme.font('title').pixelSize()}px; padding: 24px; }}")
        self.actions.refresh_icons()
        self._refresh_models()
        self.update()

    def _refresh_models(self) -> None:
        for f in self.files.values():
            self.dock.files_model.update_file(f)
        self.dock.files_model.refresh_icons()
        self.dock.dir_model.clear_all()
        for key, recs in self.dir_records.items():
            self.dock.dir_model.add_dicomdir(self.files[key], recs)
        self._rebuild_wsi()

    def open_settings(self, page: int = PAGE_LANGUAGE) -> None:
        dlg = SettingsDialog(page, self)
        dlg.languageChosen.connect(self.set_language)
        dlg.themeChosen.connect(self.set_theme)
        dlg.exec()

    def set_language(self, lang: str) -> None:
        """재시작 없이 번역기를 바꾸고 저장한다."""
        i18n.apply(QApplication.instance(), lang)
        self.settings.setValue(KEY_LANGUAGE, lang)

    def set_theme(self, name: str) -> None:
        theme.apply(QApplication.instance(), name)
        self.settings.setValue(KEY_THEME, name)

    def show_shortcuts(self) -> None:
        ShortcutsDialog(self.actions, self).exec()

    def _restore_settings(self) -> None:
        g = self.settings.value("geometry")
        if g is not None:
            self.restoreGeometry(g)
        st = self.settings.value("windowState")
        if st is not None:
            self.restoreState(st)
            self.dock.restore_maximized = str(self.settings.value(KEY_DOCK_MAX, "false")).lower() == "true"
        for sp, key in ((self.vsplit, "vsplit"), (self.hsplit, "hsplit")):
            v = self.settings.value(key)
            if v is not None:
                sp.restoreState(v)
                self._layout_applied = True

    def _save_settings(self) -> None:
        if self.maximized:
            self.restore_maximize()
        # 최대화한 Floating 창은 일반 크기로 되돌린 뒤 저장해야 saveState에 복원용 크기가 남는다.
        # showNormal()의 크기 변경은 비동기라 일반 크기를 직접 넣는다
        dock_max = self.dock.isFloating() and self.dock.isMaximized()
        if dock_max:
            normal = self.dock.normalGeometry()
            self.dock.showNormal()
            self.dock.setGeometry(normal)
        self.settings.setValue(KEY_DOCK_MAX, dock_max)
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.setValue("vsplit", self.vsplit.saveState())
        self.settings.setValue("hsplit", self.hsplit.saveState())

    def showEvent(self, e):
        super().showEvent(e)
        self.native.install()
        if not self._layout_applied:
            self._layout_applied = True
            QTimer.singleShot(0, self._apply_default_sizes)

    def _apply_default_sizes(self) -> None:
        h = self.vsplit.height()
        self.vsplit.setSizes([int(h * 0.55), h - int(h * 0.55)])
        w = self.hsplit.width()
        rw = self.raw.min_width()
        self.hsplit.setSizes([rw, max(320, w - rw)])
        self.resizeDocks([self.dock], [300], Qt.Orientation.Horizontal)

    def reset_layout(self) -> None:
        self.restore_maximize()
        for k in ("windowState", "vsplit", "hsplit"):
            self.settings.remove(k)
        self.dock.setFloating(False)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dock)
        self.dock.show()
        self._apply_default_sizes()

    def closeEvent(self, e):
        self._save_settings()
        if self.batch and not self.batch.finished:
            self.cancel_batch()
        self.on_close_hook()
        super().closeEvent(e)

    def on_close_hook(self) -> None:
        """열린 슬라이드를 닫고 타일 작업이 끝나기를 기다린다."""
        self.image_gen.next()
        self.image.show_message("")
        self.image.tile_pool.waitForDone(3000)

    # ================= 최근 파일 =================
    def _recent(self) -> list[str]:
        v = self.settings.value("recent", [])
        if isinstance(v, str):
            v = [v]
        return list(v or [])

    def _add_recent(self, paths) -> None:
        r = self._recent()
        for p in paths:
            s = str(p)
            r = [x for x in r if normalize_path(x) != normalize_path(s)]
            r.insert(0, s)
        self.settings.setValue("recent", r[:MAX_RECENT])
        # 최근 파일 항목에서 호출되면 실행 중인 그 QAction을 지우게 되므로 다음 이벤트 루프에서 재구성한다
        QTimer.singleShot(0, self._rebuild_recent)

    def _rebuild_recent(self) -> None:
        self.recent_menu.clear()
        r = self._recent()
        if not r:
            a = self.recent_menu.addAction(self.tr("(none)"))
            a.setEnabled(False)
            return
        for i, p in enumerate(r):
            self.recent_menu.addAction(f"&{(i + 1) % 10} {p}", lambda _=False, x=p: self.open_paths([x]))

    # ================= 열기 =================
    def open_files_dialog(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, self.tr("Open File"), self._last_dir(), self.tr("All files (*)"))
        if paths:
            self._remember_dir(paths[0])
            self.open_paths(paths)

    def open_folder_dialog(self) -> None:
        d = QFileDialog.getExistingDirectory(self, self.tr("Open Folder"), self._last_dir())
        if d:
            self._remember_dir(d)
            self.open_paths([d])

    def open_dicomdir_dialog(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, self.tr("Open DICOMDIR"), self._last_dir(),
                                       "DICOMDIR (DICOMDIR);;" + self.tr("All files (*)"))
        if p:
            self._remember_dir(p)
            self.open_paths([p])

    def _last_dir(self) -> str:
        return str(self.settings.value("lastDir", ""))

    def _remember_dir(self, p: str) -> None:
        pp = Path(p)
        self.settings.setValue("lastDir", str(pp if pp.is_dir() else pp.parent))

    def open_paths(self, paths, add_recent: bool = True) -> None:
        paths = [Path(p) for p in paths]
        if not paths:
            return
        if add_recent:
            self._add_recent(paths)
        # 이미 열린 파일 하나만 지정했으면 기존 노드를 선택한다
        if len(paths) == 1 and normalize_path(paths[0]) in self.files:
            self.reveal_file(normalize_path(paths[0]))
            return
        if self.batch is None or self.batch.finished:
            self.batch = Batch()
            self.last_errors = []
            self.err_label.hide()
        self._err_count = 0
        b = self.batch
        b.scanning += 1
        self._set_progress(self.tr("Scanning files…"), busy=True)
        submit(self.pool, expand_paths, paths, b.token, on_done=self._on_scanned,
               on_failed=self._on_scan_failed, tag=b)

    def _on_scan_failed(self, msg: str, b: Batch) -> None:
        b.scanning -= 1
        if msg.startswith("Cancelled"):
            self._maybe_finish(b)
            return
        b.errors.append((self.tr("(folder scan)"), msg))
        self._maybe_finish(b)

    def _on_scanned(self, res, b: Batch) -> None:
        b.scanning -= 1
        b.errors.extend(res.errors)
        if b.token.is_cancelled():
            self._maybe_finish(b)
            return
        new = []
        for p in res.files:
            k = normalize_path(p)
            if k in self.files or k in b.tasks:
                continue
            new.append(p)
        if not new and len(res.files) == 1:
            self.reveal_file(normalize_path(res.files[0]))
        for p in new:
            f = DicomFile(p)
            self.seq[f.key] = self._seq_next
            self._seq_next += 1
            b.total += 1
            b.tasks[f.key] = submit(self.pool, load_job, f, b.token, on_done=self._on_loaded,
                                    on_failed=lambda m, tag, ff=f: self._on_load_failed(ff, m, tag), tag=b)
        self._update_batch_progress(b)
        self._maybe_finish(b)

    def _on_load_failed(self, f: DicomFile, msg: str, b: Batch) -> None:
        f.state = FileState.FAILED
        f.error = msg
        self._on_loaded((f, None), b)

    def _on_loaded(self, result, b: Batch) -> None:
        f, recs = result
        b.tasks.pop(f.key, None)
        b.done += 1
        if f.key in self.files:
            return
        if f.state == FileState.FAILED:
            b.errors.append((f.path, f.error))
        self._add_file(f, recs)
        b.added += 1
        self._update_batch_progress(b)
        self._maybe_finish(b)

    def _add_file(self, f: DicomFile, recs) -> None:
        if f.key not in self.seq:
            self.seq[f.key] = self._seq_next
            self._seq_next += 1
        self.files[f.key] = f
        self.dock.files_model.add_file(f, self.seq[f.key])
        if recs is not None:
            self.dir_records[f.key] = recs
            self.dock.dir_model.add_dicomdir(f, recs)
        self.dock.dir_model.update_image_info(f)
        self._wsi_timer.start()
        self.dock.refresh_empty()

    def _update_batch_progress(self, b: Batch) -> None:
        if b is self.batch and not b.finished:
            if b.total:
                self._set_progress(self.tr("Reading files {0} / {1}").format(b.done, b.total), b.done, b.total)

    def _maybe_finish(self, b: Batch) -> None:
        if b.finished or b.scanning > 0 or b.done < b.total:
            return
        self._finish_batch(b)

    def _finish_batch(self, b: Batch, cancelled: bool = False) -> None:
        b.finished = True
        log.info("열기 배치 종료: 추가 %d, 오류 %d, 취소 %s", b.added, len(b.errors), cancelled)
        self._set_progress(None)
        self._rebuild_wsi()
        self.last_errors = list(b.errors)
        if b.errors:
            self._err_count = len(b.errors)
            self._show_err_label()
        self.statusBar().showMessage(self.tr("Cancelled") if cancelled
                                     else self.tr("Opened %n file(s).", "", b.added), 5000)
        if b.added:
            self.set_tab(TAB_WSI if self.groups else TAB_FILES)

    def _show_err_label(self) -> None:
        c = theme.hex_("accent")
        details = self.tr("Details")
        self.err_label.setText(self.tr("%n file(s) could not be opened.", "", self._err_count)
                               + f" <a href='#' style='color:{c}'>{details}</a>")
        self.err_label.show()

    def cancel_batch(self) -> None:
        b = self.batch
        if b is None or b.finished:
            return
        b.token.cancel()
        # 시작 전 작업은 큐에서 꺼내 버린다. 실행 중 작업은 토큰으로 중단되고 결과는 그대로 반영한다
        for key, t in list(b.tasks.items()):
            if take(self.pool, t):
                b.tasks.pop(key, None)
                b.total -= 1
        self._finish_batch(b, cancelled=True)

    def show_open_errors(self) -> None:
        if self.last_errors:
            OpenErrorsDialog(self.last_errors, self).exec()

    def _set_progress(self, text: str | None, value: int = 0, total: int = 0, busy: bool = False) -> None:
        on = text is not None
        self.progress.setVisible(on)
        self.cancel_btn.setVisible(on)
        self.progress_label.setVisible(on)
        if on:
            self.progress_label.setText(text)
            if busy:
                self.progress.setRange(0, 0)
            else:
                self.progress.setRange(0, max(1, total))
                self.progress.setValue(value)

    def _rebuild_wsi(self) -> None:
        files = sorted(self.files.values(), key=lambda f: self.seq.get(f.key, 0))
        self.groups, non_wsi = group_files(files)
        self.dock.wsi_model.rebuild(self.groups, non_wsi)
        self.dock.refresh_empty()
        self._sync_tab_selection()

    # ================= 닫기 =================
    def close_current(self) -> None:
        if self.cur_kind != "file" or self.cur_key not in self.files:
            return
        key = self.cur_key
        self._clear_views()
        f = self.files.pop(key)
        f.release()
        self.dock.files_model.remove_file(key)
        if key in self.dir_records:
            self.dir_records.pop(key)
            self.dock.dir_model.remove_dicomdir(key)
        self._rebuild_wsi()

    def close_all(self) -> None:
        self.cancel_batch()
        self._clear_views()
        for f in self.files.values():
            f.release()
        self.files.clear()
        self.dir_records.clear()
        self.dock.files_model.clear_all()
        self.dock.dir_model.clear_all()
        self.err_label.hide()
        self._err_count = 0
        self._rebuild_wsi()

    def _clear_views(self) -> None:
        self.cancel_file_job()
        self._release_current()
        self.cur_kind = self.cur_key = None
        self.tag.show_message(self._msg_select)
        self.raw.show_message("")
        self.clear_image()
        self.path_label.setText("")
        self.ts_label.setText("")
        self.set_title("")
        self.search_reset()

    def _release_current(self) -> None:
        if self.cur_file is not None:
            self.cur_file.release()
            self.cur_file = None

    # ================= 선택 =================
    def _on_node_selected(self, kind: str, key) -> None:
        if kind in (KIND_FILE, KIND_DIRROOT):
            f = self.files.get(key)
            if f is not None:
                self.show_file(f)
        elif kind == KIND_GROUP:
            self.show_group(key)
        elif kind == KIND_RECORD:
            dd_key, rec = key
            self.show_record(dd_key, rec)

    def reveal_file(self, key) -> None:
        """기존 노드를 선택해 표시한다 (중복 열기, 요약표 더블클릭)."""
        f = self.files.get(key)
        if f is None:
            return
        tab = self.dock.tabs.currentIndex()
        if not self.dock.select_key(key, tab, emit=False):
            self.set_tab(TAB_FILES)
            self.dock.select_key(key, TAB_FILES, emit=False)
        self.show_file(f)

    def _select_instance_from_summary(self, key) -> None:
        self.dock.select_key(key, TAB_WSI, emit=False)
        f = self.files.get(key)
        if f is not None:
            self.show_file(f)

    def set_tab(self, i: int) -> None:
        self.dock.tabs.setCurrentIndex(i)
        if not self.dock.isVisible():
            self.dock.show()

    def _on_tab_changed(self, i: int) -> None:
        self.tab_actions[i].setChecked(True)
        self._sync_tab_selection()

    def _sync_tab_selection(self) -> None:
        if self.cur_key is not None:
            self.dock.select_key(self.cur_key, emit=False)

    def cancel_file_job(self) -> None:
        if self.file_token is not None:
            self.file_token.cancel()
            self.file_token = None

    def show_file(self, f: DicomFile, select_node: int | None = None) -> None:
        self.cancel_file_job()
        gen = self.file_gen.next()
        self.cur_kind, self.cur_key = "file", f.key
        self.set_title(f.path.name)
        self.path_label.setText(str(f.path))
        self.ts_label.setText(f.transfer_syntax_name)
        if self.cur_file is not None and self.cur_file is not f:
            self._release_current()
        if f.state in (FileState.CANCELLED, FileState.PENDING) or (f.state != FileState.FAILED and f.index is None):
            self._reparse(f, gen, select_node)
            return
        self.cur_file = f
        if f.state == FileState.FAILED:
            self.tag.show_message(lambda err=f.error: self.tr("Cannot read the file. {0}").format(tr_core(err or "")))
            try:
                f.open_source()
                self.raw.show_bytes(f.read_raw, f.size)
            except OSError:
                self.raw.show_message("")
            self.clear_image()
            self.search_set_enabled(False)
            return
        f.open_source()
        self.tag.show_file(f)
        self.raw.show_bytes(f.read_raw, f.size, deflate=f.transfer_syntax == TS_DEFLATE)
        self.search_set_enabled(True)
        self.search_file_changed()
        self.show_image_for_file(f)
        if select_node is not None:
            self.tag.select_node(select_node)

    def _reparse(self, f: DicomFile, gen: int, select_node) -> None:
        tok = self.file_token = CancelToken()
        f.state = FileState.PENDING

        def show_loading():
            if self.file_gen.is_current(gen) and f.state == FileState.PENDING:
                self.tag.show_loading()
                self.statusBar().showMessage(self.tr("Reading…"))

        QTimer.singleShot(500, show_loading)
        self.raw.show_message("")
        self.clear_image()

        def done(result, _tag):
            ff, recs = result
            if ff.key not in self.files:
                self._add_file(ff, recs)
                self._wsi_timer.start()
            else:
                self.dock.files_model.update_file(ff)
                if recs is not None and ff.key not in self.dir_records:
                    self.dir_records[ff.key] = recs
                    self.dock.dir_model.add_dicomdir(ff, recs)
                self._wsi_timer.start()
            self.statusBar().clearMessage()
            if not self.file_gen.is_current(gen):
                return
            if ff.state == FileState.CANCELLED:
                self.tag.show_message(lambda: self.tr("Cancelled"))
                return
            self.show_file(ff, select_node)

        submit(self.pool, load_job, f, tok, on_done=done, tag=gen)

    def show_group(self, gkey) -> None:
        g = self.dock.wsi_model.group_data.get(gkey)
        if g is None:
            return
        self.cancel_file_job()
        self.file_gen.next()
        self._release_current()
        self.cur_kind, self.cur_key = "group", gkey
        self.set_title(g.name)
        self.path_label.setText(str(g.instances[0].file.path.parent) if g.instances else "")
        self.ts_label.setText(g.instances[0].file.transfer_syntax_name if g.instances else "")
        self.tag.show_wsi(g, lambda f: f.transfer_syntax_name)
        self.raw.show_message(lambda: self.tr("A WSI image has no single RAW. Select an Instance in the Explorer."))
        self.search_set_enabled(False)
        self.show_image_for_group(g)

    def show_record(self, dd_key, rec: DirRecord) -> None:
        dd = self.files.get(dd_key)
        if rec.ref_path is not None:
            if not rec.exists:
                self.cancel_file_job()
                self.file_gen.next()
                self._release_current()
                self.cur_kind, self.cur_key = "record", None
                self.tag.show_message(lambda p=rec.ref_path: self.tr("Referenced file not found. {0}").format(p))
                self.raw.show_message("")
                self.clear_image()
                self.search_set_enabled(False)
                return
            key = normalize_path(rec.ref_path)
            f = self.files.get(key)
            if f is None:
                f = DicomFile(rec.ref_path)
                self.seq[f.key] = self._seq_next
                self._seq_next += 1
            self.show_file(f)
            return
        if dd is not None:
            self.show_file(dd, select_node=rec.node)

    # ================= Tag ↔ RAW =================
    def _info_text(self, f: DicomFile, nid: int) -> str:
        idx = f.index
        cols = f.formatter.columns(nid)
        label = cols[C_TAG] if idx.kind[nid] != K_ELEMENT else f"{cols[C_TAG]} {cols[C_NAME]}"
        if idx.is_virtual(nid):
            return f"{label} │ " + self.tr("Deflate body (no original file position)")
        s, h, t = idx.start[nid], idx.header_len[nid], idx.total_len[nid]
        end = s + max(t, 1) - 1
        return (f"{label} │ 0x{format_offset(s, f.size)}–0x{format_offset(end, f.size)} │ "
                + self.tr("header {0} + value {1} = {2} bytes").format(h, f"{t - h:,}", f"{t:,}"))

    def _on_tag_node(self, nid: int, scroll: bool = True) -> None:
        f = self.cur_file
        if f is None or not f.loaded or nid < 0:
            self.raw.hex.clear_highlight()
            self.raw.set_info(None)
            return
        idx = f.index
        if idx.is_virtual(nid):
            self.raw.hex.clear_highlight()
        else:
            self.raw.hex.set_highlight(idx.start[nid], idx.header_len[nid], idx.total_len[nid], scroll)
        self.raw.set_info(self._info_text(f, nid))

    def _on_hex_cursor(self, off: int) -> None:
        f = self.cur_file
        self.statusBar().showMessage(f"Offset 0x{format_offset(off, max(f.size if f else 0, 1))} ({off})")
        if f is None or not f.loaded:
            return
        nid = f.index.find(off)
        if nid is None:
            return
        if f.index.needs_fragments(nid):
            self._request_fragments(nid)
        if not self.tag.select_node(nid, emit=False):
            # Show only로 숨겨진 노드: Tree 선택은 그대로 두고 안내한다 (SPEC-041)
            self.statusBar().showMessage(self.tr("The item at this offset is hidden by Show only."), 5000)
            return
        self._on_tag_node(nid, scroll=False)

    def _request_fragments(self, nid: int) -> None:
        f = self.cur_file
        if f is None or not f.index.needs_fragments(nid):
            return
        pending = getattr(f, "_frag_pending", set())
        if nid in pending:
            return
        pending.add(nid)
        f._frag_pending = pending
        tok = CancelToken()
        self.statusBar().showMessage(self.tr("Indexing fragments…"))

        def done(nodes, _tag):
            pending.discard(nid)
            if self.cur_file is f:
                self.tag.model.insert_fragments(nid, nodes)
                cur = self.raw.hex.cursor
                if cur >= 0 and f.index.contains(nid, cur):
                    self._on_hex_cursor(cur)
            else:
                f.index.add_fragments(nid, nodes)
            self.statusBar().showMessage(self.tr("%n fragment(s)", "", len(nodes)), 3000)

        def failed(msg, _tag):
            pending.discard(nid)
            self.statusBar().showMessage(self.tr("Fragment indexing failed: {0}").format(tr_core(msg)), 5000)

        submit(self.pool, f.fragment_nodes, nid, tok, on_done=done, on_failed=failed)

    # ================= 영역 최대화 =================
    def _areas(self):
        return {"tag": self.tag, "raw": self.raw, "image": self.image}

    def toggle_maximize(self, name: str) -> None:
        if self.maximized == name:
            self.restore_maximize()
            return
        if self.maximized:
            self.restore_maximize()
        self._saved_sizes = (self.vsplit.sizes(), self.hsplit.sizes())
        if name == "tag":
            self.hsplit.hide()
        else:
            self.tag.hide()
            (self.image if name == "raw" else self.raw).hide()
        self.maximized = name
        self._areas()[name].toolbar.set_maximized(True)

    def restore_maximize(self) -> None:
        if not self.maximized:
            return
        self._areas()[self.maximized].toolbar.set_maximized(False)
        self.maximized = None
        for w in (self.tag, self.hsplit, self.raw, self.image):
            w.show()
        if self._saved_sizes:
            self.vsplit.setSizes(self._saved_sizes[0])
            self.hsplit.setSizes(self._saved_sizes[1])

    def _focused_area(self) -> str | None:
        w = QApplication.focusWidget()
        while w is not None:
            for name, panel in self._areas().items():
                if w is panel:
                    return name
            w = w.parentWidget()
        return None

    def toggle_maximize_focused(self) -> None:
        name = self._focused_area() or self.maximized
        if name:
            self.toggle_maximize(name)

    # ================= 단축키 동작 =================
    def escape(self) -> None:
        if self.maximized:
            self.restore_maximize()
            return
        if self.search_escape():
            return
        if self.batch and not self.batch.finished:
            self.cancel_batch()
            return
        self.cancel_file_job()

    def copy_focused(self) -> None:
        w = QApplication.focusWidget()
        if w is self.tag.tree:
            self.tag.copy_value()
        elif w is self.raw.hex:
            self.raw.hex.copy_selection()
        elif isinstance(w, QLineEdit):
            w.copy()
        elif w is not None and hasattr(w, "copy"):
            w.copy()

    def cycle_focus(self) -> None:
        order = [self.dock.current_tree(), self.tag.search_edit, self.tag.tree, self.raw.hex,
                 self.image_focus_widget()]
        order = [w for w in order if w is not None and w.isVisible() and w.isEnabled()]
        if not order:
            return
        cur = QApplication.focusWidget()
        i = next((k for k, w in enumerate(order) if w is cur or (cur is not None and w.isAncestorOf(cur))), -1)
        order[(i + 1) % len(order)].setFocus(Qt.FocusReason.TabFocusReason)

    # ================= 이미지 =================
    def image_focus_widget(self) -> QWidget | None:
        return self.image.view

    def _instance_label(self, f: DicomFile) -> tuple[str, str]:
        """(분류, 레벨 표기) — WSI 탭 분류 결과에서 찾는다."""
        for g in self.groups:
            for inst in g.instances:
                if inst.file is f:
                    return inst.category, inst.level_label
        return "", ""

    def show_image_for_file(self, f: DicomFile) -> None:
        gen = self.image_gen.next()
        self.image.show_message("")
        cat, label = self._instance_label(f)
        if cat == "VOLUME" and f.summary.frames >= 2:
            # 단독 VOLUME은 그 파일 하나로 슬라이드를 열어 레벨 하나만 표시한다 (자동 전환 없음)
            submit(self.pool, Slide.open, [f.path], tag=(gen, f, label),
                   on_done=self._on_file_slide, on_failed=self._on_image_failed)
            return
        if not f.summary.has_pixel_data:
            self.image.show_message(lambda: tr_core(MSG_NO_IMAGE))
            return
        submit(self.pool, decode_job, f.path, f.transfer_syntax, f.summary.has_pixel_data,
               tag=(gen, f), on_done=self._on_decoded, on_failed=self._on_image_failed)

    def _on_file_slide(self, slide, tag) -> None:
        gen, f, label = tag
        if not self.image_gen.is_current(gen):
            slide.close()
            return
        self.image.show_slide(slide, multi_level=False, label=label)

    def _on_decoded(self, result, tag) -> None:
        gen, f = tag
        if not self.image_gen.is_current(gen):
            return
        status, img, detail = result
        if status == OK:
            self.image.show_image(img)
        elif status == NO_IMAGE:
            self.image.show_message(lambda: tr_core(MSG_NO_IMAGE))
        else:
            self.image.show_message(lambda ts=f.transfer_syntax: tr_core(MSG_CANNOT_DISPLAY).format(ts_name(ts)),
                                    tr_core(detail))

    def _on_image_failed(self, msg: str, tag) -> None:
        gen, f = tag[0], tag[1]
        if self.image_gen.is_current(gen):
            ts = f.transfer_syntax if isinstance(f, DicomFile) else ""
            self.image.show_message(lambda t=ts: tr_core(MSG_CANNOT_DISPLAY).format(ts_name(t)), tr_core(msg))

    def show_image_for_group(self, g) -> None:
        gen = self.image_gen.next()
        self.image.show_message("")
        files = [i.file for i in g.instances]
        submit(self.pool, Slide.open, [f.path for f in files], tag=(gen, files[0] if files else None),
               on_done=self._on_group_slide, on_failed=self._on_image_failed)

    def _on_group_slide(self, slide, tag) -> None:
        if not self.image_gen.is_current(tag[0]):
            slide.close()
            return
        self.image.show_slide(slide, multi_level=True)

    def clear_image(self) -> None:
        self.image_gen.next()
        self.image.show_message("")

    def _on_tiles_pending(self, n: int) -> None:
        if n:
            self.statusBar().showMessage(self.tr("Reading tiles {0}").format(n))
            self._tile_msg = True
        elif getattr(self, "_tile_msg", False):
            self._tile_msg = False
            self.statusBar().clearMessage()

    # ================= 검색 =================
    def _init_search(self) -> None:
        self.search_gen = Generation()
        self.search_token: CancelToken | None = None
        self.matches: list[int] = []
        self.match_pos = -1
        self._has_query = False
        self.tag.searchRequested.connect(self.run_search)
        self.tag.stepRequested.connect(self.search_step)
        self.tag.show_only_chk.setChecked(str(self.settings.value(KEY_SHOW_ONLY, "false")).lower() == "true")
        self.tag.showOnlyToggled.connect(self._on_show_only)

    def _on_show_only(self, on: bool) -> None:
        self.settings.setValue(KEY_SHOW_ONLY, on)
        self._apply_filter()

    def _apply_filter(self) -> None:
        """Show only가 켜져 있고 검색 조건이 있으면 일치 노드와 상위 노드만 보인다 (SPEC-041)."""
        want = self.tag.show_only_chk.isChecked() and self._has_query and self.cur_kind == "file"
        if want or self.tag.model.filtering:
            self.tag.apply_filter(self.matches if want else None)

    def focus_search(self) -> None:
        self.tag.search_edit.setFocus()
        self.tag.search_edit.selectAll()

    def run_search(self, criteria: Criteria | None = None) -> None:
        c = criteria if criteria is not None else self.tag.criteria()
        comp = compile_criteria(c)
        self.tag.show_validation(comp.errors)
        if self.search_token is not None:
            self.search_token.cancel()  # 이전 검색 취소
        gen = self.search_gen.next()
        f = self.cur_file
        self._has_query = comp.active
        if f is None or not f.loaded or not comp.active or self.cur_kind != "file":
            self._set_matches([], gen)
            return
        tok = self.search_token = CancelToken()
        self.tag.count_label.setText(self.tr("Searching…"))
        submit(self.pool, search, f.index, f.formatter, comp, tok, tag=(gen, f),
               on_done=self._on_search_done, on_failed=self._on_search_failed)

    def _on_search_done(self, hits, tag) -> None:
        gen, f = tag
        if not self.search_gen.is_current(gen) or f is not self.cur_file:
            return  # 최신 세대 결과만 반영한다
        self._set_matches(hits, gen)
        if hits:
            self.search_step(1)

    def _on_search_failed(self, msg: str, tag) -> None:
        if self.search_gen.is_current(tag[0]) and not msg.startswith("Cancelled"):
            self.statusBar().showMessage(self.tr("Search failed: {0}").format(tr_core(msg)), 5000)

    def _set_matches(self, hits: list[int], gen: int) -> None:
        self.matches = hits
        self.match_pos = -1
        self.tag.model.set_matches(hits)
        self._apply_filter()
        self.tag.show_count(0, len(hits), self._has_query)

    def search_step(self, d: int) -> None:
        if self.tag.debounce.isActive():
            self.tag.debounce.stop()
            self.run_search()
            return
        if not self.matches:
            return
        n = len(self.matches)
        self.match_pos = (self.match_pos + d) % n if self.match_pos >= 0 else (0 if d > 0 else n - 1)
        self.tag.select_node(self.matches[self.match_pos])  # 상위 펼침 + RAW 동기화
        self.tag.show_count(self.match_pos + 1, n, True)

    def toggle_advanced(self) -> None:
        if self.tag.adv_btn.isEnabled():
            self.tag.adv_btn.toggle()
            if self.tag.adv_btn.isChecked():
                self.tag.adv["tag"].setFocus()

    def search_set_enabled(self, on: bool) -> None:
        for w in (self.tag.search_edit, self.tag.prev_btn, self.tag.next_btn, self.tag.show_only_chk,
                  self.tag.adv_btn, self.tag.adv_panel):
            w.setEnabled(on)
        # 비활성 명령은 리본 버튼도 비활성(ink-faint)이다 (5.3.3)
        for n in ("edit.find", "edit.advanced", "edit.find_prev", "edit.find_next", "edit.copy_tag", "edit.copy_row"):
            self.actions[n].setEnabled(on)
        if not on:
            self._set_matches([], self.search_gen.next())
            self.tag.count_label.setText("")

    def search_file_changed(self) -> None:
        if not self.tag.criteria().is_empty():
            self.run_search()
        else:
            self._set_matches([], self.search_gen.next())

    def search_reset(self) -> None:
        if self.search_token is not None:
            self.search_token.cancel()
        self._has_query = False
        self._set_matches([], self.search_gen.next())

    def search_escape(self) -> bool:
        """상세 패널 닫기 → 검색어 지우기 순서. 처리했으면 True."""
        if self.tag.adv_btn.isChecked():
            self.tag.adv_btn.setChecked(False)
            return True
        if self.tag.search_edit.text():
            self.tag.search_edit.clear()
            return True
        return False

    # ================= 드래그 앤 드롭 =================
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.overlay.adjustSize()
            r = self.vsplit.rect()
            sz = self.overlay.sizeHint()
            self.overlay.setGeometry(r.center().x() - sz.width() // 2, r.center().y() - sz.height() // 2,
                                     sz.width(), sz.height())
            self.overlay.raise_()
            self.overlay.show()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.overlay.hide()

    def dropEvent(self, e):
        self.overlay.hide()
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            e.acceptProposedAction()
            self.open_paths(paths)
