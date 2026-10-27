# PS3.5 인코딩 규칙으로 파일을 순회해 요소 헤더 위치를 기록한 ElementIndex를 만든다.
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

from pydicom import datadict

from .element_index import (
    F_BIG, F_ENCAP, F_IMPLICIT, F_SEQ, F_UNDEF, F_VIRTUAL,
    K_BOT, K_ELEMENT, K_ERROR, K_FRAGMENT, K_ITEM, K_ITEM_DELIM, K_PREAMBLE, K_PREFIX, K_SEQ_DELIM,
    TAG_ITEM, TAG_ITEM_DELIM, TAG_PIXEL_DATA, TAG_SEQ_DELIM,
    ElementIndex, vr_code,
)

UNDEF = 0xFFFFFFFF
LONG_VRS = {b"OB", b"OD", b"OF", b"OL", b"OV", b"OW", b"SQ", b"SV", b"UC", b"UN", b"UR", b"UT", b"UV"}
CHECK_EVERY = 4096
MSG_NOT_DICOM = "Not a DICOM file (no 'DICM' at offset 128)"

TS_IMPLICIT_LE = "1.2.840.10008.1.2"
TS_EXPLICIT_LE = "1.2.840.10008.1.2.1"
TS_DEFLATE = "1.2.840.10008.1.2.1.99"
TS_EXPLICIT_BE = "1.2.840.10008.1.2.2"


class Cancelled(Exception):
    """CancelToken으로 작업이 취소됨."""


class ParseError(Exception):
    def __init__(self, pos: int, msg: str):
        super().__init__(msg)
        self.pos = pos
        self.msg = msg


class NotDicomError(Exception):
    """오프셋 128에 'DICM'이 없다."""


@dataclass
class IndexResult:
    index: ElementIndex
    transfer_syntax: str
    body: bytes | None  # Deflate 본문(압축 해제). 그 외 None
    error: str | None


def _is_cancelled(token) -> bool:
    return token is not None and token.is_cancelled()


_vr_cache: dict[int, str] = {}


def implicit_vr(tag: int, creator: str | None) -> str:
    group, elem = tag >> 16, tag & 0xFFFF
    if group & 1:
        if 0x0010 <= elem <= 0x00FF:
            return "LO"
        if elem == 0:
            return "UL"
        if creator:
            try:
                return _first_vr(datadict.private_dictionary_VR(tag, creator))
            except KeyError:
                pass
        return "UN"
    v = _vr_cache.get(tag)
    if v is None:
        if elem == 0:
            v = "UL"
        else:
            try:
                v = _first_vr(datadict.dictionary_VR(tag))
            except KeyError:
                v = "UN"
        _vr_cache[tag] = v
    return v


def _first_vr(v: str) -> str:
    if v == "OB or OW":
        return "OW"
    return v.split(" or ")[0][:2]


