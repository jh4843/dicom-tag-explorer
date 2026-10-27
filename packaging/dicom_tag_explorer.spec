# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec. onedir 빌드를 만든다 (Spec v0.1.0 2.7).
import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
from gen_notices import NoticeError, generate  # noqa: E402

VERSION_FILE = os.environ.get("VW_VERSION_FILE")
NOTICES = Path(os.environ.get("VW_NOTICES_OUT", ROOT / "build" / "THIRD_PARTY_NOTICES.txt"))
BUILD_INFO = os.environ.get("VW_BUILD_INFO")
RES = ROOT / "src" / "dicom_tag_explorer" / "ui" / "resources"
RES_DEST = "dicom_tag_explorer/ui/resources"
# 앱 리소스: 아이콘 SVG 52개 + icons.json, 앱 아이콘, 빌드 때 만든 .qm (Spec 2.7 번들 데이터)
APP_DATAS = ([(str(f), f"{RES_DEST}/icons") for f in sorted((RES / "icons").glob("*.svg"))]
             + [(str(RES / "icons" / "icons.json"), f"{RES_DEST}/icons"), (str(RES / "app.svg"), RES_DEST)]
             + [(str(f), f"{RES_DEST}/i18n") for f in sorted((RES / "i18n").glob("*.qm"))])

# 번들하지 않는 파일.
# - opengl32sw.dll: 소프트웨어 OpenGL(Mesa). 쓰지 않는다
# - generic/networkinformation/tls 플러그인과 그것들만 쓰는 Qt6Network.dll: 허용 Qt 모듈(Core/Gui/Widgets/Svg) 밖
# - api-ms-win-*.dll, ucrtbase.dll: Windows 10/11 기본 구성요소(UCRT). PATH의 다른 프로그램 폴더에서 끌려오지 않게 한다
DROP_FILES = {"opengl32sw.dll", "qt6network.dll", "ucrtbase.dll"}
DROP_PREFIXES = ("api-ms-win-",)
DROP_PLUGIN_DIRS = ("networkinformation", "tls", "generic")
# PySide6 도구 실행 파일은 빌드 때만 쓴다 (lupdate, lrelease, linguist, designer 등)
DROP_SUFFIX_EXE = ".exe"

a = Analysis(
    [str(ROOT / "src" / "dicom_tag_explorer" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=APP_DATAS,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pytest", "setuptools", "_distutils_hack", "pkg_resources", "distutils",
              "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick"],
    noarchive=False,
    optimize=0,
    # LGPL 라이브러리의 Python 파일도 exe 밖(_internal)에 두어 사용자가 교체할 수 있게 한다 (Spec 3.5)
    module_collection_mode={"PySide6": "py", "shiboken6": "py"},
)


def _keep(entry) -> bool:
    dest = entry[0].replace("\\", "/")
    name = dest.rsplit("/", 1)[-1]
    low = name.lower()
    if low in DROP_FILES or low.startswith(DROP_PREFIXES):
        return False
    if low.endswith(DROP_SUFFIX_EXE):
        return False
    # Qt 번역은 qtbase_ko.qm만 넣는다
    if "/translations/" in dest.lower() and low.endswith(".qm") and low != "qtbase_ko.qm":
        return False
    return not any(f"/plugins/{d}/" in dest for d in DROP_PLUGIN_DIRS)


a.binaries = [e for e in a.binaries if _keep(e)]
a.datas = [e for e in a.datas if _keep(e)]

# 번들 내용으로 고지 파일을 만들고 금지 검사를 한다. 실패하면 빌드를 중단한다 (SPEC-028)
try:
    generate(a.pure, a.binaries, a.datas, NOTICES)
except NoticeError as e:
    print("\n[gen_notices] 라이선스 검사 실패. 빌드를 중단합니다.", file=sys.stderr)
    for err in e.errors:
        print("  -", err, file=sys.stderr)
    raise SystemExit(1)
print(f"[gen_notices] {NOTICES}")
a.datas += [("THIRD_PARTY_NOTICES.txt", str(NOTICES), "DATA")]
if BUILD_INFO:
    a.datas += [(f"{RES_DEST}/build_info.json", BUILD_INFO, "DATA")]

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="DicomTagExplorer",
    console=False,
    upx=False,
    version=VERSION_FILE,
    icon=str(ROOT / "packaging" / "app.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="DicomTagExplorer")
