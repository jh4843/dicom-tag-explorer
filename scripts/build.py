# onedir로 빌드하고 LGPL 보완 문서와 함께 배포 zip을 만든다 (Spec v0.1.0 2.7).
"""사용법: .venv\\Scripts\\python scripts\\build.py

저장소 루트 .venv(전역 site-packages 미포함)에서 실행한다. 다른 인터프리터로 실행하면 중단한다.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dicom_tag_explorer import __version__ as VERSION  # noqa: E402

SPEC = ROOT / "packaging" / "dicom_tag_explorer.spec"
BUILD = ROOT / "build"
DIST = ROOT / "dist"
APP = "DicomTagExplorer"
RELEASE = f"DICOM-Tag-Explorer-{VERSION}-win64"
LICENSES = ["LGPL-3.0.txt", "GPL-3.0.txt"]

VERSION_INFO = """# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
                    date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041204B0', [
      StringStruct('CompanyName', 'Vieworks'),
      StringStruct('FileDescription', 'DICOM Tag Explorer'),
      StringStruct('FileVersion', '{v}'),
      StringStruct('InternalName', '{app}'),
      StringStruct('OriginalFilename', '{app}.exe'),
      StringStruct('ProductName', 'DICOM Tag Explorer'),
      StringStruct('ProductVersion', '{v}')])]),
    VarFileInfo([VarStruct('Translation', [0x0412, 1200])])
  ]
)
"""


def check_env() -> None:
    venv = (ROOT / ".venv").resolve()
    if Path(sys.prefix).resolve() != venv:
        raise SystemExit(f"저장소 .venv에서 실행하세요 (현재 {sys.prefix})")
    cfg = (venv / "pyvenv.cfg").read_text(encoding="utf-8")
    if "include-system-site-packages = false" not in cfg:
        raise SystemExit(".venv가 전역 site-packages를 포함합니다")


def clean_path() -> str:
    """PATH의 다른 프로그램 폴더(JDK 등)에서 DLL이 끌려오지 않게 최소 PATH로 빌드한다."""
    win = os.environ.get("SystemRoot", r"C:\Windows")
    return os.pathsep.join([str(Path(sys.executable).parent), sys.base_prefix,
                            os.path.join(win, "System32"), win])


def prepare() -> Path:
    """번들 준비 (Spec 2.7): 번역 .qm 생성, 토큰 검사, build_info.json."""
    py = sys.executable
    if subprocess.run([py, str(ROOT / "scripts" / "i18n.py"), "release"], cwd=ROOT).returncode != 0:
        raise SystemExit("번역 .qm 생성 실패 (한국어 미완료 항목이 있으면 실패한다)")
    if subprocess.run([py, str(ROOT / "scripts" / "gen_tokens.py"), "--check"], cwd=ROOT).returncode != 0:
        raise SystemExit("design_tokens.py가 tokens.json과 다릅니다")
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                                text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                               capture_output=True, text=True).stdout.strip()
        if dirty:
            commit += "+"  # 커밋되지 않은 변경 포함
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    info = BUILD / "build_info.json"
    info.write_text(json.dumps({"date": datetime.now().strftime("%Y-%m-%d"), "commit": commit}), encoding="utf-8")
    return info


def run_pyinstaller(version_file: Path, build_info: Path, notices: Path) -> None:
    env = dict(os.environ, PATH=clean_path(), VW_BUILD_INFO=str(build_info), VW_VERSION_FILE=str(version_file),
               VW_NOTICES_OUT=str(notices))
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--distpath", str(DIST), "--workpath", str(BUILD / "work"), str(SPEC)]
    print(">", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=ROOT, env=env)
    if r.returncode != 0:
        raise SystemExit(f"PyInstaller 빌드 실패 (종료 코드 {r.returncode})")


def qt_readme(onedir: Path) -> str:
    import PySide6
    import shiboken6
    from PySide6 import QtCore
    internal = onedir / "_internal"
    files = sorted(p.relative_to(onedir) for p in (internal / "PySide6").glob("Qt6*.dll"))
    plugins = sorted({p.parent.relative_to(onedir) for p in (internal / "PySide6" / "plugins").rglob("*.dll")})
    lines = [f"       {p}" for p in files] + [f"       {p}\\*.dll  (Qt 플러그인)" for p in plugins]
    tpl = (ROOT / "packaging" / "QT_LGPL_README.txt").read_text(encoding="utf-8")
    return tpl.format(APP_VERSION=VERSION, QT_VERSION=QtCore.qVersion(), PYSIDE_VERSION=PySide6.__version__,
                      SHIBOKEN_VERSION=shiboken6.__version__, QT_FILES="\n".join(lines))


def add_docs(target: Path, notices: Path, readme: str) -> None:
    (target / "LICENSES").mkdir(parents=True, exist_ok=True)
    for name in LICENSES:
        shutil.copy2(ROOT / "packaging" / "licenses" / name, target / "LICENSES" / name)
    shutil.copy2(notices, target / "THIRD_PARTY_NOTICES.txt")
    (target / "QT_LGPL_README.txt").write_text(readme, encoding="utf-8")
    shutil.copy2(ROOT / "packaging" / "EULA.txt", target / "EULA.txt")


def zip_dir(src: Path, dest: Path) -> None:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                z.write(p, Path(src.name) / p.relative_to(src))


def main() -> int:
    check_env()
    t0 = time.perf_counter()
    for d in (BUILD, DIST):
        if d.exists():
            shutil.rmtree(d)
    BUILD.mkdir()
    t = ",".join(VERSION.split(".") + ["0"])
    vf = BUILD / "version_info.txt"
    vf.write_text(VERSION_INFO.format(t=f"({t})", v=VERSION, app=APP), encoding="utf-8")

    info = prepare()
    notices = BUILD / "THIRD_PARTY_NOTICES.txt"
    run_pyinstaller(vf, info, notices)

    rel = DIST / RELEASE
    shutil.move(str(DIST / APP), rel)
    add_docs(rel, notices, qt_readme(rel))
    zip_dir(rel, DIST / f"{RELEASE}.zip")
    shutil.rmtree(BUILD)  # 중간 산출물. dist에는 배포 폴더와 zip만 남긴다

    print(f"\n완료 ({time.perf_counter() - t0:.0f}s)")
    for p in sorted(rel.iterdir()):
        if p.is_file():
            print(f"  {p.relative_to(DIST)}  {p.stat().st_size:,} B")
    z = DIST / f"{RELEASE}.zip"
    print(f"  {z.relative_to(DIST)}  {z.stat().st_size:,} B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
