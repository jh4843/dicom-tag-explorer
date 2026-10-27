# 타일 캐시 메모리 상한(L-05)과 단일 레벨 요청 수 (SPEC-025, TC-050 근거).
from __future__ import annotations

import numpy as np
from PySide6.QtGui import QPixmap

from dicom_tag_explorer.core.wsi import TileResult
from dicom_tag_explorer.ui.image_view import CACHE_BYTES, TileCache, tile_job, tile_reduction


def test_byte_limit(qapp):
    c = TileCache()
    for i in range(70):
        c.put(i, QPixmap(1024, 1024))
    assert c.bytes <= CACHE_BYTES == 256 * 1024 * 1024
    assert len(c) == 64
    assert 0 not in c and 69 in c  # 오래된 것부터 버린다


def test_markers_count_zero_bytes_and_item_limit(qapp):
    c = TileCache(max_items=10)
    for i in range(20):
        c.put(i, "sparse")
    assert c.bytes == 0 and len(c) == 10


def test_single_level_request_limit():
    c = TileCache()
    assert c.capacity(1024, 1024) == 64
    # 축소 타일 기준 용량: level_4(1024² 81장)를 4% 이하로 보면 64² 이하로 줄어 모두 들어간다
    assert c.capacity(64, 64) // 2 >= 81
    # level_0(20,306장) 맞춤 보기는 4² 수준이라 장 수 상한 안에 든다
    assert c.capacity(4, 4) // 2 >= 20306


def test_tile_reduction():
    assert tile_reduction(1.0, 1024) == 1
    assert tile_reduction(0.6, 1024) == 1
    assert tile_reduction(0.5, 1024) == 2
    assert tile_reduction(0.04, 1024) == 16  # 1024/16 = 64px, 화면 약 41px
    assert tile_reduction(1e-6, 1024) == 1024  # 1px 아래로는 줄이지 않는다


class _FakeSlide:
    def read_tile(self, level, x, y, z, path):
        return TileResult(np.full((1024, 1000, 3), 200, np.uint8), False)


def test_tile_job_reduces(qapp):
    status, img, _ = tile_job(_FakeSlide(), 0, 0, 0, None, None, 16)
    assert status == "ok" and (img.width(), img.height()) == (63, 64)  # 올림
    status, img, _ = tile_job(_FakeSlide(), 0, 0, 0, None, None)
    assert (img.width(), img.height()) == (1000, 1024)
