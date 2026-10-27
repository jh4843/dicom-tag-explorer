# ElementIndex 역매핑 단위 테스트 (TC-010 포함).
from __future__ import annotations

from dicom_factory import encapsulated_file, nested_file
from dicom_tag_explorer.core.dicom_file import DicomFile
from dicom_tag_explorer.core.element_index import (
    K_FRAGMENT, K_ITEM_DELIM, K_PREAMBLE, K_PREFIX, K_SEQ_DELIM,
)


def assert_start_maps_to_self(f: DicomFile):
    idx = f.index
    for i in range(len(idx)):
        if idx.is_virtual(i) or idx.total_len[i] == 0:
            continue
        assert idx.find(idx.start[i]) == i, i


def test_find_preamble_prefix_and_bounds(tmp_path):
    f = DicomFile(nested_file(tmp_path / "n.dcm")).load()
    idx = f.index
    for off in (0, 64, 127):
        assert idx.kind[idx.find(off)] == K_PREAMBLE
    for off in (128, 131):
        assert idx.kind[idx.find(off)] == K_PREFIX
    assert idx.find(-1) is None
    assert idx.find(idx.file_size) is None


def test_delimiter_bytes_map_to_delimiter_nodes(tmp_path):
    f = DicomFile(nested_file(tmp_path / "n.dcm", undefined=True)).load()
    idx = f.index
    delims = [i for i in range(len(idx)) if idx.kind[i] in (K_ITEM_DELIM, K_SEQ_DELIM)]
    assert delims
    for d in delims:
        for k in range(8):
            assert idx.find(idx.start[d] + k) == d
    assert_start_maps_to_self(f)


def test_every_byte_of_value_maps_to_deepest(tmp_path):
    f = DicomFile(nested_file(tmp_path / "n.dcm", undefined=True)).load()
    idx = f.index
    for off in range(132, idx.file_size):
        n = idx.find(off)
        assert n is not None
        # 더 깊은 자식 중 이 오프셋을 포함하는 노드가 없어야 한다
        assert not any(idx.contains(c, off) for c in idx.children(n))


def test_fragment_mapping_before_and_after_index(tmp_path):
    f = DicomFile(encapsulated_file(tmp_path / "e.dcm", frames=2)).load()
    idx = f.index
    px = idx.find_child(-1, 0x7FE00010)
    inside = idx.start[px] + idx.header_len[px] + 8 + 3
    assert idx.find(inside) == px
    idx.add_fragments(px, f.fragment_nodes(px))
    frag = [c for c in idx.children(px) if idx.kind[c] == K_FRAGMENT][0]
    assert idx.find(idx.start[frag] + 9) == frag
    assert idx.depth_path(frag) == [px, frag]
    assert_start_maps_to_self(f)


def test_tc010_label_and_dicomdir(s_v_label, s_v_dd, loader):
    for p in (s_v_label, s_v_dd):
        f = loader(p)
        assert_start_maps_to_self(f)
        idx = f.index
        assert idx.kind[idx.find(10)] == K_PREAMBLE
        for i in range(len(idx)):
            if idx.kind[i] in (K_ITEM_DELIM, K_SEQ_DELIM):
                assert idx.find(idx.start[i] + 7) == i
