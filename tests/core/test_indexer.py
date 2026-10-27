# indexer 단위 테스트. pydicom 내장 파일, 생성 파일, 사내 샘플(TC-004, TC-007)을 쓴다.
from __future__ import annotations

import struct

import pytest
from pydicom.data import get_testdata_file

from dicom_factory import encapsulated_file, nested_file
from dicom_tag_explorer.core.dicom_file import DicomFile, FileState
from dicom_tag_explorer.core.element_index import (
    F_BIG, F_SEQ, F_UNDEF, F_VIRTUAL, K_BOT, K_ELEMENT, K_ERROR, K_FRAGMENT, K_ITEM, K_ITEM_DELIM,
    K_PREAMBLE, K_PREFIX, K_SEQ_DELIM, vr_str,
)

PYDICOM_FILES = ["MR_small_implicit.dcm", "CT_small.dcm", "image_dfl.dcm", "MR_small_bigendian.dcm",
                 "MR_small_RLE.dcm", "JPEG2000.dcm", "MR_small_jpeg_ls_lossless.dcm"]


def tag_at(f: DicomFile, nid: int) -> int:
    idx = f.index
    data = f.read(idx.start[nid], 4)
    fmt = ">HH" if idx.flags[nid] & F_BIG else "<HH"
    g, e = struct.unpack(fmt, data)
    return (g << 16) | e


def assert_offsets_match(f: DicomFile):
    idx = f.index
    n = 0
    for i in range(len(idx)):
        if idx.kind[i] == K_ELEMENT and not idx.flags[i] & F_VIRTUAL:
            assert tag_at(f, i) == idx.tag[i], f"node {i}"
            n += 1
    assert n > 0


def assert_tree_consistent(f: DicomFile):
    idx = f.index
    for i in range(len(idx)):
        p = idx.parent[i]
        assert idx.children(p)[idx.row[i]] == i
        if p >= 0:
            s, e = idx.start[p], idx.start[p] + idx.total_len[p]
            assert s <= idx.start[i] and idx.start[i] + idx.total_len[i] <= e


@pytest.mark.parametrize("name", PYDICOM_FILES)
def test_pydicom_files_index(name):
    f = DicomFile(get_testdata_file(name)).load()
    assert f.state == FileState.OK, f.error
    idx = f.index
    assert idx.kind[0] == K_PREAMBLE and idx.kind[1] == K_PREFIX
    assert_offsets_match(f)
    assert_tree_consistent(f)


def test_implicit_vr_from_dictionary():
    f = DicomFile(get_testdata_file("MR_small_implicit.dcm")).load()
    idx = f.index
    rows = idx.find_child(-1, 0x00280010)
    assert vr_str(idx.vr[rows]) == "US"
    assert idx.find_child(-1, 0x00080016) is not None


def test_big_endian_body_flags():
    f = DicomFile(get_testdata_file("MR_small_bigendian.dcm")).load()
    idx = f.index
    meta = idx.find_child(-1, 0x00020010)
    body = idx.find_child(-1, 0x00280010)
    assert not idx.flags[meta] & F_BIG
    assert idx.flags[body] & F_BIG


def test_deflate_meta_offsets_and_virtual_body():
    f = DicomFile(get_testdata_file("image_dfl.dcm")).load()
    idx = f.index
    assert f.transfer_syntax == "1.2.840.10008.1.2.1.99"
    for i in range(len(idx)):
        if idx.kind[i] != K_ELEMENT:
            continue
        if idx.tag[i] >> 16 == 0x0002:
            assert not idx.flags[i] & F_VIRTUAL
        else:
            assert idx.flags[i] & F_VIRTUAL
    # 압축된 본문 바이트는 어떤 노드에도 매핑되지 않는다
    last_meta = max(i for i in range(len(idx)) if idx.tag[i] >> 16 == 2 and idx.kind[i] == K_ELEMENT)
    body_off = idx.start[last_meta] + idx.total_len[last_meta] + 4
    assert idx.find(body_off) is None
    # 본문 값은 압축 해제 버퍼에서 읽는다
    assert f.summary.sop_class_uid


