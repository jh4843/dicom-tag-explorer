# 열린 DICOM 파일 하나의 경로·상태·색인·요약 메타를 관리한다.
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pydicom.multival import MultiValue
from pydicom.uid import UID

from .bytesource import ByteSource, FileReader
from .element_index import ElementIndex
from .indexer import Cancelled, NotDicomError, index_file, walk_fragments
from .element_index import F_BIG, F_VIRTUAL

WSI_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.77.1.6"
DICOMDIR_SOP_CLASS = "1.2.840.10008.1.3.10"


class FileState(Enum):
    PENDING = "pending"
    OK = "ok"
    DAMAGED = "damaged"  # 중간까지 파싱
    FAILED = "failed"  # DICOM 아님 / 파싱 실패
    CANCELLED = "cancelled"


@dataclass
class Summary:
    sop_class_uid: str = ""
    sop_instance_uid: str = ""
    study_uid: str = ""
    series_uid: str = ""
    image_type: list[str] = field(default_factory=list)
    total_cols: int | None = None
    total_rows: int | None = None
    cols: int | None = None
    rows: int | None = None
    frames: int = 1
    container_id: str = ""
    series_description: str = ""
    z_offset: float | None = None
    focal_planes: int = 1
    optical_path_id: str = ""
    has_pixel_data: bool = False
    tile_cols: int | None = None
    tile_rows: int | None = None

    @property
    def image_type3(self) -> str:
        return self.image_type[2] if len(self.image_type) >= 3 else ""


def normalize_path(path: Path | str) -> Path:
    """중복 판별용 정규화 절대 경로 (Windows는 대소문자 무시)."""
    return Path(os.path.normcase(os.path.abspath(path)))


