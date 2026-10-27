# 열기 대상 경로를 펼친다. 폴더는 재귀 탐색하고 오프셋 128의 'DICM'으로 DICOM을 판별한다.
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .dicom_file import normalize_path
from .indexer import MSG_NOT_DICOM, Cancelled

MSG_NOT_FOUND = "Path not found"


@dataclass
class ScanResult:
    files: list[Path] = field(default_factory=list)
    errors: list[tuple[Path, str]] = field(default_factory=list)


def is_dicom_file(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            head = fh.read(132)
    except OSError:
        return False
    return len(head) == 132 and head[128:132] == b"DICM"


def expand_paths(paths, token=None) -> ScanResult:
    """파일과 폴더가 섞인 목록을 DICOM 파일 목록으로 펼친다. 결과는 정규화 경로로 중복 제거된다.

    폴더 안의 DICOM이 아닌 파일은 조용히 건너뛰고, 직접 지정한 파일이 DICOM이 아니면 오류로 기록한다.
    """
    res = ScanResult()
    seen: set[Path] = set()

    def add(p: Path):
        k = normalize_path(p)
        if k not in seen:
            seen.add(k)
            res.files.append(Path(os.path.abspath(p)))

    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            for root, dirs, files in os.walk(p):
                if token is not None and token.is_cancelled():
                    raise Cancelled()
                dirs.sort(key=str.lower)
                for name in sorted(files, key=str.lower):
                    fp = Path(root) / name
                    if is_dicom_file(fp):
                        add(fp)
        elif p.is_file():
            if is_dicom_file(p):
                add(p)
            else:
                res.errors.append((p, MSG_NOT_DICOM))
        else:
            res.errors.append((p, MSG_NOT_FOUND))
    return res
