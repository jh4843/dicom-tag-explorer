# values 표시 문자열 단위 테스트 (TC-006, TC-007 Offset 형식 포함).
from __future__ import annotations

from pydicom.data import get_testdata_file

from dicom_factory import encapsulated_file, nested_file
from dicom_tag_explorer.core.dicom_file import DicomFile
from dicom_tag_explorer.core.element_index import K_BOT, K_ELEMENT, K_FRAGMENT, K_ITEM
from dicom_tag_explorer.core.values import (
    C_LEN, C_NAME, C_OFFSET, C_TAG, C_VALUE, C_VM, C_VR, format_offset, truncate,
)


def test_format_offset_width():
    assert format_offset(0x80, 0xFFFFFFFF) == "00000080"
    assert format_offset(0x80, 0x100000000) == "0000000080"
    assert len(format_offset(0xFFFFFFFF, 0x100000001)) == 10


def test_truncate():
    assert truncate("a" * 256) == "a" * 256
    assert truncate("a" * 300) == "a" * 256 + "…"


def test_columns_basic(tmp_path):
    f = DicomFile(nested_file(tmp_path / "n.dcm", undefined=True)).load()
    idx, fm = f.index, f.formatter
    pre = fm.columns(0)
    assert pre[C_TAG] == "Preamble" and pre[C_OFFSET] == "00000000" and pre[C_LEN] == "128"
    assert fm.columns(1)[C_TAG] == "DICM" and fm.columns(1)[C_OFFSET] == "00000080"
    pn = idx.find_child(-1, 0x00100010)
    c = fm.columns(pn)
    assert c[C_TAG] == "(0010,0010)" and c[C_VR] == "PN" and c[C_NAME] == "PatientName"
    assert c[C_VALUE] == "테스트^환자"  # ISO_IR 192 적용
    sq = idx.find_child(-1, 0x0040A043)
    c = fm.columns(sq)
    assert c[C_LEN] == "Undef." and c[C_VR] == "SQ"
    items = [k for k in idx.children(sq) if idx.kind[k] == K_ITEM]
    assert fm.columns(items[0])[C_TAG] == "Item #1"
    assert fm.columns(items[1])[C_TAG] == "Item #2"
    meaning = idx.find_child(items[0], 0x00080104)
    assert fm.columns(meaning)[C_VALUE] == "첫째"  # 상위 데이터셋 문자셋을 따른다


def test_private_names(tmp_path):
    f = DicomFile(nested_file(tmp_path / "n.dcm")).load()
    idx, fm = f.index, f.formatter
    assert fm.columns(idx.find_child(-1, 0x00090010))[C_NAME] == "PrivateCreator"
    assert fm.columns(idx.find_child(-1, 0x00091001))[C_NAME] == "TEST CREATOR"
    ob = fm.columns(idx.find_child(-1, 0x00091002))
    assert ob[C_VR] == "OB" and ob[C_VALUE] == "01 02 03 00"  # 짝수 길이 패딩


def test_implicit_unknown_private_is_un(tmp_path):
    f = DicomFile(nested_file(tmp_path / "i.dcm", undefined=False, implicit=True)).load()
    idx, fm = f.index, f.formatter
    c = fm.columns(idx.find_child(-1, 0x00091002))
    assert c[C_VR] == "UN"
    assert fm.columns(idx.find_child(-1, 0x00280010))[C_VR] == "US"


def test_encapsulated_values(tmp_path):
    f = DicomFile(encapsulated_file(tmp_path / "e.dcm", frames=3)).load()
    idx, fm = f.index, f.formatter
    px = idx.find_child(-1, 0x7FE00010)
    assert fm.columns(px)[C_VALUE] == "<Encapsulated 3 frames>"
    assert fm.columns(px)[C_LEN] == "Undef."
    idx.add_fragments(px, f.fragment_nodes(px))
    kids = idx.children(px)
    assert idx.kind[kids[0]] == K_BOT and fm.columns(kids[0])[C_VALUE] == "<Basic Offset Table 3 entries>"
    frag = kids[1]
    assert idx.kind[frag] == K_FRAGMENT
    assert fm.columns(frag)[C_TAG] == "Fragment #1"
    assert fm.columns(frag)[C_VALUE] == "<Fragment 10 bytes>"


def test_native_pixel_data_value():
    f = DicomFile(get_testdata_file("CT_small.dcm")).load()
    px = f.index.find_child(-1, 0x7FE00010)
    assert f.formatter.columns(px)[C_VALUE] == "<Native 32768 bytes>"


def test_deflate_offsets_dash():
    f = DicomFile(get_testdata_file("image_dfl.dcm")).load()
    idx, fm = f.index, f.formatter
    for i in range(len(idx)):
        if idx.kind[i] != K_ELEMENT:
            continue
        off = fm.columns(i)[C_OFFSET]
        if idx.tag[i] >> 16 == 2:
            assert off != "-"
        else:
            assert off == "-"


def test_tc006_label_sop_class(s_v_label, loader):
    f = loader(s_v_label)
    c = f.formatter.columns(f.index.find_child(-1, 0x00080016))
    assert (c[C_VR], c[C_VM], c[C_NAME], c[C_VALUE]) == ("UI", "1", "SOPClassUID", "1.2.840.10008.5.1.4.1.1.77.1.6")


def test_tc006_private_names_3dhistech(s_h, loader):
    f = loader(s_h / "000002.dcm")
    idx, fm = f.index, f.formatter
    names = []
    for i in range(len(idx)):
        if idx.kind[i] == K_ELEMENT and (idx.tag[i] >> 16) & 1 and (idx.tag[i] & 0xFFFF) >= 0x1000:
            names.append(fm.columns(i)[C_NAME])
    assert names
    assert all(n == "Private" or n.startswith("3DHISTECH") for n in names), set(names)


def test_all_label_columns_render(s_v_label, loader):
    f = loader(s_v_label)
    for i in range(len(f.index)):
        c = f.formatter.columns(i)
        assert len(c) == 7


def test_empty_basic_offset_table(tmp_path):
    f = DicomFile(encapsulated_file(tmp_path / "e.dcm", frames=2, has_bot=False)).load()
    px = f.index.find_child(-1, 0x7FE00010)
    f.index.add_fragments(px, f.fragment_nodes(px))
    assert f.formatter.columns(f.index.children(px)[0])[C_VALUE] == "<empty>"
