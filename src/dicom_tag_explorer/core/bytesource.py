# 파일을 읽기 전용 mmap으로 열어 범위 읽기와 파일 크기를 제공하는 래퍼.
from __future__ import annotations

import mmap
import os
from pathlib import Path


class ByteSource:
    """읽기 전용 mmap 래퍼. 파일 전체를 메모리에 올리지 않고 필요한 범위만 읽는다."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._fh = open(self.path, "rb")
        self.size = self.path.stat().st_size
        self._mm: mmap.mmap | None = None
        if self.size > 0:
            self._mm = mmap.mmap(self._fh.fileno(), 0, access=mmap.ACCESS_READ)

    @property
    def buffer(self):
        """struct.unpack_from에 바로 넘길 수 있는 버퍼. 빈 파일이면 b''."""
        return self._mm if self._mm is not None else b""

    def read(self, offset: int, length: int) -> bytes:
        if self._mm is None or offset >= self.size or length <= 0:
            return b""
        offset = max(0, offset)
        return self._mm[offset:min(self.size, offset + length)]

    def close(self) -> None:
        if self._mm is not None:
            self._mm.close()
            self._mm = None
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    @property
    def closed(self) -> bool:
        return self._fh is None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class FileReader:
    """파일 읽기로 범위를 읽는 버퍼 대용 (len, 슬라이스만). mmap 페이지 폴트는 GIL을 쥔 채 디스크를 기다리지만
    파일 읽기는 시스템 호출 동안 GIL을 놓는다. OS 캐시가 빈 큰 파일을 백그라운드에서 훑을 때 UI 스레드가 멈추지 않는다 (QA-01).
    한 스레드에서만 쓴다."""

    def __init__(self, path: Path | str):
        self._fh = open(Path(path), "rb", buffering=0)
        self.size = os.fstat(self._fh.fileno()).st_size

    def __len__(self) -> int:
        return self.size

    def __getitem__(self, s: slice) -> bytes:
        self._fh.seek(s.start)
        return self._fh.read(s.stop - s.start)

    def close(self) -> None:
        self._fh.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
