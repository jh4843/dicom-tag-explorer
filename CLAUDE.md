# DICOM Tag Explorer

바이오분자영상팀의 WSI(Whole Slide Imaging) DICOM 뷰어/탐색기.
DICOM 표준(PS3.3 VL Whole Slide Microscopy Image IOD, Sup.145)에 따라 DICOM 파일의 Tag를 표시·검색하고, 관련 이미지(피라미드 레벨, Label, Overview, Thumbnail)를 표시한다.

- 실행 환경: Windows 10/11 (x64) 데스크톱
- 용도: 상용 배포 가능해야 함 → **라이선스 정책 준수가 최우선 제약**
- 기술 스택: Python 3.14 (고정) / PySide6-Essentials / pydicom / wsidicom (상세는 버전별 Spec에서 확정)

## 폴더 구조

```
CLAUDE.md                  # 이 파일 (프로젝트 규칙)
VERSION                    # 현재 릴리즈 버전 (SemVer, 예: 0.1.0)
CHANGELOG.md               # 버전별 변경 이력
THIRD_PARTY_LICENSES.md    # 사용 중인 외부 라이브러리와 라이선스 대장
.claude/agents/            # leader, uiux-designer, developer, qa
.claude/skills/            # new-version, gate-update, license-check
docs/DIR/vX.Y.Z.md         # 버전별 요구사항 (Design Input Requirements)
docs/Spec/vX.Y.Z.md        # 버전별 사양 (설계/UI/인수조건)
docs/Dashboard/vX.Y.Z.html # 버전별 Gate 진행상황 대시보드
```

소스 코드는 G2에서 `src/dicom_tag_explorer/`, 테스트는 `tests/`에 둔다. (구조 확정은 Spec에서)

## 버전 관리

- SemVer `MAJOR.MINOR.PATCH`, 시작 버전 `0.1.0`.
- 새 버전 착수 시 `/new-version X.Y.Z` 스킬로 DIR·Spec·Dashboard 3개 파일을 생성한다.
- `VERSION`과 `CHANGELOG.md`는 **G3 통과 시점에만** 갱신한다.
- 문서 파일명은 `v` 접두사 포함 (`v0.1.0.md`), `VERSION` 파일 내용은 접두사 없이 (`0.1.0`).

## Gate 프로세스 (G1 ~ G3)

| Gate | 이름 | 통과 조건 | 승인 |
|------|------|-----------|------|
| G1 | 요구사항·사양 확정 | DIR 작성 완료, Spec 작성 완료(UI 사양 포함), 모든 DIR 항목이 SPEC에 추적됨, 신규 라이브러리 라이선스 승인 | leader + 사용자 |
| G2 | 구현 완료 | Spec 기능 구현, 단위 테스트 통과, Windows에서 실행 확인 | leader |
| G3 | QA·릴리즈 | 인수조건 스모크 테스트 통과, 라이선스 대장 최신화, VERSION/CHANGELOG 갱신 | leader + 사용자 |

- Dashboard는 요구사항(DIR) 카드가 대기 → G1 → G2 → G3 열로 이동하는 칸반이다. 완료 열은 두지 않고 G3를 통과한 카드는 하단 "완료 항목" 표에만 나열된다. 작업 로그는 두지 않는다.
- 카드 이동과 Gate 승인은 반드시 `/gate-update` 스킬로 기록한다.
- 이전 Gate가 통과되지 않으면 다음 Gate 작업을 "완료"로 표시하지 않는다.
- 요구사항 ID 추적: `DIR-001` → `SPEC-001` → `TC-001`.

## 에이전트 역할

| 에이전트 | 역할 | 주 산출물 |
|----------|------|-----------|
| `leader` | 시니어 개발자, DICOM/WSI 전문가. 요구사항·사양 작성, 기술·라이선스 결정, Gate 승인, 작업 분배 | DIR, Spec, Dashboard |
| `uiux-designer` | 화면 구성, 사용자 흐름, 와이어프레임, 스타일 가이드 | Spec의 UI 사양 섹션 |
| `developer` | Spec 기반 구현과 단위 테스트 | `src/`, `tests/` |
| `qa` | 인수조건 기반 최소 스모크 테스트, 결과 기록 | Spec의 테스트 결과, Dashboard G3 |

## Design System

