# SOP Class·Image Type 분류, WSI 그룹핑(Study+Series UID), 레벨·초점면 라벨을 계산한다.
from __future__ import annotations

from dataclasses import dataclass, field

from pydicom.uid import UID

from .dicom_file import DicomFile, FileState

KNOWN_TYPES = ("VOLUME", "LABEL", "OVERVIEW", "THUMBNAIL")
TYPE_ORDER = {t: i for i, t in enumerate(KNOWN_TYPES)}
NON_WSI = "(Non-WSI)"


def image_kind(f: DicomFile) -> str:
    """WSI면 Image Type 값 3 (정의되지 않은 값도 그대로). WSI가 아니면 ''."""
    if not f.is_wsi:
        return ""
    return f.summary.image_type3


def category(f: DicomFile) -> str:
    """VOLUME / LABEL / OVERVIEW / THUMBNAIL / OTHER (WSI 아님은 '')."""
    k = image_kind(f)
    if not f.is_wsi:
        return ""
    return k if k in KNOWN_TYPES else "OTHER"


def image_size(f: DicomFile) -> tuple[int, int] | None:
    s = f.summary
    if s.total_cols and s.total_rows:
        return (s.total_cols, s.total_rows)
    if s.cols and s.rows:
        return (s.cols, s.rows)
    return None


def size_text(size) -> str:
    return f"{size[0]}x{size[1]}" if size else ""


def sop_class_name(uid: str) -> str:
    if not uid:
        return ""
    u = UID(uid)
    n = u.name
    return n if n and n != uid else uid


def file_info(f: DicomFile) -> str:
    """파일 탭 정보 컬럼 (SPEC-018)."""
    if f.state == FileState.FAILED:
        return "Open failed"
    if f.state == FileState.CANCELLED:
        return "Cancelled"
    if f.state == FileState.PENDING:
        return ""
    if f.is_dicomdir:
        return "Media Storage Directory"
    if f.is_wsi:
        return f"{image_kind(f)}  {size_text(image_size(f))}".strip()
    return sop_class_name(f.summary.sop_class_uid)


@dataclass
class WsiInstance:
    file: DicomFile
    kind: str  # Image Type 값 3 그대로
    category: str
    size: tuple[int, int] | None
    level: int | None = None
    z_index: int | None = None
    op_id: str = ""
    level_label: str = ""  # 'L0 z1 OP 2', VOLUME이 아니면 '-'

    @property
    def label(self) -> str:
        lv = self.level_label if self.category == "VOLUME" else ""
        return f"{self.kind:<8} {lv}".rstrip()


@dataclass
class WsiGroup:
    study_uid: str
    series_uid: str
    name: str
    instances: list[WsiInstance] = field(default_factory=list)
    z_values: list[float] = field(default_factory=list)
    optical_paths: list[str] = field(default_factory=list)

    @property
    def key(self) -> tuple[str, str]:
        return (self.study_uid, self.series_uid)

    @property
    def files(self) -> list[DicomFile]:
        return [i.file for i in self.instances]


def group_name(f: DicomFile) -> str:
    s = f.summary
    if s.container_id:
        return s.container_id
    if s.series_description:
        return s.series_description
    return s.series_uid[-12:] if s.series_uid else "?"


def group_files(files: list[DicomFile]) -> tuple[list[WsiGroup], list[DicomFile]]:
    """열린 순서를 유지하며 WSI 그룹과 Non-WSI 파일 목록을 만든다. 실패·취소 파일은 제외한다."""
    groups: dict[tuple[str, str], WsiGroup] = {}
    non_wsi: list[DicomFile] = []
    for f in files:
        if not f.loaded:
            continue
        if not f.is_wsi:
            non_wsi.append(f)
            continue
        key = (f.summary.study_uid, f.summary.series_uid)
        g = groups.get(key)
        if g is None:
            g = groups[key] = WsiGroup(key[0], key[1], group_name(f))
        g.instances.append(WsiInstance(f, image_kind(f), category(f), image_size(f)))
    for g in groups.values():
        _label_group(g)
    return list(groups.values()), non_wsi


def _label_group(g: WsiGroup) -> None:
    vols = [i for i in g.instances if i.category == "VOLUME"]
    sizes = sorted({i.size for i in vols if i.size}, key=lambda s: (s[0] * s[1], s[0]), reverse=True)
    rank = {s: k for k, s in enumerate(sizes)}
    zs = sorted({i.file.summary.z_offset for i in vols if i.file.summary.z_offset is not None})
    ops = []
    for i in vols:
        op = i.file.summary.optical_path_id
        if op not in ops:
            ops.append(op)
    g.z_values = zs
    g.optical_paths = ops
    for i in vols:
        i.level = rank.get(i.size)
        z = i.file.summary.z_offset
        i.z_index = zs.index(z) if z is not None and z in zs else (0 if zs else None)
        i.op_id = i.file.summary.optical_path_id
        parts = [f"L{i.level}" if i.level is not None else "L?"]
        if len(zs) >= 2:
            parts.append(f"z{i.z_index}")
        if len(ops) >= 2:
            parts.append(f"OP {i.op_id}")
        i.level_label = " ".join(parts)
    for i in g.instances:
        if i.category != "VOLUME":
            i.level_label = "-"
    order = {id(i): n for n, i in enumerate(g.instances)}

    def key(i: WsiInstance):
        if i.category == "VOLUME":
            return (0, i.level if i.level is not None else 999, i.z_index or 0,
                    ops.index(i.op_id) if i.op_id in ops else 0, order[id(i)])
        if i.category in TYPE_ORDER:
            return (TYPE_ORDER[i.category], 0, 0, 0, order[id(i)])
        return (len(KNOWN_TYPES), 0, 0, 0, order[id(i)])

    g.instances.sort(key=key)
