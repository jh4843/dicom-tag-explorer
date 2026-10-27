# DICOMDIR 레코드 트리 단위 테스트 (TC-023).
from __future__ import annotations

from pydicom.data import get_testdata_file
from pydicom.fileset import FileSet

from dicom_factory import make_dataset
from dicom_tag_explorer.core.dicom_file import DicomFile
from dicom_tag_explorer.core.dicomdir import build_records, iter_records


def _types(recs):
    return [r.record_type for r in iter_records(recs)]


def test_generated_dicomdir_missing_file(tmp_path):
    fs = FileSet()
    for k in range(3):
        ds = make_dataset()
        ds.PatientName = "Test^Dummy"
        ds.PatientID = "T0"
        ds.StudyInstanceUID = "1.2.3"
        ds.SeriesInstanceUID = "1.2.3.4"
        ds.StudyDate = "20260101"
        ds.StudyTime = "000000"
        ds.StudyID = "1"
        ds.AccessionNumber = ""
        ds.Modality = "OT"
        ds.SeriesNumber = 1
        ds.InstanceNumber = k + 1
        fs.add(ds)
    out = tmp_path / "disk"
    fs.write(out)
    dd = out / "DICOMDIR"
    f = DicomFile(dd).load()
    recs = build_records(f)
    assert _types(recs) == ["PATIENT", "STUDY", "SERIES", "IMAGE", "IMAGE", "IMAGE"]
    images = [r for r in iter_records(recs) if r.record_type == "IMAGE"]
    assert all(r.exists for r in images)
    images[1].ref_path.unlink()
    recs = build_records(DicomFile(dd).load())
    images = [r for r in iter_records(recs) if r.record_type == "IMAGE"]
    assert [r.exists for r in images] == [True, False, True]
    assert images[1].info == "File not found"
    assert recs[0].name == "Test^Dummy" and recs[0].info == "ID T0"


def test_pydicom_dicomdir_offsets_are_items():
    f = DicomFile(get_testdata_file("DICOMDIR")).load()
    recs = build_records(f)
    assert recs
    for r in iter_records(recs):
        assert f.read(r.offset, 4) == b"\xfe\xff\x00\xe0"


def test_tc023_sample_dicomdir(s_v_dd, loader):
    f = loader(s_v_dd)
    recs = build_records(f)
    assert len(recs) == 1 and recs[0].record_type == "PATIENT"
    st = recs[0].children
    assert len(st) == 1 and st[0].record_type == "STUDY"
    se = st[0].children
    assert len(se) == 1 and se[0].record_type == "SERIES"
    im = se[0].children
    assert len(im) == 20 and all(r.record_type == "IMAGE" for r in im)
    for r in iter_records(recs):
        assert f.read(r.offset, 4) == b"\xfe\xff\x00\xe0"
    assert all(r.exists for r in im)
