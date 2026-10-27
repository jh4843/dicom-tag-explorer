# 파일/WSI/DICOMDIR 분류 트리 모델 (QStandardItemModel, 2컬럼 이름 | 정보).
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QBrush, QStandardItem, QStandardItemModel

from ..core.classify import NON_WSI, WsiGroup, file_info, size_text
from ..core.dicom_file import DicomFile, FileState, normalize_path
from ..core.dicomdir import DirRecord
from . import theme
from .common import tr_core
from .icons import icon
from .theme import color

ROLE_KIND = Qt.ItemDataRole.UserRole + 1
ROLE_KEY = Qt.ItemDataRole.UserRole + 2
ROLE_SEQ = Qt.ItemDataRole.UserRole + 3

KIND_FOLDER = "folder"
KIND_FILE = "file"
KIND_GROUP = "group"
KIND_NONWSI = "nonwsi"
KIND_DIRROOT = "dirroot"
KIND_RECORD = "record"


CATEGORY_ICONS = {"VOLUME": "wsi-volume", "LABEL": "wsi-label", "OVERVIEW": "wsi-overview",
                  "THUMBNAIL": "wsi-thumbnail"}
RECORD_ICONS = {"PATIENT": "patient", "STUDY": "study", "SERIES": "series"}


def _brush(token: str) -> QBrush:
    return QBrush(color(token))


def _muted() -> QBrush:
    return _brush("ink-muted")


def _error() -> QBrush:
    return _brush("danger")


def _row(name: str, info: str, kind: str, key, tooltip: str = "") -> list[QStandardItem]:
    a = QStandardItem(name)
    b = QStandardItem(info)
    for it in (a, b):
        it.setEditable(False)
        it.setData(kind, ROLE_KIND)
        it.setData(key, ROLE_KEY)
        if tooltip:
            it.setToolTip(tooltip)
    b.setForeground(_muted())
    b.setFont(theme.font("mono-sm"))  # 정보 컬럼은 mono-sm ink-muted (ExplorerTree README)
    return [a, b]


def _apply_state(items: list[QStandardItem], f: DicomFile) -> None:
    a, b = items
    tip = str(f.path)
    if f.state == FileState.FAILED:
        a.setIcon(icon("error"))
        a.setForeground(_error())
        b.setForeground(_error())
        tip += "\n" + tr_core(f.error or "")
    elif f.state == FileState.DAMAGED:
        a.setIcon(icon("warning"))
        a.setForeground(_brush("warning"))
        tip += "\n" + QCoreApplication.translate("ExplorerModels", "Parse stopped: {0}").format(tr_core(f.error or ""))
    elif f.state == FileState.CANCELLED:
        a.setIcon(icon("cancelled"))
        a.setForeground(_brush("ink-faint"))
        tip += "\n" + QCoreApplication.translate("ExplorerModels", "Cancelled")
    else:
        a.setIcon(icon("dicom-file"))
        a.setData(None, Qt.ItemDataRole.ForegroundRole)  # 빈 QBrush()는 검정으로 그려지므로 역할 값을 지워 기본 ink를 쓴다
        b.setForeground(_muted())
    b.setText(tr_core(file_info(f)))
    a.setToolTip(tip)
    b.setToolTip(tip)


class FilesModel(QStandardItemModel):
    """폴더 > 파일 2단계, 열린 순서."""

    def __init__(self, parent=None):
        super().__init__(0, 2, parent)
        self.folders: dict[str, QStandardItem] = {}
        self.items: dict[Path, list[QStandardItem]] = {}

    def add_file(self, f: DicomFile, seq: int = 0) -> None:
        """seq(탐색 순번) 순서로 끼워 넣는다. 병렬 로딩이 끝나는 순서와 무관하게 열린 순서를 유지한다."""
        if f.key in self.items:
            self.update_file(f)
            return
        folder = str(f.path.parent) + "\\"
        fk = folder.lower()
        parent = self.folders.get(fk)
        if parent is None:
            row = _row(folder, "", KIND_FOLDER, folder, folder)
            row[0].setIcon(icon("folder"))
            row[0].setData(seq, ROLE_SEQ)
            self.insertRow(self._pos(self.invisibleRootItem(), seq), row)
            parent = self.folders[fk] = row[0]
        row = _row(f.path.name, "", KIND_FILE, f.key)
        row[0].setData(seq, ROLE_SEQ)
        _apply_state(row, f)
        parent.insertRow(self._pos(parent, seq), row)
        self.items[f.key] = row

    @staticmethod
    def _pos(parent: QStandardItem, seq: int) -> int:
        for r in range(parent.rowCount()):
            v = parent.child(r, 0).data(ROLE_SEQ)
            if v is not None and v > seq:
                return r
        return parent.rowCount()

    def update_file(self, f: DicomFile) -> None:
        row = self.items.get(f.key)
        if row:
            _apply_state(row, f)

    def remove_file(self, key: Path) -> None:
        row = self.items.pop(key, None)
        if not row:
            return
        parent = row[0].parent()
        parent.removeRow(row[0].row())
        if parent.rowCount() == 0:
            self.folders = {k: v for k, v in self.folders.items() if v is not parent}
            self.removeRow(parent.row())

    def refresh_icons(self) -> None:
        for it in self.folders.values():
            it.setIcon(icon("folder"))

    def item_for(self, key: Path) -> QStandardItem | None:
        row = self.items.get(key)
        return row[0] if row else None

    def clear_all(self) -> None:
        self.removeRows(0, self.rowCount())
        self.folders.clear()
        self.items.clear()


