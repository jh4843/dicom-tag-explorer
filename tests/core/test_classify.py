# 분류·WSI 그룹핑 단위 테스트 (TC-001, TC-022).
from __future__ import annotations

from collections import Counter

from pydicom.data import get_testdata_file

from dicom_factory import WSI_SOP, make_dataset, write
from dicom_tag_explorer.core.classify import category, file_info, group_files
from dicom_tag_explorer.core.dicom_file import DicomFile


def wsi_file(path, kind, size, z=None, study="1.2.3", series="1.2.3.4", container="SLIDE-T", op="1"):
    ds = make_dataset(sop_class=WSI_SOP)
    ds.StudyInstanceUID = study
    ds.SeriesInstanceUID = series
    ds.ImageType = ["ORIGINAL", "PRIMARY", kind, "NONE"]
    ds.TotalPixelMatrixColumns, ds.TotalPixelMatrixRows = size
    ds.Columns = ds.Rows = 256
    ds.ContainerIdentifier = container
    from pydicom.dataset import Dataset
    op_item = Dataset()
    op_item.OpticalPathIdentifier = op
    ds.OpticalPathSequence = [op_item]
    if z is not None:
        pp = Dataset()
        pp.ZOffsetInSlideCoordinateSystem = z
        fg = Dataset()
        fg.PlanePositionSlideSequence = [pp]
        ds.SharedFunctionalGroupsSequence = [fg]
    return DicomFile(write(ds, path)).load()


def test_grouping_and_labels_generated(tmp_path):
    files = [
        wsi_file(tmp_path / "a.dcm", "LABEL", (100, 50)),
        wsi_file(tmp_path / "b.dcm", "VOLUME", (1000, 800), z=1.0),
        wsi_file(tmp_path / "c.dcm", "VOLUME", (2000, 1600), z=1.0),
        wsi_file(tmp_path / "d.dcm", "VOLUME", (2000, 1600), z=0.0),
        wsi_file(tmp_path / "e.dcm", "LOCALIZER", (10, 10)),
        wsi_file(tmp_path / "f.dcm", "VOLUME", (1000, 800), z=0.0),
        wsi_file(tmp_path / "g.dcm", "THUMBNAIL", (50, 40)),
        wsi_file(tmp_path / "h.dcm", "VOLUME", (500, 400), series="9.9"),
        DicomFile(get_testdata_file("CT_small.dcm")).load(),
    ]
    groups, non_wsi = group_files(files)
    assert len(groups) == 2 and len(non_wsi) == 1
    g = groups[0]
    assert g.name == "SLIDE-T"
    assert [i.label for i in g.instances] == [
        "VOLUME   L0 z0", "VOLUME   L0 z1", "VOLUME   L1 z0", "VOLUME   L1 z1",
        "LABEL", "THUMBNAIL", "LOCALIZER"]
    assert g.z_values == [0.0, 1.0]
    assert groups[1].instances[0].level_label == "L0"
    assert category(files[4]) == "OTHER"
    assert file_info(files[8]) == "CT Image Storage"
    assert file_info(files[1]) == "VOLUME  1000x800"


def test_optical_path_label(tmp_path):
    files = [wsi_file(tmp_path / "a.dcm", "VOLUME", (100, 100), op="A"),
             wsi_file(tmp_path / "b.dcm", "VOLUME", (100, 100), op="B")]
    g = group_files(files)[0][0]
    assert [i.level_label for i in g.instances] == ["L0 OP A", "L0 OP B"]


def test_tc001_classification(s_h, s_v, loader):
    h = Counter(category(loader(p)) for p in sorted(s_h.glob("*.dcm")))
    assert h == Counter({"VOLUME": 10, "LABEL": 1, "OVERVIEW": 1, "OTHER": 2})
    others = sorted(loader(p).summary.image_type3 for p in s_h.glob("*.dcm")
                    if category(loader(p)) == "OTHER")
    assert others == ["LOCALIZER", "REGIONLOCALIZER"]
    v = Counter(category(loader(p)) for p in sorted(s_v.glob("*.dcm")))
    assert v == Counter({"VOLUME": 18, "LABEL": 1, "OVERVIEW": 1})


def test_tc022_grouping(s_h, s_v, loader):
    files = [loader(p) for p in sorted(s_h.glob("*.dcm")) + sorted(s_v.glob("*.dcm"))]
    groups, non_wsi = group_files(files)
    assert [len(g.instances) for g in groups] == [14, 20]
    gh, gv = groups
    vols_v = [i.label.split(None, 1)[1] for i in gv.instances if i.category == "VOLUME"]
    assert vols_v == [f"L{l} z{z}" for l in range(9) for z in (0, 1)]
    vols_h = [i.level_label for i in gh.instances if i.category == "VOLUME"]
    assert vols_h == [f"L{l}" for l in range(10)]
    assert [i.category for i in gh.instances][-2:] == ["OTHER", "OTHER"]
    assert [i.category for i in gv.instances][-2:] == ["LABEL", "OVERVIEW"]
