# wsidicom 어댑터. 슬라이드 열기, 레벨 목록, 타일 읽기, sparse 판별을 한 곳에 모은다.
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from wsidicom import WsiDicom
from wsidicom.errors import WsiDicomError, WsiDicomNotFoundError, WsiDicomOutOfBoundsError
from wsidicom.geometry import Point

log = logging.getLogger("vw")


class TileError(Exception):
    """타일 좌표가 범위 밖이거나 읽기에 실패했다."""


@dataclass(frozen=True)
class LevelInfo:
    index: int  # 0 = 최대 해상도 (트리의 Ln과 같은 순서)
    level: int  # wsidicom 피라미드 레벨 번호 (배율 지수)
    size: tuple[int, int]
    tile_size: tuple[int, int]
    downsample: float  # 레벨 0 대비 축소 비율

    @property
    def tiles(self) -> tuple[int, int]:
        return (-(-self.size[0] // self.tile_size[0]), -(-self.size[1] // self.tile_size[1]))


@dataclass
class TileResult:
    array: np.ndarray | None  # RGB uint8 (H, W, 3). sparse면 None
    sparse: bool


def _release_frame_sequences(levels) -> None:
    """TILED_SPARSE 레벨의 타일 위치 색인을 지금 만들고 Per-Frame Functional Groups Sequence를 놓는다 (QA-04).
    wsidicom은 이 시퀀스로 색인을 한 번 만든 뒤(SparseTileIndex.planes) 다시 읽지 않지만, Dataset과 cached
    frame_sequence가 계속 붙잡아 S-V에서 약 280 MB를 차지한다. 슬라이드를 워커 스레드에 넘기기 전(열 때) 한 번 한다.
    wsidicom 0.29 내부 구조에 기대므로 구조가 다르거나 실패하면 그 인스턴스는 그대로 둔다(메모리만 더 쓴다)."""
    for level in levels:
        for inst in level.instances.values():
            try:
                data = inst.image_data
                tiles = data.tiles
                if not hasattr(type(tiles), "planes"):
                    continue  # TILED_FULL: 시퀀스로 색인을 만들지 않는다
                datasets = data._datasets
                tiles.planes  # noqa: B018 색인을 지금 만든다
                for ds in datasets:
                    ds.tile_type  # noqa: B018 판정에 이 시퀀스를 쓰므로 지우기 전에 캐시해 둔다
                    if "PerFrameFunctionalGroupsSequence" in ds:
                        del ds["PerFrameFunctionalGroupsSequence"]
                    ds.__dict__.pop("frame_sequence", None)
            except Exception:  # 최적화일 뿐이다. 실패해도 타일 읽기는 wsidicom 기본 동작으로 한다
                log.debug("Per-Frame 시퀀스 해제 생략", exc_info=True)


class Slide:
    """WsiDicom 슬라이드 1개. 스레드 안전한 read_tile만 워커에서 호출한다."""

    def __init__(self, wsi: WsiDicom):
        self._wsi = wsi
        lv = list(wsi.levels)
        lv.sort(key=lambda l: l.size.width * l.size.height, reverse=True)
        base = lv[0].size.width
        self.levels = [LevelInfo(i, l.level, (l.size.width, l.size.height),
                                 (l.tile_size.width, l.tile_size.height), base / l.size.width)
                       for i, l in enumerate(lv)]
        self._lv = lv
        _release_frame_sequences(lv)
        self.focal_planes: list[float] = sorted(float(z) for z in lv[0].focal_planes)
        self.optical_paths: list[str] = [str(p) for p in lv[0].optical_paths]
        self.default_z = self.focal_planes[0] if self.focal_planes else None  # L-04: 가장 작은 Z
        self.default_path = self.optical_paths[0] if self.optical_paths else None  # 첫 Optical Path

    @classmethod
    def open(cls, paths: list[Path | str]) -> "Slide":
        try:
            wsi = WsiDicom.open([Path(p) for p in paths])
        except WsiDicomError as e:
            raise TileError(f"Cannot open slide: {e}") from e
        if not list(wsi.levels):
            wsi.close()
            raise TileError("No VOLUME level")
        return cls(wsi)

    def close(self) -> None:
        self._wsi.close()

    def best_level(self, scale: float) -> int:
        """현재 배율(화면 픽셀 / 레벨0 픽셀)에 가장 가까운, 그 이상 해상도의 레벨."""
        best = 0
        for info in self.levels:
            if 1.0 / info.downsample >= scale - 1e-9:
                best = info.index
        return best

    def _instance_z_path(self, index: int, z, path):
        z = self.default_z if z is None else z
        path = self.default_path if path is None else path
        return self._lv[index], z, path

    def is_sparse(self, index: int, x: int, y: int, z: float | None = None, path: str | None = None) -> bool:
        lvl, z, path = self._instance_z_path(index, z, path)
        try:
            inst = lvl.get_instance(z, path)
            return bool(inst.image_data.is_sparse(Point(x, y), z, path))
        except (WsiDicomOutOfBoundsError, WsiDicomNotFoundError) as e:
            raise TileError(str(e)) from e

    def read_tile(self, index: int, x: int, y: int, z: float | None = None, path: str | None = None) -> TileResult:
        info = self.levels[index]
        tx, ty = info.tiles
        if not (0 <= x < tx and 0 <= y < ty):
            raise TileError(f"Tile ({x}, {y}) is outside (0..{tx - 1}, 0..{ty - 1})")
        if self.is_sparse(index, x, y, z, path):
            return TileResult(None, True)
        lvl, z, path = self._instance_z_path(index, z, path)
        try:
            img = self._wsi.read_tile(lvl.level, (x, y), z, path)
        except (WsiDicomOutOfBoundsError, WsiDicomNotFoundError) as e:
            raise TileError(str(e)) from e
        if img.mode != "RGB":
            img = img.convert("RGB")
        return TileResult(np.asarray(img), False)