class _Walker:
    def __init__(self, idx: ElementIndex, buf, base: int, token, extra_flags: int = 0):
        self.idx = idx
        self.buf = buf  # mmap 또는 bytes
        self.base = base  # 이 버퍼의 0번 바이트가 갖는 (가상) 오프셋
        self.blen = len(buf)
        self.token = token
        self.xf = extra_flags
        self.count = 0

    def _tick(self):
        self.count += 1
        if self.count % CHECK_EVERY == 0 and _is_cancelled(self.token):
            raise Cancelled()

    def _hdr(self, pos: int, little: bool) -> tuple[int, int]:
        p = pos - self.base
        if p < 0 or p + 8 > self.blen:
            raise ParseError(pos, "Element header runs past end of file")
        g, e, ln = struct.unpack_from("<HHI" if little else ">HHI", self.buf, p)
        return (g << 16) | e, ln

    # ---- 데이터셋 ----
    def dataset(self, pos: int, end: int | None, parent: int, little: bool, explicit: bool,
                until_item_delim: bool, stop_group: int | None = None, row0: int = 0) -> tuple[int, int]:
        """end가 None이면 Item Delimitation까지. (다음 위치, 다음 row)을 돌려준다."""
        row = row0
        creators: dict[tuple[int, int], str] = {}
        limit = end if end is not None else self.base + self.blen
        while pos < limit:
            if stop_group is not None:
                p = pos - self.base
                if p + 2 > self.blen:
                    break
                g = struct.unpack_from("<H", self.buf, p)[0]
                if g != stop_group:
                    break
            tag, ln = self._hdr(pos, little)
            if tag == TAG_ITEM_DELIM:
                self._tick()
                fl = self.xf | (F_BIG if not little else 0)
                self.idx.append(pos, 8, 8, parent, tag, 0, K_ITEM_DELIM, fl, row, ln)
                row += 1
                pos += 8
                if until_item_delim:
                    return pos, row
                continue
            if tag in (TAG_ITEM, TAG_SEQ_DELIM):
                raise ParseError(pos, f"Unexpected tag in dataset ({tag >> 16:04X},{tag & 0xFFFF:04X})")
            pos = self.element(pos, tag, ln, limit, parent, row, little, explicit, creators)
            row += 1
        if until_item_delim and end is None:
            raise ParseError(pos, "Missing Item Delimitation")
        return pos, row

    def element(self, pos, tag, ln, limit, parent, row, little, explicit, creators) -> int:
        self._tick()
        buf, b = self.buf, self.base
        p = pos - b
        group, elem = tag >> 16, tag & 0xFFFF
        vr_b = bytes(buf[p + 4:p + 6]) if explicit else b""
        use_explicit = explicit and len(vr_b) == 2 and 65 <= vr_b[0] <= 90 and 65 <= vr_b[1] <= 90
        flags = self.xf
        if not little:
            flags |= F_BIG
        if use_explicit:
            vr = vr_b.decode("ascii")
            if vr_b in LONG_VRS:
                if p + 12 > self.blen:
                    raise ParseError(pos, "Element header runs past end of file")
                ln = struct.unpack_from("<I" if little else ">I", buf, p + 8)[0]
                hlen = 12
            else:
                ln = struct.unpack_from("<H" if little else ">H", buf, p + 6)[0]
                hlen = 8
        else:
            flags |= F_IMPLICIT
            creator = None
            if group & 1 and elem >= 0x1000:
                creator = creators.get((group, elem >> 8))
            vr = implicit_vr(tag, creator)
            hlen = 8
        vstart = pos + hlen
        undef = ln == UNDEF
        if undef:
            flags |= F_UNDEF
        is_seq = vr == "SQ" or (undef and (vr == "UN" or not use_explicit) and tag != TAG_PIXEL_DATA)
        nid = self.idx.append(pos, hlen, 0, parent, tag, vr_code(vr), K_ELEMENT, flags, row,
                              -1 if undef else ln)
        if is_seq:
            self.idx.flags[nid] |= F_SEQ
            # Undefined Length UN은 Implicit VR Little Endian으로 인코딩된다 (PS3.5 6.2.2)
            s_little, s_explicit = (True, False) if vr == "UN" else (little, explicit)
            if undef:
                endpos = self.sequence(vstart, None, nid, s_little, s_explicit)
            else:
                if vstart + ln > limit:
                    raise ParseError(pos, "Value length exceeds the enclosing range")
                endpos = self.sequence(vstart, vstart + ln, nid, s_little, s_explicit)
        elif undef:
            if tag == TAG_PIXEL_DATA:
                self.idx.flags[nid] |= F_ENCAP
                endpos = self.encapsulated_end(pos, vstart, limit, parent, little)
            else:
                self.fragments_eager(vstart, nid, little)
                endpos = self.encapsulated_end(pos, vstart, None, parent, little)
        else:
            endpos = vstart + ln
            if endpos > limit:
                raise ParseError(pos, "Value length exceeds the enclosing range")
            if group & 1 and 0x0010 <= elem <= 0x00FF and ln <= 256:
                creators[(group, elem)] = bytes(buf[vstart - b:endpos - b]).decode("latin-1").strip(" \0")
        self.idx.total_len[nid] = endpos - pos
        self.idx.subtree_end[nid] = len(self.idx.start)
        return endpos

    def sequence(self, pos: int, end: int | None, parent: int, little: bool, explicit: bool) -> int:
        row = 0
        limit = end if end is not None else self.base + self.blen
        while pos < limit:
            self._tick()
            tag, ln = self._hdr(pos, little)
            fl = self.xf | (0 if little else F_BIG)
            if tag == TAG_SEQ_DELIM:
                self.idx.append(pos, 8, 8, parent, tag, 0, K_SEQ_DELIM, fl, row, ln)
                return pos + 8
            if tag != TAG_ITEM:
                raise ParseError(pos, f"Non-Item tag inside Sequence ({tag >> 16:04X},{tag & 0xFFFF:04X})")
            undef = ln == UNDEF
            nid = self.idx.append(pos, 8, 0, parent, tag, 0, K_ITEM, fl | (F_UNDEF if undef else 0), row,
                                  -1 if undef else ln)
            if undef:
                endpos, _ = self.dataset(pos + 8, None, nid, little, explicit, True)
            else:
                if pos + 8 + ln > limit:
                    raise ParseError(pos, "Item length exceeds the enclosing range")
                endpos, _ = self.dataset(pos + 8, pos + 8 + ln, nid, little, explicit, False)
            self.idx.total_len[nid] = endpos - pos
            self.idx.subtree_end[nid] = len(self.idx.start)
            pos = endpos
            row += 1
        if end is None:
            raise ParseError(pos, "Missing Sequence Delimitation")
        return pos

    def encapsulated_end(self, pos, vstart, limit, parent, little) -> int:
        """Encapsulated 값의 끝(Sequence Delimitation 다음) 위치. 최상위 마지막 요소면 빠른 경로를 쓴다."""
        if parent == -1 and limit is not None:
            p = limit - 8 - self.base
            if p >= vstart - self.base:
                g, e, l2 = struct.unpack_from("<HHI" if little else ">HHI", self.buf, p)
                if ((g << 16) | e) == TAG_SEQ_DELIM and l2 == 0:
                    return limit
        q = vstart
        while True:
            self._tick()
            tag, ln = self._hdr(q, little)
            if tag == TAG_SEQ_DELIM:
                return q + 8
            if tag != TAG_ITEM or ln == UNDEF:
                raise ParseError(q, "Invalid Item in encapsulated value")
            q += 8 + ln

    def fragments_eager(self, vstart: int, parent: int, little: bool) -> None:
        for (s, hl, tl, tag, kind, ln) in walk_fragments(self.buf, self.base, vstart, little, self.token):
            self.idx.append(s, hl, tl, parent, tag, 0, kind, self.xf, 0, ln)
        # row 재계산
        for r, c in enumerate(range(parent + 1, len(self.idx.start))):
            self.idx.row[c] = r


