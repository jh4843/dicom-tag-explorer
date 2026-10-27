# 색인 노드를 TAG/VR/VM/Length/Name/Value/Offset 표시 문자열로 바꾼다 (값 해석은 pydicom).
from __future__ import annotations

import threading
from typing import Callable

from pydicom import charset, datadict
from pydicom.dataelem import RawDataElement, convert_raw_data_element
from pydicom.multival import MultiValue
from pydicom.tag import BaseTag

from .element_index import (
    F_BIG, F_ENCAP, F_IMPLICIT, F_SEQ, F_UNDEF, F_VIRTUAL,
    K_BOT, K_ERROR, K_FRAGMENT, K_ITEM, K_ITEM_DELIM, K_PREAMBLE, K_PREFIX, K_SEQ_DELIM,
    TAG_PIXEL_DATA, ElementIndex, vr_str,
)

COLUMNS = ("TAG", "VR", "VM", "Length", "Name", "Value", "Offset")
C_TAG, C_VR, C_VM, C_LEN, C_NAME, C_VALUE, C_OFFSET = range(7)
DISPLAY_MAX = 256
READ_MAX = 1 << 20  # 텍스트 값 해석 상한 (1 MiB)
BINARY_VRS = {"OB", "OD", "OF", "OL", "OV", "OW", "UN"}
TAG_CHARSET = 0x00080005
TAG_NUMBER_OF_FRAMES = 0x00280008
CACHE_MAX = 20000


def format_offset(offset: int, file_size: int) -> str:
    """파일 크기가 0xFFFFFFFF 이하면 8자리, 넘으면 10자리 대문자 hex (L-01)."""
    width = 10 if file_size > 0xFFFFFFFF else 8
    return f"{offset:0{width}X}"


def format_tag(tag: int) -> str:
    return f"({tag >> 16:04X},{tag & 0xFFFF:04X})"


def truncate(s: str, n: int = DISPLAY_MAX) -> str:
    return s if len(s) <= n else s[:n] + "…"


def _fmt_scalar(v) -> str:
    if isinstance(v, BaseTag):
        return format_tag(int(v))
    if isinstance(v, bytes):
        return v.decode("latin-1")
    return str(v)


