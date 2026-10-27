# pyside6-lupdate로 .ts를 갱신하고(update), pyside6-lrelease로 .qm을 만든다(release). 한국어 미완료 항목이 있으면 실패한다.
"""사용법:
    python scripts/i18n.py update              # src/dicom_tag_explorer 전체에서 문자열을 추출해 두 .ts를 갱신
    python scripts/i18n.py release             # .qm 생성. dicom_tag_explorer_ko.ts에 unfinished가 있으면 종료 코드 1
    python scripts/i18n.py release --ts DIR    # 다른 폴더의 .ts로 검사·생성 (테스트용)

Spec v0.1.0 2.8.3, SPEC-034. 도구는 PySide6-Essentials에 들어 있는 pyside6-lupdate / pyside6-lrelease이다.
"""
from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "dicom_tag_explorer"
I18N = PKG / "ui" / "resources" / "i18n"
KO, EN = "dicom_tag_explorer_ko.ts", "dicom_tag_explorer_en.ts"


def tool(name: str) -> str:
    p = Path(sys.executable).parent / f"{name}.exe"
    return str(p) if p.exists() else name


def sources() -> list[str]:
    return [str(p) for p in sorted(PKG.rglob("*.py")) if "__pycache__" not in p.parts]


def lupdate(ts: Path, plural_only: bool = False) -> None:
    cmd = [tool("pyside6-lupdate"), *sources(), "-no-obsolete", "-ts", str(ts)]
    if plural_only:
        cmd.insert(1, "-pluralonly")
    subprocess.run(cmd, check=True)


def unfinished(ts: Path) -> list[str]:
    """번역이 없거나 unfinished로 표시된 원문 목록."""
    out = []
    for ctx in ET.parse(ts).getroot().iter("context"):
        cname = ctx.findtext("name")
        for m in ctx.iter("message"):
            t = m.find("translation")
            if t is None or t.get("type") in ("unfinished", "obsolete", "vanished"):
                if t is not None and t.get("type") in ("obsolete", "vanished"):
                    continue
                out.append(f"{cname}: {m.findtext('source')}")
            elif m.get("numerus") == "yes":
                if not [n for n in t.iter("numerusform") if (n.text or "").strip()]:
                    out.append(f"{cname}: {m.findtext('source')}")
            elif not (t.text or "").strip():
                out.append(f"{cname}: {m.findtext('source')}")
    return out


def release(ts_dir: Path = I18N, out_dir: Path | None = None) -> int:
    out_dir = out_dir or ts_dir
    missing = unfinished(ts_dir / KO)
    if missing:
        print(f"한국어 번역 미완료 {len(missing)}건 ({KO}):")
        for m in missing[:50]:
            print("  -", m)
        return 1
    for name in (KO, EN):
        qm = out_dir / name.replace(".ts", ".qm")
        subprocess.run([tool("pyside6-lrelease"), str(ts_dir / name), "-qm", str(qm)], check=True,
                       stdout=subprocess.DEVNULL)
        print("생성:", qm)
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("update", "release"):
        print(__doc__)
        return 2
    if argv[0] == "update":
        I18N.mkdir(parents=True, exist_ok=True)
        lupdate(I18N / KO)
        lupdate(I18N / EN, plural_only=True)
        return 0
    ts_dir = Path(argv[argv.index("--ts") + 1]) if "--ts" in argv else I18N
    return release(ts_dir)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