- 기준 문서는 Design System 아티팩트(https://claude.ai/artifact/6qZWnW8at3kfXwP4xavnVv)이고, 저장소 사본은 `docs/design-system/`(`tokens.json`, `README.md`, 컴포넌트별 README)이다. 둘이 다르면 사용자에게 묻는다.
- 다크 테마가 기본이고 라이트는 보조다. 색은 두 층이다. primary·secondary·neutral 팔레트가 있고, 그 위에 용도 토큰이 있다. 코드는 `ui/theme.py`의 용도 토큰만 쓰고 hex 값을 직접 쓰지 않는다.
- 바탕색을 지정하면 짝 글자색도 지정한다. 선택 행의 글자는 항상 `ink`다. 허용 조합은 `docs/design-system/README.md`의 가독성 규칙 표를 따른다.
- 아이콘은 자체 제작 SVG만 쓴다. 원본은 `src/dicom_tag_explorer/ui/resources/icons/`(다크 색)에 있고, 라이트 테마는 `icons.json`의 `recolor.light`로 치환한다. 아이콘을 추가하거나 수정할 때는 `scripts/make_icons.py`를 고친 뒤 다시 생성하고, Design System Asset도 함께 갱신한다.

## 라이선스 정책 (상용 무료 사용 가능 여부)

새 의존성 추가 전 반드시 `/license-check`로 확인하고 `THIRD_PARTY_LICENSES.md`에 기록한다. 판단이 애매하면 추가하지 말고 사용자에게 묻는다.

- **허용**: MIT, BSD-2/3-Clause, Apache-2.0, ISC, Zlib, PSF, MS-PL, HPND, Unlicense/CC0
- **조건부 허용**: LGPL-2.1/3.0 — 동적 링크로만 사용, 라이선스 고지 포함. 배포는 PyInstaller `onedir` 폴더 하나(사용자 결정)이며, LGPL 보완으로 LGPL 전문, Qt 소스 입수처, Qt 교체 방법 문서를 함께 제공하고 Qt·PySide6는 `_internal`에서 교체할 수 있게 둔다. (DIR-021, 022)
- **고지 파일**: 빌드 스크립트가 포함된 의존성의 LICENSE 원문으로 `THIRD_PARTY_NOTICES.txt`를 자동 생성하고 금지 라이선스가 있으면 빌드를 실패시킨다. 앱 설정 창의 라이선스 항목과 배포물에 모두 포함한다. (DIR-019, 020, 027)
  - PyInstaller 자체는 GPL + bootloader 예외로 상용 배포 가능.
- **조건부 허용 (승인됨, 2026-10-26)**: MPL-2.0은 수정 없이 사용할 때만(certifi). FreeType은 FTL 선택 + 고지 파일·설정 창 라이선스 항목에 크레딧 문구. MS VC++ 런타임은 EULA에 Microsoft 보호 조항 포함.
- **EULA**: Microsoft 보호 조항을 넣고, LGPL-3.0 4항에 따라 Qt 교체 목적의 수정·리버스 엔지니어링을 금지하지 않는다. 상용 배포 전 법무 검토.
- **금지**: GPL/AGPL(예외조항 없는 것), SSPL, CC-BY-NC 등 비상업 조항, "academic/research only", 라이선스 미표기
- **주의**: 패키지 본체가 허용이어도 **플러그인·코덱이 GPL**인 경우가 있음.
  - 예: `pylibjpeg-libjpeg`는 GPL-3.0 → 금지. JPEG 디코딩은 `pylibjpeg-openjpeg`(MIT), `imagecodecs`(BSD-3), Pillow 등으로 대체.

## 작업 규칙

- 답변·문서는 한국어. 문장은 `.`, `?`, `!`로 끝내고 `:`로 끝내지 않는다.
- 코드를 수정했다면 완료 보고 전에 테스트(`pytest`)를 실행한다.

## 테스트 샘플

- 위치는 `E:\JaeHyeokDoc\#1_Pathology\03_Images\DICOM`이다. 저장소 밖에 있으므로 복사하거나 커밋하지 않고 경로로만 참조한다.
  - `3DHISTECH-1/`에는 3DHISTECH 슬라이드 1개(파일 14개)가 있다.
  - `C23-013918_..._ESZ-202_R07S03/`에는 DICOMDIR, label, overview, 초점면 2개(z_0, z_1) × 레벨 0~8이 있다.
