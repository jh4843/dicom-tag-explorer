# 통합·상세 검색 조건을 파싱·검증하고 파일의 모든 노드에서 일치 노드 번호를 찾는다.
from __future__ import annotations

import re
from dataclasses import dataclass, field, fields

from .element_index import ElementIndex, K_ERROR, K_PREAMBLE, K_PREFIX
from .indexer import Cancelled
from .values import C_LEN, C_NAME, C_VALUE, C_VM, C_VR, ValueFormatter

CHECK_EVERY = 2048
STANDARD_VRS = ("AE", "AS", "AT", "CS", "DA", "DS", "DT", "FD", "FL", "IS", "LO", "LT", "OB", "OD", "OF",
                "OL", "OV", "OW", "PN", "SH", "SL", "SQ", "SS", "ST", "SV", "TM", "UC", "UI", "UL", "UN",
                "UR", "US", "UT", "UV")

HINTS = {
    "tag": "Format: 0010,0010 / 00100010 / (0010,0010). A prefix is allowed (e.g. 0010)",
    "vr": "Format: two-letter VR (e.g. PN)",
    "vm": "Format: decimal number",
    "length": "Format: decimal number",
    "offset": "Format: hex (0x optional)",
}


@dataclass
class Criteria:
    text: str = ""  # 통합 검색 (모든 컬럼)
    tag: str = ""
    vr: str = ""
    vm: str = ""
    name: str = ""
    length: str = ""
    offset: str = ""
    value: str = ""
    match_case: bool = False
    regex: bool = False

    def is_empty(self) -> bool:
        return not any(getattr(self, f.name).strip() for f in fields(self) if isinstance(getattr(self, f.name), str))


def normalize_tag(s: str) -> str | None:
    t = re.sub(r"[()\s,]", "", s).upper()
    if not t or len(t) > 8 or not re.fullmatch(r"[0-9A-F]+", t):
        return None
    return t


@dataclass
class Compiled:
    text: object = None  # 문자열 매처
    tag_prefix: str | None = None
    vr: str | None = None
    vm: str | None = None
    length: str | None = None
    offset: int | None = None
    name: object = None
    value: object = None
    errors: dict = field(default_factory=dict)  # 필드 → 오류 안내 (검색에서 제외)

    @property
    def active(self) -> bool:
        return any(v is not None for v in (self.text, self.tag_prefix, self.vr, self.vm, self.length,
                                           self.offset, self.name, self.value))


def _matcher(s: str, match_case: bool, regex: bool):
    if regex:
        return re.compile(s, 0 if match_case else re.IGNORECASE).search
    if match_case:
        return lambda v: s in v
    low = s.casefold()
    return lambda v: low in v.casefold()


def compile_criteria(c: Criteria) -> Compiled:
    out = Compiled()
    for fld in ("text", "name", "value"):
        s = getattr(c, fld).strip()
        if s:
            try:
                setattr(out, fld, _matcher(s, c.match_case, c.regex))
            except re.error as e:
                out.errors[fld] = f"Regular expression error: {e}"
    if c.tag.strip():
        t = normalize_tag(c.tag)
        if t is None:
            out.errors["tag"] = HINTS["tag"]
        else:
            out.tag_prefix = t
    if c.vr.strip():
        v = c.vr.strip().upper()
        if re.fullmatch(r"[A-Z]{2}", v):
            out.vr = v
        else:
            out.errors["vr"] = HINTS["vr"]
    for fld in ("vm", "length"):
        s = getattr(c, fld).strip()
        if s:
            if s.isdigit():
                setattr(out, fld, str(int(s)))
            else:
                out.errors[fld] = HINTS[fld]
    if c.offset.strip():
        s = c.offset.strip().lower()
        s = s[2:] if s.startswith("0x") else s
        if s and re.fullmatch(r"[0-9a-f]+", s):
            out.offset = int(s, 16)
        else:
            out.errors["offset"] = HINTS["offset"]
    return out


def _has_tag(idx: ElementIndex, i: int) -> bool:
    return idx.kind[i] not in (K_PREAMBLE, K_PREFIX, K_ERROR)


def search(idx: ElementIndex, fmt: ValueFormatter, comp: Compiled, token=None) -> list[int]:
    """모든 노드(접힌 노드, 색인된 Fragment 포함)에서 조건을 모두 만족하는 노드 번호 (파일 순서)."""
    if not comp.active:
        return []
    out = []
    order = list(range(idx.n_main))
    # 확장(Fragment) 노드는 부모 Pixel Data 바로 뒤 순서로 끼운다
    if idx.ext:
        ext_after = {p: range(f, f + c) for p, (f, c) in list(idx.ext.items())}  # UI 스레드의 추가와 경합 방지
        merged = []
        for i in order:
            merged.append(i)
            if i in ext_after:
                merged.extend(ext_after[i])
        order = merged
    for k, i in enumerate(order):
        if k % CHECK_EVERY == 0 and token is not None and token.is_cancelled():
            raise Cancelled()
        if comp.offset is not None:
            if idx.is_virtual(i) or not idx.contains(i, comp.offset):
                continue
        if comp.tag_prefix is not None:
            if not _has_tag(idx, i):
                continue
            tag_hex = f"{idx.tag[i]:08X}"
            if not tag_hex.startswith(comp.tag_prefix):
                continue
        cols = fmt.compute(i)
        if comp.vr is not None and cols[C_VR] != comp.vr:
            continue
        if comp.vm is not None and cols[C_VM] != comp.vm:
            continue
        if comp.length is not None and cols[C_LEN] != comp.length:
            continue
        if comp.name is not None and not comp.name(cols[C_NAME]):
            continue
        if comp.value is not None and not comp.value(cols[C_VALUE]):
            continue
        if comp.text is not None and not any(comp.text(c) for c in cols if c):
            continue
        out.append(i)
    return out
