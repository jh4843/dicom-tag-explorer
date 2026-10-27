# 요소 노드를 컬럼형 배열로 보관하고 바이트 오프셋 → 노드 역매핑을 제공하는 색인.
from __future__ import annotations

from array import array
from bisect import bisect_right

# 노드 종류
K_PREAMBLE = 0
K_PREFIX = 1  # 'DICM'
K_ELEMENT = 2
K_ITEM = 3
K_ITEM_DELIM = 4
K_SEQ_DELIM = 5
K_BOT = 6
K_FRAGMENT = 7
K_ERROR = 8

# 플래그
F_UNDEF = 1  # Undefined Length (0xFFFFFFFF)
F_ENCAP = 2  # Encapsulated Pixel Data (Fragment 지연 색인 대상)
F_VIRTUAL = 4  # Deflate 본문. start는 가상 오프셋이고 원본 파일 위치가 없다
F_SEQ = 8  # Sequence로 해석한 요소 (SQ, Undefined Length UN 등)
F_IMPLICIT = 16  # 이 노드는 Implicit VR로 인코딩되어 있다
F_BIG = 32  # 이 노드는 Big Endian으로 인코딩되어 있다

TAG_ITEM = 0xFFFEE000
TAG_ITEM_DELIM = 0xFFFEE00D
TAG_SEQ_DELIM = 0xFFFEE0DD
TAG_PIXEL_DATA = 0x7FE00010


def vr_code(vr: str) -> int:
    if not vr:
        return 0
    return (ord(vr[0]) << 8) | ord(vr[1])


def vr_str(code: int) -> str:
    if not code:
        return ""
    return chr(code >> 8) + chr(code & 0xFF)


class ElementIndex:
    """전위 순회 순서의 노드 색인.

    본 노드(0 .. n_main-1)는 파일 순서로 정렬되어 있다. Fragment 노드는 나중에 확장 노드로
    배열 끝에 덧붙이며, 기존 노드 번호는 바뀌지 않는다.
    """

    def __init__(self, file_size: int):
        self.file_size = file_size
        self.start = array("q")
        self.header_len = array("h")
        self.total_len = array("q")
        self.parent = array("i")
        self.subtree_end = array("i")
        self.tag = array("I")
        self.vr = array("H")
        self.kind = array("B")
        self.flags = array("B")
        self.row = array("i")
        self.length = array("q")  # 헤더에 기록된 값 길이 (Undefined면 -1)
        self.n_main = 0
        self.ext: dict[int, tuple[int, int]] = {}  # pixel 노드 → (첫 확장 id, 개수)
        self._children: dict[int, list[int]] = {}
        self.error: str | None = None
        self.virtual_base: int | None = None  # Deflate 본문 가상 오프셋 시작

    # ---- 생성 ----
    def append(self, start, header_len, total_len, parent, tag, vr, kind, flags, row, length) -> int:
        nid = len(self.start)
        self.start.append(start)
        self.header_len.append(header_len)
        self.total_len.append(total_len)
        self.parent.append(parent)
        self.subtree_end.append(nid + 1)
        self.tag.append(tag)
        self.vr.append(vr)
        self.kind.append(kind)
        self.flags.append(flags)
        self.row.append(row)
        self.length.append(length)
        return nid

    def finish(self) -> None:
        self.n_main = len(self.start)

    def add_fragments(self, pixel_node: int, nodes: list[tuple]) -> None:
        """nodes: (start, header_len, total_len, tag, kind, length) 목록. UI 스레드에서 호출한다."""
        if pixel_node in self.ext or not nodes:
            return
        first = len(self.start)
        fl = self.flags[pixel_node] & F_VIRTUAL
        for r, (start, hl, tl, tag, kind, length) in enumerate(nodes):
            self.append(start, hl, tl, pixel_node, tag, 0, kind, fl, r, length)
        self.ext[pixel_node] = (first, len(nodes))
        self._children.pop(pixel_node, None)

    # ---- 조회 ----
    def __len__(self) -> int:
        return len(self.start)

    def is_virtual(self, nid: int) -> bool:
        return bool(self.flags[nid] & F_VIRTUAL)

    def needs_fragments(self, nid: int) -> bool:
        return bool(self.flags[nid] & F_ENCAP) and nid not in self.ext

    def children(self, nid: int) -> list[int]:
        """nid = -1이면 최상위 노드 목록."""
        c = self._children.get(nid)
        if c is not None:
            return c
        if nid in self.ext:
            first, count = self.ext[nid]
            c = list(range(first, first + count))
        elif nid >= self.n_main and nid >= 0:
            c = []
        else:
            c = []
            i = nid + 1
            end = self.subtree_end[nid] if nid >= 0 else self.n_main
            se = self.subtree_end
            while i < end:
                c.append(i)
                i = se[i]
        self._children[nid] = c
        return c

    def has_children(self, nid: int) -> bool:
        if nid in self.ext:
            return True
        if self.flags[nid] & F_ENCAP:
            return True
        return nid < self.n_main and self.subtree_end[nid] > nid + 1

    def depth_path(self, nid: int) -> list[int]:
        """루트부터 nid까지의 조상 목록 (nid 포함)."""
        path = []
        while nid >= 0:
            path.append(nid)
            nid = self.parent[nid]
        path.reverse()
        return path

    def contains(self, nid: int, offset: int) -> bool:
        s = self.start[nid]
        return s <= offset < s + self.total_len[nid]

    def find(self, offset: int) -> int | None:
        """오프셋을 포함하는 가장 깊은 노드. 없으면 None. O(log n + depth)."""
        if offset < 0 or offset >= self.file_size:
            return None
        if self.virtual_base is not None and offset >= self.virtual_base:
            return None
        i = bisect_right(self.start, offset, 0, self.n_main) - 1
        while i >= 0 and not self.contains(i, offset):
            i = self.parent[i]
        if i < 0:
            return None
        ext = self.ext.get(i)
        if ext:
            first, count = ext
            j = bisect_right(self.start, offset, first, first + count) - 1
            if j >= first and self.contains(j, offset):
                return j
        return i

    def find_child(self, parent: int, tag: int) -> int | None:
        for c in self.children(parent):
            if self.tag[c] == tag and self.kind[c] == K_ELEMENT:
                return c
        return None

    def find_path(self, tags: list[int], parent: int = -1) -> int | None:
        """tags 경로를 따라 내려간다. Sequence는 첫 Item으로 들어간다."""
        node = parent
        for k, t in enumerate(tags):
            if node >= 0 and self.flags[node] & F_SEQ:
                items = [c for c in self.children(node) if self.kind[c] == K_ITEM]
                if not items:
                    return None
                node = items[0]
            c = self.find_child(node, t)
            if c is None:
                return None
            node = c
        return node