def walk_fragments(buf, base: int, vstart: int, little: bool, token=None) -> list[tuple]:
    """Encapsulated 값의 Item 헤더를 순회한다. (start, header_len, total_len, tag, kind, length) 목록.
    buf는 len()과 슬라이스를 지원하면 된다 (bytes, mmap, FileReader)."""
    out = []
    q = vstart
    blen = len(buf)
    first = True
    fmt = "<HHI" if little else ">HHI"
    n = 0
    while True:
        n += 1
        if n % CHECK_EVERY == 0 and _is_cancelled(token):
            raise Cancelled()
        p = q - base
        if p + 8 > blen:
            raise ParseError(q, "Fragment header runs past end of file")
        g, e, ln = struct.unpack(fmt, buf[p:p + 8])  # 슬라이스: bytes·mmap·FileReader 모두 받는다
        tag = (g << 16) | e
        if tag == TAG_SEQ_DELIM:
            out.append((q, 8, 8, tag, K_SEQ_DELIM, ln))
            return out
        if tag != TAG_ITEM or ln == UNDEF:
            raise ParseError(q, "Invalid Item in encapsulated value")
        if p + 8 + ln > blen:
            raise ParseError(q, "Fragment length runs past end of file")
        out.append((q, 8, 8 + ln, tag, K_BOT if first else K_FRAGMENT, ln))
        first = False
        q += 8 + ln


