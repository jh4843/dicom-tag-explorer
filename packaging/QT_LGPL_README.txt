DICOM Tag Explorer {APP_VERSION} - Qt / PySide6 (LGPL-3.0) 안내
=================================================================

이 프로그램은 다음 LGPL-3.0 라이브러리를 수정하지 않고 동적 링크(별도 DLL)로 사용합니다.

  - Qt {QT_VERSION} (Qt Core, Qt GUI, Qt Widgets, Qt SVG 와 그 플러그인)
  - PySide6 {PYSIDE_VERSION} (PySide6-Essentials) / shiboken6 {SHIBOKEN_VERSION}

LGPL-3.0 전문은 LICENSES\LGPL-3.0.txt, LGPL이 참조하는 GPL-3.0 전문은 LICENSES\GPL-3.0.txt에 있습니다.
Qt에 포함된 서드파티 구성요소의 고지는 THIRD_PARTY_NOTICES.txt의 PySide6-Essentials / Qt 항목에 있습니다.


1. 소스 입수처
--------------
아래 주소는 빌드 시점(2026-10-26)에 존재를 확인했습니다.

Qt {QT_VERSION}
  - 전체 소스: https://download.qt.io/official_releases/qt/6.11/6.11.0/single/qt-everywhere-src-6.11.0.zip
  - 모듈 소스: https://download.qt.io/official_releases/qt/6.11/6.11.0/submodules/qtbase-everywhere-src-6.11.0.tar.xz
               https://download.qt.io/official_releases/qt/6.11/6.11.0/submodules/qtsvg-everywhere-src-6.11.0.tar.xz
  - Git 태그 : https://code.qt.io/cgit/qt/qtbase.git/tag/?h=v6.11.0
               https://code.qt.io/cgit/qt/qtsvg.git/tag/?h=v6.11.0

PySide6 / shiboken6 {PYSIDE_VERSION}
  - 소스     : https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.0-src/pyside-setup-everywhere-src-6.11.0.zip
  - Git 태그 : https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v6.11.0


2. Qt 라이브러리 교체 방법
--------------------------
Qt와 PySide6는 프로그램 폴더의 _internal 아래에 별도 파일로 있으므로 직접 교체할 수 있습니다.

  1) 교체 전에 프로그램 폴더 전체를 백업합니다.
  2) 교체 대상은 다음 위치에 있습니다.
{QT_FILES}
  3) 같은 Qt 마이너 버전(6.11.x), Windows x64, MSVC로 빌드한 Qt DLL로 위 파일을 바꿉니다.
     Qt를 바꾸면 PySide6 바인딩(_internal\PySide6\*.pyd, *.py, pyside6.abi3.dll)과
     shiboken6(_internal\shiboken6\)도 그 Qt로 빌드한 것으로 함께 바꿔야 합니다.
     (pyside-setup 소스로 직접 빌드하거나, 같은 버전의 PySide6-Essentials / shiboken6 wheel에서 꺼냅니다.)
  4) 폴더의 DicomTagExplorer.exe를 실행합니다. 설정 창의 정보 항목에서 버전을 확인할 수 있습니다.

이 프로그램의 사용권 계약(EULA.txt)은 위 교체를 위한 수정과, 그 수정을 디버깅하기 위한 리버스 엔지니어링을
금지하지 않습니다 (LGPL-3.0 4항).
