# DICOMDIR의 Directory Record를 Offset 규칙으로 계층화하고 참조 파일 경로를 해석한다.
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pydicom.multival import MultiValue

from .dicom_file import DicomFile
from .element_index import K_ITEM

TAG_ROOT_FIRST = 0x00041200
TAG_RECORD_SEQ = 0x00041220
TAG_NEXT = 0x00041400
TAG_LOWER = 0x00041420
TAG_RECORD_TYPE = 0x00041430
TAG_REF_FILE_ID = 0x00041500


@dataclass
class DirRecord:
    record_type: str
    offset: int  # DICOMDIR 파일 안 Item 시작 위치 (Preamble 포함 기준)
    node: int  # DICOMDIR 색인의 Item 노드 번호
    name: str = ""
    info: str = ""
    ref_path: Path | None = None
    children: list["DirRecord"] = field(default_factory=list)

    @property
    def exists(self) -> bool:
        return self.ref_path is None or self.ref_path.is_file()


def _val(f: DicomFile, item: int, tag: int):
    c = f.index.find_child(item, tag)
    if c is None:
        return None
    el = f.formatter.element(c)
    return el.value if el is not None else None


def _str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (MultiValue, list)):
        return "\\".join(str(x) for x in v)
    return str(v).strip()


def _date(v: str) -> str:
    return f"{v[:4]}-{v[4:6]}-{v[6:8]}" if len(v) == 8 and v.isdigit() else v


def _describe(f: DicomFile, rec: DirRecord, base: Path) -> None:
    it = rec.node
    rt = rec.record_type
    ref = _val(f, it, TAG_REF_FILE_ID)
    if ref:
        parts = [str(x) for x in ref] if isinstance(ref, (MultiValue, list)) else str(ref).split("\\")
        rec.ref_path = base.joinpath(*[p for p in parts if p])
    if rt == "PATIENT":
        rec.name = _str(_val(f, it, 0x00100010))
        pid = _str(_val(f, it, 0x00100020))
        rec.info = f"ID {pid}" if pid else ""
    elif rt == "STUDY":
        rec.name = _date(_str(_val(f, it, 0x00080020)))
        rec.info = _str(_val(f, it, 0x00081030))
    elif rt == "SERIES":
        mod = _str(_val(f, it, 0x00080060))
        num = _str(_val(f, it, 0x00200011))
        rec.name = f"{mod}  #{num}" if num else mod
    elif rec.ref_path is not None:
        rec.name = rec.ref_path.name
    if rec.ref_path is not None and not rec.exists:
        rec.info = "File not found"


def build_records(f: DicomFile) -> list[DirRecord]:
    """루트 레코드 목록. Offset 체인을 따라가고, 체인이 없으면 순서대로 나열한다."""
    idx = f.index
    seq = idx.find_child(-1, TAG_RECORD_SEQ)
    if seq is None:
        return []
    base = f.path.parent
    items = [c for c in idx.children(seq) if idx.kind[c] == K_ITEM]
    by_off: dict[int, DirRecord] = {}
    recs: list[DirRecord] = []
    for it in items:
        rec = DirRecord(_str(_val(f, it, TAG_RECORD_TYPE)), idx.start[it], it)
        _describe(f, rec, base)
        by_off[rec.offset] = rec
        recs.append(rec)
    first = _val(f, -1, TAG_ROOT_FIRST)
    if not first or int(first) not in by_off:
        return recs
    seen: set[int] = set()

    def chain(off: int) -> list[DirRecord]:
        out = []
        while off and off in by_off and off not in seen:
            seen.add(off)
            r = by_off[off]
            low = _val(f, r.node, TAG_LOWER)
            if low:
                r.children = chain(int(low))
            out.append(r)
            nxt = _val(f, r.node, TAG_NEXT)
            off = int(nxt) if nxt else 0
        return out

    return chain(int(first))


def iter_records(recs: list[DirRecord]):
    for r in recs:
        yield r
        yield from iter_records(r.children)
