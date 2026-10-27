# wsidicom 어댑터 단위 테스트 (TC-028, TC-030).
from __future__ import annotations

import pytest

from dicom_tag_explorer.core.wsi import Slide, TileError


@pytest.fixture(scope="module")
def slide_v(s_v):
    s = Slide.open(sorted(s_v.glob("*.dcm")))
    yield s
    s.close()


def test_tc028_levels_and_focal_planes(slide_v, s_h):
    assert len(slide_v.levels) == 9
    assert slide_v.focal_planes == [0.0, 1.0]
    assert slide_v.default_z == 0.0
    assert [l.index for l in slide_v.levels] == list(range(9))
    assert slide_v.levels[0].downsample == 1.0
    assert slide_v.levels[1].downsample == pytest.approx(2.0, rel=0.01)
    h = Slide.open(sorted(s_h.glob("*.dcm")))
    try:
        assert len(h.levels) == 10
    finally:
        h.close()


def test_tc030_read_tile(slide_v):
    for z in (0.0, 1.0):
        r = slide_v.read_tile(0, 10, 10, z=z)
        assert not r.sparse
        assert r.array.shape == (1024, 1024, 3)
    with pytest.raises(TileError):
        slide_v.read_tile(0, 10_000, 0)


def test_best_level(slide_v):
    assert slide_v.best_level(1.0) == 0
    assert slide_v.best_level(0.5) == 1
    assert slide_v.best_level(0.3) == 1
    assert slide_v.best_level(0.0001) == 8


def test_single_volume_file(s_v):
    p = sorted(s_v.glob("*_z_0_level_3.dcm"))[0]
    s = Slide.open([p])
    try:
        assert len(s.levels) == 1
        assert not s.read_tile(0, 0, 0).sparse
    finally:
        s.close()


def test_qa04_per_frame_sequences_released_and_tiles_unchanged(s_v):
    """QA-04: 열린 슬라이드는 TILED_SPARSE 타일 색인을 만든 뒤 Per-Frame Functional Groups Sequence를 붙잡지 않는다.
    타일 내용과 sparse 판정은 wsidicom을 그대로 쓴 결과와 같다."""
    import numpy as np
    from wsidicom import WsiDicom
    from wsidicom.geometry import Point

    paths = sorted(s_v.glob("*.dcm"))
    s = Slide.open(paths)
    ref = WsiDicom.open(paths)
    try:
        # 개수만 비교한다 (실패 메시지에 샘플 UID가 찍히지 않게)
        kept = sum(1 for lvl in s._wsi.levels for inst in lvl.instances.values() for ds in inst.image_data._datasets
                   if "PerFrameFunctionalGroupsSequence" in ds or "frame_sequence" in ds.__dict__)
        assert kept == 0
        ref_levels = sorted(ref.levels, key=lambda l: l.size.width * l.size.height, reverse=True)
        for info in s.levels:
            tx, ty = info.tiles
            for z in s.focal_planes:
                for x, y in {(0, 0), (tx // 2, ty // 2), (tx - 1, ty - 1)}:
                    r = s.read_tile(info.index, x, y, z=z)
                    inst = ref_levels[info.index].get_instance(z, s.default_path)
                    sparse = bool(inst.image_data.is_sparse(Point(x, y), z, s.default_path))
                    assert r.sparse == sparse, (info.index, x, y, z)
                    if not sparse:
                        want = np.asarray(ref.read_tile(ref_levels[info.index].level, (x, y), z, s.default_path).convert("RGB"))
                        assert np.array_equal(r.array, want), (info.index, x, y, z)
    finally:
        s.close()
        ref.close()