def test_undefined_length_sequence_nodes(tmp_path):
    f = DicomFile(nested_file(tmp_path / "n.dcm", undefined=True)).load()
    assert f.state == FileState.OK, f.error
    idx = f.index
    sq = idx.find_child(-1, 0x0040A043)
    assert idx.flags[sq] & F_UNDEF and idx.flags[sq] & F_SEQ
    kids = idx.children(sq)
    assert [idx.kind[k] for k in kids] == [K_ITEM, K_ITEM, K_SEQ_DELIM]
    item = kids[0]
    assert idx.flags[item] & F_UNDEF
    assert idx.kind[idx.children(item)[-1]] == K_ITEM_DELIM
    # SQ 범위는 Sequence Delimitation 끝까지
    sd = kids[-1]
    assert idx.start[sq] + idx.total_len[sq] == idx.start[sd] + 8
    assert_offsets_match(f)
    assert_tree_consistent(f)


@pytest.mark.parametrize("implicit", [False, True])
def test_defined_length_sequence(tmp_path, implicit):
    f = DicomFile(nested_file(tmp_path / "d.dcm", undefined=False, implicit=implicit)).load()
    assert f.state == FileState.OK, f.error
    idx = f.index
    sq = idx.find_child(-1, 0x0040A043)
    assert idx.flags[sq] & F_SEQ
    assert [idx.kind[k] for k in idx.children(sq)] == [K_ITEM, K_ITEM]
    assert_tree_consistent(f)


def test_undefined_length_un_parsed_as_sequence(tmp_path):
    p = nested_file(tmp_path / "u.dcm", undefined=True)
    data = bytearray(p.read_bytes())
    f = DicomFile(p).load()
    sq = f.index.find_child(-1, 0x0040A043)
    s = f.index.start[sq]
    assert data[s + 4:s + 6] == b"SQ"
    # 기존 SQ를 Undefined Length UN(내부는 Implicit VR LE, PS3.5 6.2.2)으로 바꾼 파일을 만든다
    implicit_item = struct.pack("<HHI", 0x0008, 0x0100, 2) + b"A1"
    item = struct.pack("<HHI", 0xFFFE, 0xE000, len(implicit_item)) + implicit_item
    un = struct.pack("<HH2sHI", 0x0040, 0xA043, b"UN", 0, 0xFFFFFFFF) + item + struct.pack("<HHI", 0xFFFE, 0xE0DD, 0)
    end = s + f.index.total_len[sq]
    new = bytes(data[:s]) + un + bytes(data[end:])
    q = tmp_path / "u2.dcm"
    q.write_bytes(new)
    g = DicomFile(q).load()
    assert g.state == FileState.OK, g.error
    sq2 = g.index.find_child(-1, 0x0040A043)
    assert g.index.flags[sq2] & F_SEQ
    item2 = g.index.children(sq2)[0]
    code = g.index.children(item2)[0]
    assert g.index.tag[code] == 0x00080100
    assert vr_str(g.index.vr[code]) == "SH"


def test_encapsulated_pixel_data_lazy_fragments(tmp_path):
    f = DicomFile(encapsulated_file(tmp_path / "e.dcm", frames=3)).load()
    idx = f.index
    px = idx.find_child(-1, 0x7FE00010)
    assert idx.needs_fragments(px)
    assert idx.has_children(px)
    assert idx.children(px) == []
    nodes = f.fragment_nodes(px)
    idx.add_fragments(px, nodes)
    kinds = [idx.kind[c] for c in idx.children(px)]
    assert kinds == [K_BOT, K_FRAGMENT, K_FRAGMENT, K_FRAGMENT, K_SEQ_DELIM]
    assert not idx.needs_fragments(px)
    assert_tree_consistent(f)


