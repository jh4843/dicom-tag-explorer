# ElementIndex 노드 번호를 internalId로 쓰는 지연 생성 Tag Tree 모델.
from __future__ import annotations

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt, Signal


from ..core.dicom_file import DicomFile
from ..core.element_index import (
    F_SEQ, F_UNDEF, K_ERROR, K_ITEM, K_ITEM_DELIM, K_PREAMBLE, K_PREFIX, K_SEQ_DELIM,
)
from ..core.values import C_LEN, C_OFFSET, C_TAG, C_VALUE, COLUMNS
from . import theme
from .common import mono_font
from .icons import icon
from .theme import color

PSEUDO = (K_PREAMBLE, K_PREFIX, K_ITEM_DELIM, K_SEQ_DELIM)

MONO_COLS = {0, 1, 2, 3, 6}
N_COLS = len(COLUMNS)


class TagTreeModel(QAbstractItemModel):
    fragmentsRequested = Signal(int)  # Pixel Data 노드 번호
    matchesChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.file: DicomFile | None = None
        self.matches: set[int] = set()
        self._mono = mono_font()
        self._italic = theme.font("body")
        self._italic.setItalic(True)
        self._mono_italic = mono_font()
        self._mono_italic.setItalic(True)
        self._requested: set[int] = set()
        # Show only 필터 (SPEC-041). None이면 전체 목록. 켜지면 부모 → 보이는 자식, 노드 → 보이는 행
        self._kids: dict[int, list[int]] | None = None
        self._rows: dict[int, int] = {}

    def set_file(self, f: DicomFile | None) -> None:
        self.beginResetModel()
        self.file = f
        self.matches = set()
        self._requested = set()
        self._kids = None
        self._rows = {}
        self.endResetModel()

    @property
    def filtering(self) -> bool:
        return self._kids is not None

    def set_filter(self, matches) -> None:
        """matches가 None이면 전체 목록, 아니면 일치 노드와 그 상위 노드만 보인다 (SPEC-041).
        상위 집합은 색인의 parent를 따라 O(일치 수 × 깊이)로 만들고, 행 판정은 dict 조회 O(1)이다."""
        self.beginResetModel()
        if matches is None or self.idx is None:
            self._kids, self._rows = None, {}
        else:
            parent = self.idx.parent
            visible: set[int] = set()
            for m in matches:
                while m >= 0 and m not in visible:
                    visible.add(m)
                    m = parent[m]
            kids: dict[int, list[int]] = {}
            rows: dict[int, int] = {}
            for nid in sorted(visible):  # 노드 번호 = 파일 순서. Fragment(확장 노드)는 Pixel Data 아래에서만 형제다
                lst = kids.setdefault(parent[nid], [])
                rows[nid] = len(lst)
                lst.append(nid)
            self._kids, self._rows = kids, rows
        self.endResetModel()

    def is_visible(self, nid: int) -> bool:
        return self._kids is None or nid in self._rows

    def _children(self, nid: int) -> list[int]:
        if self._kids is None:
            return self.idx.children(nid)
        return self._kids.get(nid, [])

    def _row(self, nid: int) -> int:
        return self.idx.row[nid] if self._kids is None else self._rows[nid]

    @property
    def idx(self):
        return self.file.index if self.file is not None else None

    # ---- 구조 ----
    def _nid(self, index: QModelIndex) -> int:
        return index.internalId() if index.isValid() else -1

    # 필터 중(_kids)에는 expandAll이 보이는 노드마다 index·hasChildren·rowCount를 부른다(L0 일치 2만 건이면 약 8만 노드).
    # 그래서 이 세 메서드는 필터 경로를 dict 조회 한 번으로 먼저 처리한다 (TC-055)
    def index(self, row, column, parent=QModelIndex()):
        kmap = self._kids
        if kmap is not None:
            kids = kmap.get(parent.internalId() if parent.isValid() else -1)
            if kids is not None and 0 <= row < len(kids) and 0 <= column < N_COLS:
                return self.createIndex(row, column, kids[row])
            return QModelIndex()
        if self.idx is None:
            return QModelIndex()
        kids = self._children(self._nid(parent))
        if 0 <= row < len(kids) and 0 <= column < len(COLUMNS):
            return self.createIndex(row, column, kids[row])
        return QModelIndex()

    def parent(self, index=QModelIndex()):
        if not index.isValid() or self.idx is None:
            return QModelIndex()
        p = self.idx.parent[index.internalId()]
        if p < 0:
            return QModelIndex()
        return self.createIndex(self._row(p), 0, p)

    def rowCount(self, parent=QModelIndex()):
        kmap = self._kids
        if kmap is not None:
            if parent.column() > 0:
                return 0
            return len(kmap.get(parent.internalId() if parent.isValid() else -1, ()))
        if self.idx is None or parent.column() > 0:
            return 0
        return len(self._children(self._nid(parent)))

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def hasChildren(self, parent=QModelIndex()):
        kmap = self._kids
        if kmap is not None:
            return (parent.internalId() if parent.isValid() else -1) in kmap  # 목록은 비어 있지 않을 때만 둔다
        if self.idx is None:
            return False
        nid = self._nid(parent)
        if nid < 0:
            return len(self.idx) > 0
        return self.idx.has_children(nid)

    def canFetchMore(self, parent):
        nid = self._nid(parent)
        # 필터 중에는 Fragment 색인을 요청하지 않는다(일치하지 않은 Fragment는 어차피 보이지 않는다)
        return (self.idx is not None and self._kids is None and nid >= 0 and self.idx.needs_fragments(nid)
                and nid not in self._requested)

    def fetchMore(self, parent):
        nid = self._nid(parent)
        if nid >= 0 and nid not in self._requested:
            self._requested.add(nid)
            self.fragmentsRequested.emit(nid)

    def insert_fragments(self, pixel_node: int, nodes: list[tuple]) -> None:
        if self.idx is None or not self.idx.needs_fragments(pixel_node):
            return
        if self._kids is not None:
            self.idx.add_fragments(pixel_node, nodes)  # 새 Fragment는 일치 집합에 없으므로 보이는 행은 그대로다
            return
        parent = self.index_of(pixel_node)
        self.beginInsertRows(parent, 0, len(nodes) - 1)
        self.idx.add_fragments(pixel_node, nodes)
        self.endInsertRows()

    def index_of(self, nid: int, column: int = 0) -> QModelIndex:
        if self.idx is None or nid < 0 or not self.is_visible(nid):
            return QModelIndex()
        return self.createIndex(self._row(nid), column, nid)

    # ---- 데이터 ----
    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or self.file is None:
            return None
        nid = index.internalId()
        col = index.column()
        idx = self.idx
        if role == Qt.ItemDataRole.DisplayRole:
            return self.file.formatter.display(nid, col)
        if role == Qt.ItemDataRole.ToolTipRole:
            if col == C_LEN and idx.flags[nid] & F_UNDEF:
                return "0xFFFFFFFF"
            if col == C_VALUE:
                v = self.file.formatter.columns(nid)[C_VALUE]
                return v[:4096] + ("…" if len(v) > 4096 else "") if v else None
            return None
        if role == Qt.ItemDataRole.DecorationRole and col == C_TAG:
            if idx.kind[nid] == K_ITEM:
                return icon("item")
            if idx.flags[nid] & F_SEQ:
                return icon("sequence")
            return None
        if role == Qt.ItemDataRole.FontRole:
            italic = idx.kind[nid] in PSEUDO  # 의사 노드는 기울임체 (TagTree README)
            if col in MONO_COLS:
                return self._mono_italic if italic else self._mono
            return self._italic if italic else None
        if role == Qt.ItemDataRole.ForegroundRole:
            if nid in self.matches:
                return color("ink")  # 검색 일치 바탕 위 글자
            k = idx.kind[nid]
            if k == K_ERROR:
                return color("danger")
            if k in PSEUDO or col == C_OFFSET:
                return color("ink-muted")  # 의사 노드·Offset은 ink-muted (선택되면 delegate가 ink로 바꾼다)
            return None
        if role == Qt.ItemDataRole.BackgroundRole:
            return color("search-match") if nid in self.matches else None
        if role == Qt.ItemDataRole.TextAlignmentRole and col == C_LEN:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def set_matches(self, matches) -> None:
        self.matches = set(matches)
        self.matchesChanged.emit()  # 뷰가 viewport를 다시 그린다