class ValueFormatter:
    """한 파일의 노드 표시 문자열을 만든다. read(pos, n)은 (가상) 오프셋 기준 읽기 함수."""

    def __init__(self, index: ElementIndex, read: Callable[[int, int], bytes]):
        self.idx = index
        self.read = read
        self._cache: dict[int, tuple] = {}
        self._enc_cache: dict[int, list[str]] = {}
        self._lock = threading.Lock()
        self._nframes: int | None = None

    # ---- 보조 ----
    def _dataset_parent(self, nid: int) -> int:
        return self.idx.parent[nid]

    def encodings(self, nid: int) -> list[str]:
        """가장 가까운 데이터셋의 Specific Character Set. 없으면 상위로 올라간다."""
        p = self._dataset_parent(nid)
        chain = []
        enc = None
        while True:
            if p in self._enc_cache:
                enc = self._enc_cache[p]
                break
            chain.append(p)
            c = self.idx.find_child(p, TAG_CHARSET)
            if c is not None:
                el = self._element(c, None)
                v = el.value if el is not None else None
                if v:
                    vals = list(v) if isinstance(v, MultiValue) else [v]
                    enc = charset.convert_encodings([str(x) for x in vals])
                    break
            if p < 0:
                enc = ["iso8859"]
                break
            # Item → Sequence → 상위 데이터셋
            q = self.idx.parent[p]
            p = self.idx.parent[q] if q >= 0 else -1
        for c in chain:
            self._enc_cache[c] = enc
        return enc

    def private_creator(self, nid: int) -> str | None:
        tag = self.idx.tag[nid]
        group, elem = tag >> 16, tag & 0xFFFF
        if not (group & 1) or elem < 0x1000:
            return None
        ctag = (group << 16) | (elem >> 8)
        c = self.idx.find_child(self.idx.parent[nid], ctag)
        if c is None:
            return None
        raw = self.read(self.idx.start[c] + self.idx.header_len[c], max(0, self.idx.length[c]))
        return raw.decode("latin-1").strip(" \0") or None

    def _element(self, nid: int, encodings, max_len: int = READ_MAX):
        idx = self.idx
        vr = vr_str(idx.vr[nid])
        ln = idx.length[nid]
        if ln < 0 or vr == "SQ":
            return None
        ln_read = min(ln, max_len)
        data = self.read(idx.start[nid] + idx.header_len[nid], ln_read)
        fl = idx.flags[nid]
        raw = RawDataElement(BaseTag(idx.tag[nid]), vr, len(data), data, idx.start[nid],
                             bool(fl & F_IMPLICIT), not (fl & F_BIG), True, False)
        try:
            return convert_raw_data_element(raw, encoding=encodings)
        except Exception:
            return None

    def element(self, nid: int):
        """pydicom DataElement (SQ·Undefined Length는 None)."""
        return self._element(nid, self.encodings(nid))

    def number_of_frames(self) -> int:
        if self._nframes is None:
            n = 1
            c = self.idx.find_child(-1, TAG_NUMBER_OF_FRAMES)
            if c is not None:
                el = self._element(c, None)
                try:
                    n = int(el.value) if el is not None and el.value not in (None, "") else 1
                except (TypeError, ValueError):
                    n = 1
            self._nframes = n
        return self._nframes

    def item_number(self, nid: int) -> int:
        """같은 Sequence 안에서 몇 번째 Item인지 (1부터). Item이 Delimiter보다 앞에 오므로 row + 1이다."""
        return self.idx.row[nid] + 1

    # ---- 컬럼 ----
    def columns(self, nid: int) -> tuple:
        """(TAG, VR, VM, Length, Name, Value 전체, Offset)."""
        c = self._cache.get(nid)
        if c is not None:
            return c
        c = self._compute(nid)
        with self._lock:
            if len(self._cache) >= CACHE_MAX:
                self._cache.clear()
            self._cache[nid] = c
        return c

    def compute(self, nid: int) -> tuple:
        """캐시를 채우지 않는 계산 (검색용). 화면 캐시가 검색으로 밀려나지 않게 한다."""
        c = self._cache.get(nid)
        return c if c is not None else self._compute(nid)

    def display(self, nid: int, col: int) -> str:
        v = self.columns(nid)[col]
        return truncate(v) if col == C_VALUE else v

    def _compute(self, nid: int) -> tuple:
        idx = self.idx
        kind = idx.kind[nid]
        fl = idx.flags[nid]
        start = idx.start[nid]
        off = "-" if fl & F_VIRTUAL else format_offset(start, idx.file_size)
        ln = idx.length[nid]
        length = "Undef." if (fl & F_UNDEF) else str(ln)
        if kind == K_PREAMBLE:
            return ("Preamble", "", "", "128", "File Preamble", _hex(self.read(0, 16), 128), off)
        if kind == K_PREFIX:
            return ("DICM", "", "", "4", "DICM Prefix", "DICM", off)
        if kind == K_ITEM:
            return (f"Item #{self.item_number(nid)}", "", "", length, "Item", "", off)
        if kind == K_ITEM_DELIM:
            return ("Item Delim.", "", "", str(ln), "ItemDelimitationItem", "", off)
        if kind == K_SEQ_DELIM:
            return ("Seq. Delim.", "", "", str(ln), "SequenceDelimitationItem", "", off)
        if kind == K_BOT:
            v = "<empty>" if ln == 0 else f"<Basic Offset Table {ln // 4} entries>"
            return ("Basic Offset Table", "", "", str(ln), "Item", v, off)
        if kind == K_FRAGMENT:
            return (f"Fragment #{idx.row[nid]}", "", "", str(ln), "Item", f"<Fragment {ln} bytes>", off)
        if kind == K_ERROR:
            return (f"<Parse stopped: {idx.error}>", "", "", "", "", "", off)
        tag = idx.tag[nid]
        vr = vr_str(idx.vr[nid])
        name = self._name(nid, tag)
        if tag == TAG_PIXEL_DATA and not (fl & F_SEQ):
            if fl & F_ENCAP:
                v = f"<Encapsulated {self.number_of_frames()} frames>"
            else:
                v = f"<Native {ln} bytes>"
            return (format_tag(tag), vr, "1", length, name, v, off)
        if fl & F_SEQ:
            return (format_tag(tag), vr, "1", length, name, "", off)
        if fl & F_UNDEF:
            return (format_tag(tag), vr, "1", length, name, "", off)
        if vr in BINARY_VRS:
            data = self.read(start + idx.header_len[nid], min(ln, 16))
            return (format_tag(tag), vr, "1" if ln else "0", length, name, _hex(data, ln), off)
        el = self._element(nid, self.encodings(nid))
        if el is None:
            data = self.read(start + idx.header_len[nid], min(ln, 16))
            return (format_tag(tag), vr, "", length, name, _hex(data, ln), off)
        v = el.value
        if v is None or v == "":
            value = ""
        elif isinstance(v, (MultiValue, list, tuple)):
            value = "\\".join(_fmt_scalar(x) for x in v)
        else:
            value = _fmt_scalar(v)
        if ln > READ_MAX:
            value += "…"
        return (format_tag(tag), vr, str(el.VM), length, name, value, off)

    def _name(self, nid: int, tag: int) -> str:
        group, elem = tag >> 16, tag & 0xFFFF
        if group & 1:
            if 0x0010 <= elem <= 0x00FF:
                return "PrivateCreator"
            creator = self.private_creator(nid)
            if creator:
                try:
                    return datadict.get_private_entry(tag, creator)[2]
                except KeyError:
                    return creator
            return "Private"
        if elem == 0:
            return "GroupLength"
        kw = datadict.keyword_for_tag(tag)
        return kw or "Unknown"


def _hex(data: bytes, total: int) -> str:
    s = " ".join(f"{b:02X}" for b in data)
    return s + (" …" if total > len(data) else "")
