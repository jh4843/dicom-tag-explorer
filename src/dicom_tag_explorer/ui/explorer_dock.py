# 좌측 탐색 Dock. 파일/WSI/DICOMDIR 탭과 빈 상태 안내를 제공한다.
from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QDockWidget, QHeaderView, QLabel, QPushButton, QStackedWidget, QTabWidget,
    QTreeView, QVBoxLayout, QWidget,
)

from . import theme
from .common import install_ink_delegate
from .explorer_models import ROLE_KEY, ROLE_KIND, DicomdirModel, FilesModel, WsiModel
from .titlebar import enable_min_max_box

TAB_FILES, TAB_WSI, TAB_DICOMDIR = range(3)


class _EmptyPage(QWidget):
    """빈 상태 안내 + 선택 버튼. 문구는 retranslate()에서 다시 설정한다."""

    def __init__(self, on_click=None):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        lay.addWidget(self.label)
        self.button = QPushButton() if on_click else None
        if self.button is not None:
            self.button.clicked.connect(on_click)
            lay.addWidget(self.button, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(2)

    def set_texts(self, text: str, button: str = "") -> None:
        self.label.setText(text)
        if self.button is not None:
            self.button.setText(button)


class ExplorerDock(QDockWidget):
    nodeSelected = Signal(str, object)  # (kind, key)
    nodeActivated = Signal(str, object)
    openFilesRequested = Signal()
    openDicomdirRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ExplorerDock")
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable
                         | QDockWidget.DockWidgetFeature.DockWidgetFloatable
                         | QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.setMinimumWidth(200)
        self.restore_maximized = False  # 종료 때 최대화였으면 다음 Floating 표시에서 다시 최대화한다
        # Floating 창을 놓인 모니터에서 최소화·최대화할 수 있게 한다. Qt가 창 플래그를 정한 뒤에 적용한다
        self.topLevelChanged.connect(lambda floating: floating and QTimer.singleShot(0, self._apply_float_frame))
        self.files_model = FilesModel(self)
        self.wsi_model = WsiModel(self)
        self.dir_model = DicomdirModel(self)
        self._sync = False

        self.stack = QStackedWidget()
        self.start_page = _EmptyPage(self.openFilesRequested.emit)
        self.stack.addWidget(self.start_page)
        self.tabs = QTabWidget()
        self.trees: list[QTreeView] = []
        self.tab_stacks: list[QStackedWidget] = []
        self.wsi_empty = _EmptyPage()
        self.dir_empty = _EmptyPage(self.openDicomdirRequested.emit)
        empties = [None, self.wsi_empty, self.dir_empty]
        for i, model in enumerate((self.files_model, self.wsi_model, self.dir_model)):
            tree = QTreeView()
            tree.setModel(model)
            install_ink_delegate(tree)
            tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            tree.setUniformRowHeights(True)
            tree.setIndentation(18)
            tree.header().setStretchLastSection(True)
            tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
            # 사용자가 헤더 경계를 끌어 폭을 바꿀 수 있게 하고, 행이 늘거나 펼쳐질 때만 이름 컬럼을 내용에 맞춘다
            model.rowsInserted.connect(lambda *_a, t=tree: t.resizeColumnToContents(0))
            tree.expanded.connect(lambda _i, t=tree: t.resizeColumnToContents(0))
            # 마우스·키보드뿐 아니라 접근성 도구(UIA Select)의 선택 변경에도 반응하도록 selectionChanged를 쓴다
            tree.selectionModel().selectionChanged.connect(lambda sel, _d, t=tree: self._on_selection(t, sel))
            tree.activated.connect(self._on_activated)
            st = QStackedWidget()
            st.addWidget(tree)
            if empties[i] is not None:
                st.addWidget(empties[i])
            self.trees.append(tree)
            self.tab_stacks.append(st)
            self.tabs.addTab(st, "")
        self.stack.addWidget(self.tabs)
        self.setWidget(self.stack)
        self.refresh_empty()
        self.retranslate()

    def retranslate(self) -> None:
        self.setWindowTitle(self.tr("Explorer"))
        self.start_page.set_texts(self.tr("Open files or drag and drop them here."), self.tr("Open Files"))
        self.wsi_empty.set_texts(self.tr("No WSI image is open."))
        self.dir_empty.set_texts(self.tr("No DICOMDIR is open."), self.tr("Open DICOMDIR"))
        for i, t in enumerate((self.tr("Files"), "WSI", "DICOMDIR")):
            self.tabs.setTabText(i, t)
        for model in (self.files_model, self.wsi_model, self.dir_model):
            model.setHorizontalHeaderLabels([self.tr("Name"), self.tr("Info")])

    def _apply_float_frame(self) -> None:
        if self.isFloating() and self.isVisible():
            enable_min_max_box(int(self.winId()))
            theme.set_native_dark(self)
            if self.restore_maximized:
                self.restore_maximized = False
                self.showMaximized()

    def showEvent(self, e):
        super().showEvent(e)
        if self.isFloating():  # 재시작 시 Floating 상태로 복원된 경우
            QTimer.singleShot(0, self._apply_float_frame)

    def changeEvent(self, e):
        if e.type() == QEvent.Type.LanguageChange:
            self.retranslate()
        super().changeEvent(e)

    # ---- 상태 ----
    def refresh_empty(self) -> None:
        has_files = self.files_model.rowCount() > 0
        self.stack.setCurrentIndex(1 if has_files else 0)
        self.tab_stacks[TAB_WSI].setCurrentIndex(0 if self.wsi_model.groups else 1)
        self.tab_stacks[TAB_DICOMDIR].setCurrentIndex(0 if self.dir_model.roots else 1)

    def current_tree(self) -> QTreeView:
        return self.trees[self.tabs.currentIndex()]

    def model_for(self, tab: int):
        return (self.files_model, self.wsi_model, self.dir_model)[tab]

    # ---- 선택 ----
    def _on_selection(self, tree: QTreeView, selected) -> None:
        if self._sync or not selected.indexes():
            return
        idx0 = selected.indexes()[0].siblingAtColumn(0)
        self.nodeSelected.emit(idx0.data(ROLE_KIND), idx0.data(ROLE_KEY))

    def _on_activated(self, cur: QModelIndex) -> None:
        idx0 = cur.siblingAtColumn(0)
        self.nodeActivated.emit(idx0.data(ROLE_KIND), idx0.data(ROLE_KEY))

    def select_key(self, key, tab: int | None = None, emit: bool = False) -> bool:
        """해당 탭에서 key 노드를 선택한다. emit=False면 선택 신호를 보내지 않는다."""
        tab = self.tabs.currentIndex() if tab is None else tab
        model = self.model_for(tab)
        if tab == TAB_WSI and key in model.groups:
            item = model.groups[key]
        else:
            item = model.item_for(key)
        tree = self.trees[tab]
        if item is None:
            self._sync = True
            tree.selectionModel().clearSelection()
            self._sync = False
            return False
        idx = item.index()
        self._sync = not emit
        try:
            tree.setCurrentIndex(idx)
            tree.scrollTo(idx)
        finally:
            self._sync = False
        return True

    def select_index(self, tab: int, index: QModelIndex) -> None:
        self.trees[tab].setCurrentIndex(index)