class DicomFile:
    def __init__(self, path: Path | str):
        self.path = Path(os.path.abspath(path))
        self.key = normalize_path(self.path)
        self.state = FileState.PENDING
        self.error: str | None = None
        self.index: ElementIndex | None = None
        self.transfer_syntax = ""
        self.body: bytes | None = None
        self.summary = Summary()
        self.size = 0
        self._src: ByteSource | None = None
        self._lock = threading.RLock()
        self.formatter = None

    # ---- 바이트 접근 ----
    def open_source(self) -> ByteSource:
        with self._lock:
            if self._src is None or self._src.closed:
                self._src = ByteSource(self.path)
                self.size = self._src.size
            return self._src

    def release(self) -> None:
        """mmap을 닫는다. 색인은 유지한다."""
        with self._lock:
            if self._src is not None:
                self._src.close()
                self._src = None

    def read(self, pos: int, n: int) -> bytes:
        vb = self.index.virtual_base if self.index is not None else None
        if vb is not None and pos >= vb and self.body is not None:
            p = pos - vb
            return self.body[p:p + n]
        with self._lock:
            return self.open_source().read(pos, n)

    def read_raw(self, pos: int, n: int) -> bytes:
        """원본 파일 바이트 (Hex 뷰용)."""
        with self._lock:
            return self.open_source().read(pos, n)

    # ---- 읽기 ----
    @property
    def transfer_syntax_name(self) -> str:
        if not self.transfer_syntax:
            return ""
        u = UID(self.transfer_syntax)
        return u.name if u.is_transfer_syntax else self.transfer_syntax

    @property
    def is_wsi(self) -> bool:
        return self.summary.sop_class_uid == WSI_SOP_CLASS

    @property
    def is_dicomdir(self) -> bool:
        return self.summary.sop_class_uid == DICOMDIR_SOP_CLASS

    @property
    def loaded(self) -> bool:
        return self.state in (FileState.OK, FileState.DAMAGED) and self.index is not None

    def load(self, token=None, keep_open: bool = False) -> "DicomFile":
        """헤더 색인과 요약을 만든다. 예외를 던지지 않고 state/error에 기록한다."""
        from .values import ValueFormatter
        try:
            src = self.open_source()
            res = index_file(src.buffer, src.size, token)
            self.index = res.index
            self.transfer_syntax = res.transfer_syntax
            self.body = res.body
            self.formatter = ValueFormatter(self.index, self.read)
            self._summarize()
            if res.error:
                self.state = FileState.DAMAGED
                self.error = res.error
            else:
                self.state = FileState.OK
                self.error = None
        except Cancelled:
            self.state = FileState.CANCELLED
            self.error = "Cancelled"
            self.index = None
        except NotDicomError as e:
            self.state = FileState.FAILED
            self.error = str(e)
        except OSError as e:
            self.state = FileState.FAILED
            self.error = f"Cannot open file: {e.strerror or e}"
        except Exception as e:  # 예기치 않은 파싱 오류
            self.state = FileState.FAILED
            self.error = f"{type(e).__name__}: {e}"
        finally:
            if not keep_open:
                self.release()
        return self

    def fragment_nodes(self, pixel_node: int, token=None) -> list[tuple]:
        """Encapsulated Pixel Data의 Fragment 노드 목록 (백그라운드에서 호출). 색인에 붙이는 것은 호출자."""
        idx = self.index
        vstart = idx.start[pixel_node] + idx.header_len[pixel_node]
        little = not (idx.flags[pixel_node] & F_BIG)
        if idx.flags[pixel_node] & F_VIRTUAL:
            return walk_fragments(self.body, idx.virtual_base, vstart, little, token)
        # 공유 mmap과 잠금을 쓰지 않고 파일을 따로 읽는다 (QA-01). 색인 내내 잠금을 쥐면 처음 읽는 큰 파일(OS 캐시가
        # 빈 상태)에서 UI 스레드의 Hex 그리기(read_raw)가 색인이 끝날 때까지 기다리고, mmap 페이지 폴트는 GIL을 쥔 채
        # 디스크를 기다려 UI 콜백을 늦춘다
        with FileReader(self.path) as src:
            return walk_fragments(src, 0, vstart, little, token)

    # ---- 요약 ----
    def _value(self, nid):
        if nid is None:
            return None
        el = self.formatter.element(nid)
        return el.value if el is not None else None

    def _v(self, *tags):
        return self._value(self.index.find_path(list(tags)))

    def _summarize(self) -> None:
        s = Summary()
        s.sop_class_uid = _s(self._v(0x00080016)) or _s(self._v(0x00020002))
        s.sop_instance_uid = _s(self._v(0x00080018))
        s.study_uid = _s(self._v(0x0020000D))
        s.series_uid = _s(self._v(0x0020000E))
        it = self._v(0x00080008)
        s.image_type = [str(x) for x in it] if isinstance(it, (MultiValue, list)) else ([str(it)] if it else [])
        s.total_cols = _i(self._v(0x00480006))
        s.total_rows = _i(self._v(0x00480007))
        s.cols = _i(self._v(0x00280011))
        s.rows = _i(self._v(0x00280010))
        s.frames = _i(self._v(0x00280008)) or 1
        s.container_id = _s(self._v(0x00400512))
        s.series_description = _s(self._v(0x0008103E))
        s.focal_planes = _i(self._v(0x00480303)) or 1
        s.optical_path_id = _s(self._v(0x00480105, 0x00480106))
        z = self._v(0x52009229, 0x0048021A, 0x0040074A)
        if z is None:
            z = self._v(0x52009230, 0x0048021A, 0x0040074A)
        try:
            s.z_offset = float(z) if z not in (None, "") else None
        except (TypeError, ValueError):
            s.z_offset = None
        s.has_pixel_data = any(self.index.find_child(-1, t) is not None
                               for t in (0x7FE00010, 0x7FE00008, 0x7FE00009))
        s.tile_cols, s.tile_rows = s.cols, s.rows
        self.summary = s


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (MultiValue, list)):
        return "\\".join(str(x) for x in v)
    return str(v).strip()


def _i(v) -> int | None:
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None