class WsiModel(QStandardItemModel):
    def __init__(self, parent=None):
        super().__init__(0, 2, parent)
        self.items: dict[Path, QStandardItem] = {}
        self.groups: dict[tuple, QStandardItem] = {}
        self.group_data: dict[tuple, WsiGroup] = {}

    def rebuild(self, groups: list[WsiGroup], non_wsi: list[DicomFile]) -> None:
        self.removeRows(0, self.rowCount())
        self.items.clear()
        self.groups.clear()
        self.group_data = {g.key: g for g in groups}
        for g in groups:
            n = len(g.instances)
            row = _row(g.name, self.tr("%n instance(s)", "", n), KIND_GROUP, g.key,
                       f"Study UID {g.study_uid}\nSeries UID {g.series_uid}")
            row[0].setIcon(icon("wsi-slide"))
            self.appendRow(row)
            self.groups[g.key] = row[0]
            for inst in g.instances:
                r = _row(inst.label, size_text(inst.size), KIND_FILE, inst.file.key, str(inst.file.path))
                r[0].setIcon(icon(CATEGORY_ICONS.get(inst.category, "dicom-file")))
                if inst.category == "VOLUME" and inst.file.summary.z_offset is not None and len(g.z_values) >= 2:
                    tip = f"{inst.file.path}\nZ {inst.file.summary.z_offset} µm"
                    r[0].setToolTip(tip)
                    r[1].setToolTip(tip)
                row[0].appendRow(r)
                self.items[inst.file.key] = r[0]
        if non_wsi:
            n = len(non_wsi)
            row = _row(self.tr("(Non-WSI)"), self.tr("%n file(s)", "", n), KIND_NONWSI, NON_WSI)
            row[0].setIcon(icon("folder"))
            self.appendRow(row)
            for f in non_wsi:
                r = _row(f.path.name, tr_core(file_info(f)), KIND_FILE, f.key, str(f.path))
                r[0].setIcon(icon("dicom-file"))
                row[0].appendRow(r)
                self.items[f.key] = r[0]

    def item_for(self, key) -> QStandardItem | None:
        return self.items.get(key)


class DicomdirModel(QStandardItemModel):
    def __init__(self, parent=None):
        super().__init__(0, 2, parent)
        self.roots: dict[Path, QStandardItem] = {}
        self.image_items: dict[Path, list[QStandardItem]] = {}
        self._root_images: dict[Path, list[tuple[Path, QStandardItem]]] = {}

    def add_dicomdir(self, f: DicomFile, records: list[DirRecord]) -> None:
        if f.key in self.roots:
            return
        row = _row(f.path.name, str(f.path.parent) + "\\", KIND_DIRROOT, f.key, str(f.path))
        row[0].setIcon(icon("dicomdir"))
        self.appendRow(row)
        self.roots[f.key] = row[0]
        mine = self._root_images[f.key] = []

        def add(parent: QStandardItem, recs: list[DirRecord]):
            for r in recs:
                name = f"{r.record_type}  {r.name}".strip()
                items = _row(name, tr_core(r.info), KIND_RECORD, (f.key, r))
                items[0].setIcon(icon(RECORD_ICONS.get(r.record_type, "image-record")))
                if r.ref_path is not None:
                    tip = str(r.ref_path)
                    items[0].setToolTip(tip)
                    if not r.exists:
                        items[0].setIcon(icon("error"))
                        items[0].setForeground(_error())
                        items[1].setForeground(_error())
                    else:
                        rk = normalize_path(r.ref_path)
                        self.image_items.setdefault(rk, []).append(items[0])
                        mine.append((rk, items[0]))
                parent.appendRow(items)
                add(items[0], r.children)

        add(row[0], records)

    def remove_dicomdir(self, key: Path) -> None:
        it = self.roots.pop(key, None)
        if it is not None:
            self.removeRow(it.row())
            self._root_images.pop(key, None)
            self.image_items = {}
            for lst in self._root_images.values():
                for rk, item in lst:
                    self.image_items.setdefault(rk, []).append(item)

    def item_for(self, key) -> QStandardItem | None:
        if key in self.roots:
            return self.roots[key]
        v = self.image_items.get(key)
        return v[0] if v else None

    def update_image_info(self, f: DicomFile) -> None:
        for it in self.image_items.get(f.key, []):
            sib = it.parent().child(it.row(), 1) if it.parent() else None
            if sib is not None:
                sib.setText(tr_core(file_info(f)))

    def clear_all(self) -> None:
        self.removeRows(0, self.rowCount())
        self.roots.clear()
        self.image_items.clear()
        self._root_images.clear()
