# 폴더 재귀 탐색과 DICM 판별 단위 테스트 (TC-018).
from __future__ import annotations

from dicom_factory import nested_file
from dicom_tag_explorer.core.scan import expand_paths


def test_recursive_scan_and_errors(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    nested_file(tmp_path / "a" / "x.dcm")
    nested_file(tmp_path / "a" / "b" / "no_ext")
    (tmp_path / "a" / "readme.txt").write_text("hello")
    (tmp_path / "a" / "b" / "fake.dcm").write_bytes(b"\0" * 200)
    zipf = tmp_path / "z.zip"
    zipf.write_bytes(b"PK\x03\x04" + b"\0" * 200)
    res = expand_paths([tmp_path / "a", zipf, tmp_path / "a" / "x.dcm", tmp_path / "missing"])
    names = [p.name for p in res.files]
    assert names == ["x.dcm", "no_ext"]  # 같은 파일 중복 없음, 확장자 무관
    errs = {p.name: r for p, r in res.errors}
    assert "DICM" in errs["z.zip"]
    assert "missing" in errs


def test_tc018_samples(samples_dir):
    res = expand_paths([samples_dir])
    assert len(res.files) == 35
    assert not any(p.suffix == ".zip" for p in res.files)
    assert res.errors == []
