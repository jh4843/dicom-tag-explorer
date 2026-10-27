# DICOM Tag Explorer

바이오분자영상팀의 WSI(Whole Slide Imaging) DICOM 뷰어/탐색기다.
DICOM 파일의 Tag를 표시·검색하고, 피라미드 레벨·Label·Overview·Thumbnail 이미지를 표시한다.

- 실행 환경은 Windows 10/11 (x64)이다.
- 기술 스택은 Python 3.14 / PySide6-Essentials / pydicom / wsidicom이다.
- 현재 버전은 [`VERSION`](VERSION), 변경 이력은 [`CHANGELOG.md`](CHANGELOG.md)에 있다.

## 개발 환경 셋팅

**준비물**은 Python 3.14 (x64)와 Git이다.

저장소 루트에 `.venv`를 만들고 `requirements*.txt`만 설치한다.

```powershell
git clone https://github.com/jh4843/dicom-tag-explorer.git
cd dicom-tag-explorer

py -3.14 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt

# 번역 파일(.qm) 생성. 생성물이라 커밋하지 않으며, 없으면 영어로만 실행된다
.venv\Scripts\python scripts\i18n.py release
```

> **주의.** 반드시 저장소 루트의 `.venv`(전역 site-packages 미포함)를 쓴다.
> 전역 환경에 `imagecodecs` 같은 대장 밖 패키지가 있으면 wsidicom이 자동으로 import해 빌드 고지 검사가 실패한다.
> `pip install -e .`도 하지 않는다. 소스는 `PYTHONPATH`로 참조한다.

## 소스 실행

```powershell
$env:PYTHONPATH = "src"
.venv\Scripts\python -m dicom_tag_explorer
```

로그는 `%LOCALAPPDATA%\DicomTagExplorer\logs\app.log`, 설정은 `%LOCALAPPDATA%\DicomTagExplorer\settings.ini`에 남는다.

## 테스트

```powershell
.venv\Scripts\python -m pytest
```

UI 흐름은 pytest 대상이 아니다. 샘플 폴더로 자동 점검하려면 스모크 스크립트를 쓴다.

```powershell
.venv\Scripts\python scripts\smoke_ui.py "E:\JaeHyeokDoc\#1_Pathology\03_Images\DICOM"
```

테스트 샘플은 저장소 밖에 두고 경로로만 참조한다. DICOM 파일(`*.dcm`)은 커밋하지 않는다.

## 빌드 (배포물 생성)

```powershell
.venv\Scripts\python scripts\build.py
```

`build.py`는 저장소 `.venv`가 아닌 인터프리터로 실행하면 중단한다. 다음 순서로 동작한다.

1. `scripts\i18n.py release`로 `.qm`을 만든다. 한국어 번역에 미완료 항목이 있으면 실패한다.
2. `scripts\gen_tokens.py --check`로 `ui/design_tokens.py`가 `docs/design-system/tokens.json`과 같은지 확인한다.
3. PyInstaller로 onedir를 빌드한다(`packaging/dicom_tag_explorer.spec`). 이때 `scripts/gen_notices.py`가 번들 내용으로 `THIRD_PARTY_NOTICES.txt`를 만들고, `packaging/license_policy.toml`에 없거나 금지된 라이선스가 있으면 빌드를 실패시킨다.
4. EULA·LGPL 문서를 넣고 zip으로 묶은 뒤 중간 폴더 `build/`를 지운다.

결과물은 `dist/`에 생긴다.

```
dist/
  DICOM-Tag-Explorer-<버전>-win64/
    DicomTagExplorer.exe
    _internal/                     # Python 런타임, 라이브러리, 교체 가능한 Qt DLL
    THIRD_PARTY_NOTICES.txt
    EULA.txt
    QT_LGPL_README.txt             # Qt 소스 입수처와 Qt DLL 교체 방법
    LICENSES/LGPL-3.0.txt, GPL-3.0.txt
  DICOM-Tag-Explorer-<버전>-win64.zip   # 배포 파일
```

배포는 zip 하나로 한다. 사용자는 압축을 풀고 `DicomTagExplorer.exe`를 실행한다(설치 불필요).

### 빌드가 실패할 때

| 메시지 | 조치 |
|--------|------|
| `저장소 .venv에서 실행하세요` | `.venv\Scripts\python`으로 실행한다 |
| `번역 .qm 생성 실패` | `scripts\i18n.py update` 후 `dicom_tag_explorer_ko.ts`의 미완료 번역을 채운다 |
| `design_tokens.py가 tokens.json과 다릅니다` | `scripts\gen_tokens.py`로 다시 생성하고 커밋한다 |
| `[gen_notices] 대장에 없음: ...` | 새 의존성이면 `/license-check` 후 `packaging/license_policy.toml`과 `THIRD_PARTY_LICENSES.md`에 기록한다. 의도치 않은 패키지면 `.venv`에서 제거한다 |

## 자주 쓰는 스크립트

| 명령 | 용도 |
|------|------|
| `scripts\i18n.py update` | 소스에서 UI 문자열을 추출해 `.ts`를 갱신한다 |
| `scripts\i18n.py release` | `.ts`에서 `.qm`을 만든다 |
| `scripts\gen_tokens.py` | `tokens.json`으로 `ui/design_tokens.py`를 다시 만든다 |
| `scripts\make_icons.py <출력 폴더>` | 자체 제작 SVG 아이콘을 생성한다 |

## 의존성 추가 규칙

상용 배포 제품이므로 라이선스 정책이 최우선이다. 새 패키지는 다음 순서로 추가한다.

1. `/license-check`로 라이선스를 확인한다. GPL/AGPL, 비상업 조항, 라이선스 미표기는 금지다. 기준은 [`CLAUDE.md`](CLAUDE.md)의 라이선스 정책이다.
2. `requirements.txt`(런타임) 또는 `requirements-dev.txt`(개발·빌드)에 `==`로 버전을 고정한다.
3. `THIRD_PARTY_LICENSES.md`와 `packaging/license_policy.toml`을 함께 갱신한다.

## 문서

| 경로 | 내용 |
|------|------|
| `CLAUDE.md` | 프로젝트 규칙 (Gate 프로세스, 라이선스 정책, 작업 규칙) |
| `docs/DIR/vX.Y.Z.md` | 버전별 요구사항 |
| `docs/Spec/vX.Y.Z.md` | 버전별 사양 (설계, UI, 인수조건) |
| `docs/Dashboard/vX.Y.Z.html` | 버전별 Gate 진행 대시보드 |
| `docs/design-system/` | 디자인 토큰과 컴포넌트 규칙 |
| `THIRD_PARTY_LICENSES.md` | 외부 라이브러리 라이선스 대장 |
