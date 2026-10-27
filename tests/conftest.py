# 사내 샘플 경로 픽스처와 공통 로더. 샘플이 없으면 해당 테스트를 skip한다.
from __future__ import annotations

import os
from pathlib import Path

import pytest

from dicom_tag_explorer.core.dicom_file import DicomFile

DEFAULT_SAMPLES = Path(r"E:\JaeHyeokDoc\#1_Pathology\03_Images\DICOM")


def _samples_root() -> Path | None:
    env = os.environ.get("VW_SAMPLES_DIR")
    for p in ([Path(env)] if env else []) + [DEFAULT_SAMPLES]:
        if p.is_dir():
            return p
    return None


@pytest.fixture(scope="session")
def samples_dir() -> Path:
    root = _samples_root()
    if root is None:
        pytest.skip("사내 샘플 폴더가 없습니다 (VW_SAMPLES_DIR)")
    return root


@pytest.fixture(scope="session")
def s_h(samples_dir) -> Path:
    p = samples_dir / "3DHISTECH-1"
    if not p.is_dir():
        pytest.skip("S-H 샘플 없음")
    return p


@pytest.fixture(scope="session")
def s_v(samples_dir) -> Path:
    # 케이스 번호가 들어간 폴더 이름을 코드에 남기지 않도록 DICOMDIR 위치로 찾는다
    for dd in sorted(samples_dir.glob("*/*/DICOMDIR")):
        p = dd.parent
        if any(p.glob("*_z_1_level_0.dcm")):
            return p
    pytest.skip("S-V 샘플 없음")


def _one(folder: Path, pattern: str) -> Path:
    m = sorted(folder.glob(pattern))
    if not m:
        pytest.skip(f"샘플 파일 없음: {pattern}")
    return m[0]


@pytest.fixture(scope="session")
def s_v_label(s_v) -> Path:
    return _one(s_v, "*_label.dcm")


@pytest.fixture(scope="session")
def s_v_overview(s_v) -> Path:
    return _one(s_v, "*_overview.dcm")


@pytest.fixture(scope="session")
def s_v_l0z0(s_v) -> Path:
    return _one(s_v, "*_z_0_level_0.dcm")


@pytest.fixture(scope="session")
def s_v_l0z1(s_v) -> Path:
    return _one(s_v, "*_z_1_level_0.dcm")


@pytest.fixture(scope="session")
def s_v_dd(s_v) -> Path:
    return _one(s_v, "DICOMDIR")


_loaded: dict[Path, DicomFile] = {}


def load(path: Path) -> DicomFile:
    """세션 동안 같은 파일의 색인을 재사용한다."""
    path = Path(path)
    f = _loaded.get(path)
    if f is None:
        f = DicomFile(path).load()
        _loaded[path] = f
    return f


@pytest.fixture(scope="session")
def loader():
    return load
