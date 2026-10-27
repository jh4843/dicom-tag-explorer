# exe에 내장된 THIRD_PARTY_NOTICES.txt를 찾아 읽고 '=====' 머리줄로 섹션을 나눈다 (정보 창용).
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

FILE_NAME = "THIRD_PARTY_NOTICES.txt"
HEADER_RE = re.compile(r"^===== (?P<name>.+) (?P<version>\S+) \((?P<license>.+)\) =====$")
MSG_DEV = "The notices file is not available when running from source. Check it in the build output."


@dataclass
class Section:
    name: str
    version: str
    license: str
    text: str


def notices_path() -> Path | None:
    """빌드 산출물(onefile: _MEIPASS, onedir: _internal)에서만 찾는다. 소스 실행이면 None."""
    if not getattr(sys, "frozen", False):
        return None
    base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    p = base / FILE_NAME
    return p if p.is_file() else None


def parse(text: str) -> tuple[str, list[Section]]:
    """(머리말, 섹션 목록)."""
    head: list[str] = []
    sections: list[Section] = []
    cur: Section | None = None
    buf: list[str] = []
    for line in text.splitlines():
        m = HEADER_RE.match(line)
        if m:
            if cur is not None:
                cur.text = "\n".join(buf).strip()
                sections.append(cur)
            cur = Section(m["name"], m["version"], m["license"], "")
            buf = []
        elif cur is None:
            head.append(line)
        else:
            buf.append(line)
    if cur is not None:
        cur.text = "\n".join(buf).strip()
        sections.append(cur)
    return "\n".join(head).strip(), sections


def load() -> tuple[str, list[Section]] | None:
    p = notices_path()
    if p is None:
        return None
    return parse(p.read_text(encoding="utf-8"))
