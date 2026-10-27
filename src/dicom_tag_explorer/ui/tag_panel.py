# Tag 영역. 검색 바 + 상세 검색 패널 + Tag Tree / WSI 요약표 / 안내 페이지 스택.
from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFontMetrics, QGuiApplication, QKeySequence, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMenu, QProgressBar, QPushButton, QStackedWidget, QTableView, QToolButton, QTreeView,
    QVBoxLayout, QWidget,
)

from ..core.classify import WsiGroup, size_text
from ..core.search import STANDARD_VRS, Criteria
from ..core.values import C_TAG, C_VALUE
from . import theme
from .common import AreaToolbar, install_ink_delegate, mono_font, tr_core
from .icons import icon
from .tag_tree_model import TagTreeModel

PAGE_MSG, PAGE_LOADING, PAGE_TREE, PAGE_WSI = range(4)
WSI_COLS = ("Type", "Level", "Size", "Tile", "Frames", "Transfer Syntax", "File")
MONO_FIELDS = ("tag", "vr", "vm", "length", "offset")


def _repolish(w) -> None:
    w.style().unpolish(w)
    w.style().polish(w)


class TagTreeView(QTreeView):
    copyRequested = Signal()

    def keyPressEvent(self, e):
        if e.matches(QKeySequence.StandardKey.Copy):
            self.copyRequested.emit()
            return
        super().keyPressEvent(e)