def _close_open(idx: ElementIndex, pos: int) -> None:
    """파싱 중단 시 아직 닫히지 않은 노드(total_len 0)의 범위와 subtree_end를 확정한다."""
    n = len(idx.start)
    for i in range(n):
        if idx.total_len[i] == 0 and idx.kind[i] in (K_ELEMENT, K_ITEM):
            idx.total_len[i] = max(0, pos - idx.start[i])
            idx.subtree_end[i] = n


def _read_ts(idx: ElementIndex, buf) -> str:
    for c in range(len(idx.start)):
        if idx.tag[c] == 0x00020010 and idx.kind[c] == K_ELEMENT:
            s = idx.start[c] + idx.header_len[c]
            return bytes(buf[s:s + idx.length[c]]).decode("ascii", "replace").strip(" \0")
    return ""


def has_dicm(buf, size: int) -> bool:
    return size >= 132 and bytes(buf[128:132]) == b"DICM"


def index_file(buf, size: int, token=None) -> IndexResult:
    """buf는 mmap(또는 bytes). DICM이 없으면 NotDicomError."""
    if not has_dicm(buf, size):
        raise NotDicomError(MSG_NOT_DICOM)
    idx = ElementIndex(size)
    idx.append(0, 0, 128, -1, 0, 0, K_PREAMBLE, 0, 0, 128)
    idx.append(128, 0, 4, -1, 0, 0, K_PREFIX, 0, 1, 4)
    w = _Walker(idx, buf, 0, token)
    error = None
    body = None
    ts = ""
    row = 2
    try:
        pos, row = w.dataset(132, size, -1, True, True, False, stop_group=0x0002, row0=2)
        ts = _read_ts(idx, buf)
        if ts == TS_DEFLATE:
            try:
                d = zlib.decompressobj(-zlib.MAX_WBITS)
                body = d.decompress(bytes(buf[pos:size])) + d.flush()
            except zlib.error as e:
                raise ParseError(pos, f"Deflate decompression failed: {e}")
            idx.virtual_base = size
            w2 = _Walker(idx, body, size, token, extra_flags=F_VIRTUAL)
            w2.dataset(size, size + len(body), -1, True, True, False, row0=row)
        else:
            little = ts != TS_EXPLICIT_BE
            explicit = ts != TS_IMPLICIT_LE
            if not ts:
                # Transfer Syntax가 없으면 VR 글자로 추정한다
                p = pos + 4
                explicit = p + 2 <= size and all(65 <= x <= 90 for x in bytes(buf[p:p + 2]))
            w.dataset(pos, size, -1, little, explicit, False, row0=row)
    except ParseError as e:
        error = e.msg
        _close_open(idx, e.pos)
        top_rows = sum(1 for x in idx.parent if x == -1)
        end = size if not (idx.virtual_base is not None and e.pos >= size) else e.pos
        fl = F_VIRTUAL if (idx.virtual_base is not None and e.pos >= size) else 0
        idx.append(e.pos, 0, max(0, end - e.pos), -1, 0, 0, K_ERROR, fl, top_rows, 0)
        idx.error = error
    except struct.error as e:
        error = f"Structure error: {e}"
        idx.error = error
    idx.finish()
    idx._children.clear()
    return IndexResult(idx, ts, body, error)