def test_truncated_file_is_damaged(tmp_path):
    p = nested_file(tmp_path / "n.dcm", undefined=True)
    data = p.read_bytes()
    q = tmp_path / "t.dcm"
    q.write_bytes(data[:-20])
    f = DicomFile(q).load()
    assert f.state == FileState.DAMAGED
    idx = f.index
    last = idx.children(-1)[-1]
    assert idx.kind[last] == K_ERROR
    assert len(idx) > 10
    assert_tree_consistent(f)


def test_not_dicom(tmp_path):
    q = tmp_path / "x.dcm"
    q.write_bytes(b"\0" * 300)
    f = DicomFile(q).load()
    assert f.state == FileState.FAILED
    assert "DICM" in f.error


def test_cancel_token(s_v_l0z0):
    class Tok:
        def is_cancelled(self):
            return True
    f = DicomFile(s_v_l0z0).load(Tok())
    assert f.state == FileState.CANCELLED


def test_korean_path(tmp_path):
    d = tmp_path / "한글 폴더"
    d.mkdir()
    f = DicomFile(nested_file(d / "파일 1.dcm")).load()
    assert f.state == FileState.OK


# ---- 사내 샘플 ----
def test_tc004_level0_structure(s_v_l0z0, loader):
    f = loader(s_v_l0z0)
    idx = f.index
    top = idx.children(-1)
    assert idx.kind[top[0]] == K_PREAMBLE and idx.kind[top[1]] == K_PREFIX
    pf = idx.find_child(-1, 0x52009230)
    items = [c for c in idx.children(pf) if idx.kind[c] == K_ITEM]
    assert len(items) == 20306
    px = idx.find_child(-1, 0x7FE00010)
    if idx.needs_fragments(px):
        idx.add_fragments(px, f.fragment_nodes(px))
    kinds = [idx.kind[c] for c in idx.children(px)]
    assert kinds.count(K_BOT) == 1 and kinds[0] == K_BOT
    assert kinds.count(K_FRAGMENT) == 20306
    assert kinds.count(K_SEQ_DELIM) == 1 and kinds[-1] == K_SEQ_DELIM
    assert len(kinds) == 20308


def test_tc007_offsets_match_tags(s_h, s_v_label, loader):
    for p in (s_h / "000005.dcm", s_v_label):
        f = loader(p)
        assert f.state == FileState.OK
        assert_offsets_match(f)
        assert_tree_consistent(f)


def test_all_samples_index_cleanly(s_h, s_v):
    for p in sorted(s_h.glob("*.dcm")) + sorted(s_v.iterdir()):
        f = DicomFile(p).load()
        assert f.state == FileState.OK, (p.name, f.error)


def test_qa01_fragment_indexing_does_not_block_reads(tmp_path, monkeypatch):
    """QA-01: Fragment 색인(백그라운드)이 도는 동안에도 UI 스레드의 read_raw/read/release가 기다리지 않는다."""
    import threading
    import time

    from dicom_tag_explorer.core import indexer
    monkeypatch.setattr(indexer, "CHECK_EVERY", 1)  # 항목마다 토큰을 확인하게 해 색인 도중에 멈춰 둔다
    f = DicomFile(encapsulated_file(tmp_path / "e.dcm", frames=3)).load()
    px = f.index.find_child(-1, 0x7FE00010)
    entered, go = threading.Event(), threading.Event()

    class PausingToken:
        def is_cancelled(self):
            entered.set()
            go.wait(5)
            return False

    result = []
    th = threading.Thread(target=lambda: result.append(f.fragment_nodes(px, PausingToken())))
    th.start()
    try:
        assert entered.wait(5)
        t0 = time.perf_counter()
        assert f.read_raw(128, 4) == b"DICM"
        assert f.read(128, 4) == b"DICM"
        f.release()  # 파일 닫기·전환 시 호출된다. 진행 중인 색인을 깨뜨리지 않아야 한다
        assert time.perf_counter() - t0 < 1.0
    finally:
        go.set()
        th.join(10)
    f.index.add_fragments(px, result[0])
    assert [f.index.kind[c] for c in f.index.children(px)] == [K_BOT, K_FRAGMENT, K_FRAGMENT, K_FRAGMENT, K_SEQ_DELIM]
