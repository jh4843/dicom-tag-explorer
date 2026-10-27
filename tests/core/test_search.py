# 통합·상세 검색 단위 테스트 (TC-014, TC-016).
from __future__ import annotations

import pytest

from dicom_factory import nested_file
from dicom_tag_explorer.core.dicom_file import DicomFile
from dicom_tag_explorer.core.indexer import Cancelled
from dicom_tag_explorer.core.search import Criteria, compile_criteria, normalize_tag, search


def run(f, **kw):
    return search(f.index, f.formatter, compile_criteria(Criteria(**kw)))


@pytest.fixture
def nf(tmp_path):
    return DicomFile(nested_file(tmp_path / "n.dcm", undefined=True)).load()


def test_normalize_tag():
    for s in ("0010,0010", "00100010", "(0010,0010)", " (0010, 0010) "):
        assert normalize_tag(s) == "00100010"
    assert normalize_tag("0010") == "0010"
    assert normalize_tag("XYZ") is None
    assert normalize_tag("001000100") is None


def test_text_search_all_columns(nf):
    hits = run(nf, text="patientname")
    assert [nf.index.tag[i] for i in hits] == [0x00100010]  # Name, 대소문자 무시
    assert run(nf, text="PatientName", match_case=True) == hits
    assert run(nf, text="patientname", match_case=True) == []
    # 접힌 Item 안의 값도 찾는다
    assert len(run(nf, text="첫째")) == 1
    assert len(run(nf, text="(0008,0100)")) == 2


def test_advanced_and(nf):
    assert len(run(nf, tag="0008,0100")) == 2
    assert len(run(nf, tag="0008,0100", value="B2")) == 1
    assert len(run(nf, tag="0008,0100", value="B2", text="A1")) == 0
    assert len(run(nf, vr="sq")) == 1
    assert len(run(nf, vr="SQ", length="0")) == 0
    hits = run(nf, offset="0x80")
    assert [nf.index.kind[i] for i in hits] == [1]  # DICM 노드
    assert run(nf, name="^Code", regex=True)


def test_invalid_fields_are_excluded(nf):
    c = compile_criteria(Criteria(tag="zz", vm="a", length="1.5", offset="0xg", vr="P", value="B2"))
    assert set(c.errors) == {"tag", "vm", "length", "offset", "vr"}
    assert len(search(nf.index, nf.formatter, c)) == 1  # Value 조건만 남는다
    c = compile_criteria(Criteria(value="(", regex=True))
    assert "value" in c.errors and not c.active


def test_cancel(nf):
    class Tok:
        def is_cancelled(self):
            return True
    with pytest.raises(Cancelled):
        search(nf.index, nf.formatter, compile_criteria(Criteria(text="x")), Tok())


def test_tc014_unified(s_v_label, s_v_l0z0, loader):
    f = loader(s_v_label)
    assert len(run(f, text="77.1.6")) == 2
    g = loader(s_v_l0z0)
    assert len(run(g, text="ZOffsetInSlideCoordinateSystem")) == 20307


def test_tc016_advanced(s_v_l0z0, s_v_l0z1, loader):
    z1, z0 = loader(s_v_l0z1), loader(s_v_l0z0)
    assert len(run(z1, tag="0040,074A", value="1")) == 20307
    assert len(run(z0, tag="0040,074A", value="1")) == 0
    assert len(run(z1, tag="0040,074A", value=r"^1\.0+$", regex=True)) == 20307
    # 형식이 틀린 TAG는 조건에서 제외되어 Value 정규식만 남는다
    assert len(run(z1, tag="00G0", value=r"^1\.0+$", regex=True)) >= 20307


def test_tc052_full_value_and_option_scope(tmp_path):
    from dicom_factory import long_text_file
    value = "A" * 280 + "NeedleTail" + "B" * 10  # 300자
    f = DicomFile(long_text_file(tmp_path / "lt.dcm", value)).load()
    lt = [f.index.find_child(-1, 0x00204000)]
    assert run(f, text="NeedleTail") == lt  # 256자 절단값이 아니라 전체 값
    assert run(f, text="needletail") == lt
    assert run(f, text="needletail", match_case=True) == []  # 통합 검색에 적용
    assert run(f, value="needletail", match_case=True) == []  # Value에 적용
    assert run(f, name="imagecomments", match_case=True) == []  # Name에 적용
    assert len(run(f, name="ImageComments", match_case=True)) == 1
    for case in (False, True):  # TAG는 형식 비교라 옵션과 무관하다
        assert run(f, tag="0020,4000", match_case=case) == run(f, tag="0020,4000") == lt
    px_upper = run(f, tag="7FE0,0010", match_case=True)
    assert px_upper == run(f, tag="7fe0,0010", match_case=True) == run(f, tag="7fe0,0010")