class TagPanel(QWidget):
    nodeSelected = Signal(int)  # Tag Tree 현재 노드 (-1 = 없음)
    searchRequested = Signal(object)  # Criteria (300 ms debounce 후)
    stepRequested = Signal(int)  # +1 다음, -1 이전
    instanceRequested = Signal(object)  # WSI 요약표 → 파일 key
    cancelRequested = Signal()
    showOnlyToggled = Signal(bool)  # Show only 체크박스 (SPEC-041)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.reg = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 검색 바 (우측 정렬, SearchField README)
        self.toolbar = AreaToolbar(edge_right=True)
        tb = self.toolbar.lay
        tb.addStretch(1)
        self.search_edit = QLineEdit()
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedSize(300, 24)
        self.prev_btn = QToolButton()
        self.next_btn = QToolButton()
        self.count_label = QLabel("")
        self.count_label.setProperty("role", "muted")
        self.count_label.setFont(mono_font("mono-sm"))
        self.count_label.setMinimumWidth(80)
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.show_only_chk = QCheckBox()  # 결과 수와 상세 사이 (SPEC-041, SearchField README)
        self.adv_btn = QToolButton()
        self.adv_btn.setCheckable(True)
        self.adv_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        for b in (self.prev_btn, self.next_btn, self.adv_btn):
            b.setIconSize(QSize(theme.px("size-icon-sm"), theme.px("size-icon-sm")))
        for w in (self.search_edit, self.prev_btn, self.next_btn, self.count_label, self.show_only_chk, self.adv_btn):
            tb.addWidget(w)
        self.toolbar.finish()
        lay.addWidget(self.toolbar)

        # 상세 검색 패널 (UI-03). 기본 숨김
        self.adv_panel = QFrame()
        self.adv_panel.setProperty("role", "header")
        g = QGridLayout(self.adv_panel)
        g.setContentsMargins(theme.px("space-4"), theme.px("space-2"), theme.px("space-4"), theme.px("space-2"))
        g.setHorizontalSpacing(theme.px("space-4"))
        self.adv: dict[str, QLineEdit] = {}

        def field(label, key, r, c, span=1):
            g.addWidget(QLabel(label), r, c * 2)
            e = QLineEdit()
            e.setClearButtonEnabled(True)
            g.addWidget(e, r, c * 2 + 1, 1, span)
            self.adv[key] = e
            return e

        field("TAG", "tag", 0, 0).setPlaceholderText("0010,0010")
        g.addWidget(QLabel("VR"), 0, 2)
        self.vr_combo = QComboBox()
        self.vr_combo.setEditable(True)
        self.vr_combo.addItems([""] + list(STANDARD_VRS))
        self.vr_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        g.addWidget(self.vr_combo, 0, 3)
        self.adv["vr"] = self.vr_combo.lineEdit()
        field("VM", "vm", 0, 2)
        field("Name", "name", 1, 0)
        field("Length", "length", 1, 1)
        field("Offset", "offset", 1, 2).setPlaceholderText("0x")
        field("Value", "value", 2, 0, 5)
        for k in MONO_FIELDS:
            (self.vr_combo if k == "vr" else self.adv[k]).setFont(mono_font())
        opts = QHBoxLayout()
        opts.setSpacing(theme.px("space-4"))  # 체크 상자가 앞 체크박스 글자에 붙지 않게 그리드 가로 간격과 맞춘다
        self.case_chk = QCheckBox()
        self.regex_chk = QCheckBox()
        self.clear_btn = QPushButton()
        self.clear_btn.clicked.connect(self.clear_advanced)
        opts.addWidget(self.case_chk)
        opts.addWidget(self.regex_chk)
        opts.addStretch(1)
        opts.addWidget(self.clear_btn)
        g.addLayout(opts, 3, 0, 1, 6)
        self.adv_panel.hide()
        lay.addWidget(self.adv_panel)

        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(300)
        self.debounce.timeout.connect(lambda: self.searchRequested.emit(self.criteria()))
        self.search_edit.textChanged.connect(self._changed)
        for e in self.adv.values():
            e.textChanged.connect(self._changed)
        self.case_chk.toggled.connect(self._changed)
        self.regex_chk.toggled.connect(self._changed)
        # 접힌 패널의 조건은 적용하지 않는다(값은 유지). 펼치면 다시 적용한다 (D-06, TC-053)
        self.adv_btn.toggled.connect(self.adv_panel.setVisible)
        self.adv_btn.toggled.connect(self._changed)
        self.search_edit.installEventFilter(self)
        self.show_only_chk.toggled.connect(self.showOnlyToggled.emit)
        self.prev_btn.clicked.connect(lambda: self.stepRequested.emit(-1))
        self.next_btn.clicked.connect(lambda: self.stepRequested.emit(1))

        self.stack = QStackedWidget()
        self.msg = QLabel("")
        self.msg.setProperty("role", "page")
        self.msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg.setWordWrap(True)
        self._msg_fn = lambda: ""
        self.stack.addWidget(self.msg)

        loading = QFrame()
        loading.setProperty("role", "panel")
        ll = QVBoxLayout(loading)
        ll.addStretch(1)
        self.loading_label = QLabel()
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ll.addWidget(self.loading_label)
        bar = QProgressBar()
        bar.setRange(0, 0)
        bar.setMaximumWidth(240)
        ll.addWidget(bar, 0, Qt.AlignmentFlag.AlignHCenter)
        self.loading_cancel = QPushButton()
        self.loading_cancel.clicked.connect(self.cancelRequested.emit)
        ll.addWidget(self.loading_cancel, 0, Qt.AlignmentFlag.AlignHCenter)
        ll.addStretch(2)
        self.stack.addWidget(loading)

        self.model = TagTreeModel(self)
        self.tree = TagTreeView()
        self.tree.setModel(self.model)
        install_ink_delegate(self.tree)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(False)  # 교대 행 색은 쓰지 않는다 (TagTree README)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.selectionModel().currentChanged.connect(self._on_current)
        self.tree.copyRequested.connect(self.copy_value)
        self.model.matchesChanged.connect(self.tree.viewport().update)
        self._widths: list[int] | None = None  # 사용자가 바꾼 폭. 파일을 바꿔도 유지한다
        self.model.modelAboutToBeReset.connect(self._save_widths)
        self.model.modelReset.connect(self._set_widths)
        self.stack.addWidget(self.tree)

        wsi = QFrame()
        wsi.setProperty("role", "panel")
        wl = QVBoxLayout(wsi)
        wl.setContentsMargins(theme.px("space-3"), theme.px("space-2"), theme.px("space-3"), theme.px("space-2"))
        self.wsi_title = QLabel()
        self.wsi_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        wl.addWidget(self.wsi_title)
        self.wsi_model = QStandardItemModel(0, len(WSI_COLS), self)
        self.wsi_model.setHorizontalHeaderLabels(list(WSI_COLS))
        self.wsi_table = QTableView()
        self.wsi_table.setModel(self.wsi_model)
        install_ink_delegate(self.wsi_table)
        self.wsi_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.wsi_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.wsi_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.wsi_table.verticalHeader().hide()
        self.wsi_table.horizontalHeader().setStretchLastSection(True)
        self.wsi_table.doubleClicked.connect(self._wsi_activate)
        self.wsi_table.activated.connect(self._wsi_activate)
        wl.addWidget(self.wsi_table)
        self.stack.addWidget(wsi)
        lay.addWidget(self.stack, 1)
        self._guard = False
        self._errors: dict = {}
        self._zero = False
        theme.notifier().changed.connect(self.apply_theme)
        self.apply_theme()
        self.retranslate()

    def set_registry(self, reg) -> None:
        """우클릭 메뉴의 복사 명령은 레지스트리 명령이다 (리본 편집 탭과 같다)."""
        self.reg = reg

    # ---- 번역·테마 ----
    def retranslate(self) -> None:
        self.search_edit.setPlaceholderText(self.tr("Search all columns…"))
        self.search_edit.setAccessibleName(self.tr("Search all columns"))
        self.prev_btn.setToolTip(self.tr("Previous (Shift+F3)"))
        self.next_btn.setToolTip(self.tr("Next (F3)"))
        self.show_only_chk.setText(self.tr("Show only"))
        self.show_only_chk.setToolTip(self.tr("Show only matching items"))
        self.adv_btn.setText(self.tr("Advanced"))
        self.adv_btn.setToolTip(self.tr("Advanced search (Ctrl+Shift+F)"))
        self.case_chk.setText(self.tr("Match case"))
        self.regex_chk.setText(self.tr("Regex"))
        self.clear_btn.setText(self.tr("Clear"))
        self.loading_label.setText(self.tr("Reading…"))
        self.loading_cancel.setText(self.tr("Cancel"))
        self.msg.setText(self._msg_fn())
        self.show_validation(self._errors)

    def changeEvent(self, e):
        if e.type() == QEvent.Type.LanguageChange:
            self.retranslate()
        super().changeEvent(e)

    def apply_theme(self, *_) -> None:
        self.prev_btn.setIcon(icon("prev"))
        self.next_btn.setIcon(icon("next"))
        self.adv_btn.setIcon(icon("search-advanced"))
        self.tree.viewport().update()

    # ---- 검색 ----
    def _changed(self, *_):
        self.debounce.start()

    def criteria(self) -> Criteria:
        a = {k: e.text() for k, e in self.adv.items()} if self.adv_btn.isChecked() else {}
        return Criteria(text=self.search_edit.text(), match_case=self.case_chk.isChecked(),
                        regex=self.regex_chk.isChecked(), **a)

    def show_validation(self, errors: dict) -> None:
        """형식이 틀린 필드는 danger 테두리와 형식 안내 툴팁. 검색에서는 제외된다."""
        self._errors = errors
        for k, e in self.adv.items():
            w = self.vr_combo if k == "vr" else e
            w.setProperty("invalid", k in errors)
            _repolish(w)
            w.setToolTip(tr_core(errors.get(k, "")))
        self.search_edit.setProperty("invalid", "text" in errors)
        self.search_edit.setToolTip(tr_core(errors.get("text", "")))
        _repolish(self.search_edit)

    def show_count(self, pos: int, total: int, has_query: bool) -> None:
        self.count_label.setText(f"{pos} / {total}" if has_query else "")
        self._zero = has_query and total == 0
        # 0건: 입력창 danger-bg + danger 테두리, 결과 수 danger (SearchField README)
        self.search_edit.setProperty("zero", self._zero)
        self.count_label.setProperty("role", "danger" if self._zero else "muted")
        _repolish(self.search_edit)
        _repolish(self.count_label)

    def clear_advanced(self) -> None:
        for e in self.adv.values():
            e.clear()

    def eventFilter(self, obj, e):
        if obj is self.search_edit and e.type() == QEvent.Type.KeyPress and e.key() in (
                Qt.Key.Key_Return, Qt.Key.Key_Enter):
            shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self.debounce.stop()
            self.stepRequested.emit(-1 if shift else 1)
            return True
        return super().eventFilter(obj, e)

    # ---- 페이지 ----
    def show_message(self, text) -> None:
        """text는 문자열 또는 번역 문자열을 돌려주는 함수(언어가 바뀌면 다시 부른다)."""
        self.model.set_file(None)
        self._msg_fn = text if callable(text) else (lambda t=text: t)
        self.msg.setText(self._msg_fn())
        self.stack.setCurrentIndex(PAGE_MSG)

    def show_loading(self) -> None:
        self.stack.setCurrentIndex(PAGE_LOADING)

    def show_file(self, f) -> None:
        self.model.set_file(f)
        self.stack.setCurrentIndex(PAGE_TREE)

    def _save_widths(self) -> None:
        h = self.tree.header()
        if self._widths is not None and h.count() == len(self._widths):
            self._widths = [h.sectionSize(i) for i in range(h.count())]

    def _set_widths(self) -> None:
        h = self.tree.header()
        if self._widths is None:
            fm = QFontMetrics(theme.font("body"))
            mf = QFontMetrics(mono_font())
            self._widths = [mf.horizontalAdvance("0") * 22, mf.horizontalAdvance("0") * 4,
                            mf.horizontalAdvance("0") * 5, mf.horizontalAdvance("0") * 9,
                            fm.horizontalAdvance("M") * 16, fm.horizontalAdvance("M") * 22,
                            mf.horizontalAdvance("0") * 11]
        for i, w in enumerate(self._widths):
            h.resizeSection(i, w)
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

    def show_wsi(self, g: WsiGroup, ts_name) -> None:
        self.model.set_file(None)
        self.wsi_title.setText(f"WSI: {g.name}\nStudy UID {g.study_uid}   Series UID {g.series_uid}")
        self.wsi_model.removeRows(0, self.wsi_model.rowCount())
        for inst in g.instances:
            s = inst.file.summary
            tile = f"{s.cols}x{s.rows}" if inst.category == "VOLUME" and s.cols else "-"
            vals = [inst.kind, inst.level_label, size_text(inst.size), tile, str(s.frames),
                    ts_name(inst.file), inst.file.path.name]
            row = []
            for v in vals:
                it = QStandardItem(v)
                it.setData(inst.file.key, Qt.ItemDataRole.UserRole)
                row.append(it)
            row[-1].setToolTip(str(inst.file.path))
            self.wsi_model.appendRow(row)
        self.wsi_table.resizeColumnsToContents()
        self.stack.setCurrentIndex(PAGE_WSI)

    def _wsi_activate(self, index: QModelIndex) -> None:
        key = index.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
        if key is not None:
            self.instanceRequested.emit(key)

    # ---- Tree ----
    def _on_current(self, cur: QModelIndex, prev: QModelIndex) -> None:
        if self._guard:
            return
        self.nodeSelected.emit(cur.internalId() if cur.isValid() else -1)

    def apply_filter(self, matches) -> None:
        """Show only (SPEC-041). matches가 None이면 전체 목록. 선택 노드가 계속 보이면 선택과 컬럼 폭을 유지한다."""
        cur = self.current_node()
        h = self.tree.header()
        widths = [h.sectionSize(i) for i in range(h.count())]
        self._guard = True  # 모델 리셋으로 선택이 풀려도 RAW 동기화를 다시 하지 않는다
        try:
            self.model.set_filter(matches)
        finally:
            self._guard = False
        for i, w in enumerate(widths):
            h.resizeSection(i, w)
        if self.model.filtering:
            self.tree.expandAll()  # 필터 중 자식이 있는 노드는 모두 일치 노드의 상위 노드이다
        if cur >= 0 and self.model.is_visible(cur):
            self.select_node(cur, emit=False)

    def current_node(self) -> int:
        cur = self.tree.currentIndex()
        return cur.internalId() if cur.isValid() else -1

    def select_node(self, nid: int, emit: bool = True) -> bool:
        """상위 노드를 펼치고 선택한다. Show only로 숨겨진 노드면 선택을 바꾸지 않고 False."""
        idx = self.model.idx
        if idx is None or nid < 0 or not self.model.is_visible(nid):
            return False
        for a in idx.depth_path(nid)[:-1]:
            self.tree.expand(self.model.index_of(a))
        mi = self.model.index_of(nid)
        self._guard = not emit
        try:
            self.tree.setCurrentIndex(mi)
            self.tree.scrollTo(mi)
        finally:
            self._guard = False
        return True

    def _columns(self):
        nid = self.current_node()
        if nid >= 0 and self.model.file is not None:
            return self.model.file.formatter.columns(nid)
        return None

    def copy_value(self) -> None:
        cols = self._columns()
        if cols:
            QGuiApplication.clipboard().setText(cols[C_VALUE])

    def copy_tag(self) -> None:
        cols = self._columns()
        if cols:
            QGuiApplication.clipboard().setText(cols[C_TAG])

    def copy_row(self) -> None:
        cols = self._columns()
        if cols:
            QGuiApplication.clipboard().setText("\t".join(cols))

    def _context_menu(self, pos) -> None:
        mi = self.tree.indexAt(pos)
        if not mi.isValid() or self.model.file is None:
            return
        self.tree.setCurrentIndex(mi.siblingAtColumn(0))
        m = QMenu(self)
        if self.reg is not None:
            m.addAction(self.reg["edit.copy_tag"])
            m.addAction(self.tr("Copy Value"), self.copy_value)  # edit.copy(Ctrl+C)와 같은 동작
            m.addAction(self.reg["edit.copy_row"])
        m.addSeparator()
        m.addAction(self.tr("Expand All Below"), lambda: self.tree.expandRecursively(mi.siblingAtColumn(0)))
        m.addAction(self.tr("Collapse All"), self.tree.collapseAll)
        m.exec(self.tree.viewport().mapToGlobal(pos))
