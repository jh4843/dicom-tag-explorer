# DICOM Tag Explorer

바이오분자영상팀의 WSI DICOM 탐색기를 위한 디자인 시스템이다. 대상은 Windows 데스크톱 앱(PySide6/Qt)이다. 사용자는 Tag와 바이트를 확인하고 큰 슬라이드 이미지를 오래 들여다보는 연구원이다.

## 원칙

1. **이미지가 주인공이다.** 기본 테마는 다크다. 주변 UI는 낮은 밝기의 무채색에 가까운 슬레이트로 두고, 밝은 것은 슬라이드 이미지와 지금 보고 있는 데이터뿐이다. Image 뷰 캔버스(`bg-000`)는 라이트 테마에서도 어둡다.
2. **색은 의미가 있을 때만 쓴다.** `accent`(파랑)는 선택, 링크, DICOM·WSI 강조에만 쓴다. Hex 하이라이트, 검색 일치, 오류·경고는 각자 전용 토큰이 있고 다른 용도로 빌리지 않는다.
3. **밀도가 기본이다.** 행 22px, 본문 12px(9pt), 패널 모서리 0이다. 카드, 그림자, 둥근 패널로 공간을 쓰지 않는다. 그림자는 떠 있는 팝업(`shadow-popup`)에만 쓴다.
4. **바이트는 고정폭이다.** Hex, TAG, VR, VM, Length, Offset은 `mono`이고 Name과 Value는 `ui`다. 숫자 컬럼은 오른쪽 정렬이다.
5. **두 테마 모두 대비를 지킨다.** 본문 4.5:1 이상, 아이콘·테두리·포커스 3:1 이상이다. 구분이 필요한 색 쌍은 밝기도 다르다. 예를 들어 `hex-header`는 `hex-value`보다 밝다.

## 기본 팔레트

색은 두 층이다. 아래 세 스케일이 기본 팔레트이고, 다음 절의 용도 토큰은 모두 이 팔레트를 가리키는 별칭이다. 화면 코드는 용도 토큰만 쓰고 팔레트 단계를 직접 쓰지 않는다. 색을 조정할 때는 팔레트를 고친다.

| 스케일 | 기준 단계 | 성격 |
|---|---|---|
| **Primary** 파랑 `primary-50`~`900` | `primary-400` #4c9dff (다크) · `primary-600` #0a66d1 (라이트) | 선택, 포커스, 링크, DICOM·WSI 강조. H&E 염색의 분홍·보라와 겹치지 않는 차가운 파랑이다. |
| **Secondary** 호박 `secondary-50`~`900` | `secondary-200` #f2b33d | Hex 헤더 바이트, Hex 커서, 검색 일치, 경고. Primary와 색상·밝기가 모두 달라 한 화면에 같이 있어도 구분된다. |
| **Neutral** 슬레이트 `neutral-0`~`950` | `neutral-850` #171b21 (다크 패널) · `neutral-0` (라이트 패널) | 바탕, 선, 글자, 아이콘. 파랑 쪽으로 아주 약간 기운 회색이다. |

- 오류(`danger`), 완료(`success`), 타이틀바 닫기(`caption-close-hover`)는 상태 전용 색이라 팔레트 밖에 둔다.
- VIEWORKS 브랜드 빨강(#DB0032)은 UI 색으로 쓰지 않는다. 오류색과 겹치기 때문이다. 앱 아이콘과 설정의 정보 화면 로고에만 쓴다.

## 색

용도 토큰의 이름은 역할이다. 값은 테마마다 다르고 Qt에서는 `ui/theme.py`가 같은 이름으로 들고 있다.

| 역할 | 토큰 | 규칙 |
|---|---|---|
| 바탕 | `bg-000` < `bg-100` < `bg-200` < `bg-300` < `bg-400` | 깊이 순서다. 창 바탕은 `bg-100`, 패널은 `bg-200`, 헤더·입력창은 `bg-300`, hover는 `bg-400`이다. |
| 선 | `line`, `line-strong` | 패널 경계는 `line`, 조작 가능한 컨트롤(입력창·버튼) 테두리는 `line-strong`이다. |
| 글자 | `ink`, `ink-muted`, `ink-faint` | 값·본문은 `ink`, 보조 정보(정보 컬럼, Offset, 상태바)는 `ink-muted`, Delimiter와 비활성은 `ink-faint`다. |
| 선택 | `selection`, `selection-inactive` | 검색의 "현재 위치"는 별도 색 없이 `selection`이다. |
| Hex | `hex-header`, `hex-value`, `hex-cursor` | 선택 요소의 헤더 바이트, Value 바이트, 클릭 커서다. |
| 검색 | `search-match` | 일치 행 바탕이다. 선택되면 `selection`이 이긴다. |
| 상태 | `danger`, `danger-bg`, `warning`, `success` | 아이콘과 함께 쓴다. 색만으로 상태를 알리지 않는다. |
| 타이틀바 | `caption-hover`, `caption-close-hover` | 닫기 hover는 Windows와 같은 `#c42b1c`에 흰 글리프다. |
| WSI 타일 | `tile-loading`, `tile-sparse`, `tile-hatch` | 읽는 중은 단색, 저장되지 않은 타일은 유리색에 빗금, 읽기 실패는 `tile-sparse` 위에 `danger` X다. |

## 가독성 규칙

바탕을 정하면 글자도 정해진다. 아래 표에 없는 조합은 쓰지 않는다. 숫자는 대비율이고 다크/라이트 순서다. 본문 기준은 4.5:1이다.

| 바탕 | 허용 글자 | 다크 | 라이트 |
|---|---|---|---|
| `bg-100` | ink · ink-muted | 14.7 / 7.3 | 15.0 / 5.8 |
| `bg-200` | ink · ink-muted · ink-faint · accent · danger · warning | 13.9 / 6.9 / 4.8 / 6.2 / 6.2 / 9.3 | 16.6 / 6.4 / 4.7 / 5.5 / 5.6 / 5.4 |
| `bg-300` | ink · ink-muted | 12.7 / 6.3 | 14.5 / 5.6 |
| `bg-400` | ink | 11.3 | 13.3 |
| `selection` | **ink만** | 7.0 | 12.6 |
| `selection-inactive` | ink만 | 10.3 | 13.3 |
| `search-match` | ink만 | 7.9 | 14.8 |
| `hex-header` | ink만 | 5.8 | 11.6 |
| `hex-value` | ink만 | 9.6 | 9.2 |
| `danger-bg` | ink · danger | 12.6 / 5.6 | 14.5 / 4.9 |
| `accent` | accent-ink | 7.1 | 5.5 |
| `caption-close-hover` | #ffffff | 5.7 | 5.7 |

- **선택 행은 글자가 항상 `ink`다.** 회색 보조 글자(`ink-muted`, `ink-faint`), 오류색, 링크색도 선택되면 `ink`로 바뀐다. 시스템 강조색(Windows accent)을 그대로 쓰지 않는다. 진한 파랑 위에 검정 글자가 남는 사고가 여기서 난다.
- **Qt 적용.** QPalette의 Active·Inactive 두 그룹 모두에 Window=`bg-100`, Base=`bg-200`, AlternateBase=`bg-300`, Text·WindowText·ButtonText=`ink`, PlaceholderText=`ink-faint`, Highlight=`selection`(Inactive는 `selection-inactive`), HighlightedText=`ink`, Link=`accent`, ToolTipBase=`bg-300`, ToolTipText=`ink`를 넣는다. Disabled 그룹의 Text는 `ink-faint`다. ForegroundRole로 색을 정한 셀은 delegate가 `State_Selected`일 때 HighlightedText로 덮어쓴다.
- **바탕만 바꾸지 않는다.** QSS나 delegate에서 바탕색을 칠하면 같은 규칙에서 글자색도 지정한다.
- **기울임체와 회색을 겹치지 않는다.** Preamble·Delimiter 같은 의사 노드는 기울임체 하나로만 구분하고 색은 `ink-muted`까지만 낮춘다. 크기는 12px 아래로 줄이지 않는다.
- **잘림은 말줄임으로 처리한다.** 긴 UID나 Value는 `…`로 끝내고 툴팁에 전체를 보여준다. 글자가 칸 경계에서 반쯤 잘려 보이지 않게 한다.

## 글자

- `ui` 패밀리는 Segoe UI Variable Text이고, 한국어는 맑은 고딕으로 폴백한다. 둘 다 Windows 기본 글꼴이라 배포물에 글꼴 파일을 넣지 않는다.
- `mono` 패밀리는 Consolas다. Hex 정렬이 깨지지 않도록 다른 고정폭으로 폴백한다.
- 스타일은 `title` 14/20, `body` 12/16, `body-strong`, `caption` 11/14, `label`, `mono` 12/17, `mono-sm` 11/14다. 이 밖의 크기는 만들지 않는다.

## 간격과 크기

- 간격은 2·4·6·8·12·16·24px(`space-1`~`space-8`)만 쓴다.
- 모서리는 패널 0, 컨트롤 3px, 팝업 6px이다.
- 고정 크기는 타이틀바 32px(캡션 버튼 46×32), 리본 탭 줄 28px, 리본 본문 84px, 행 22px, 아이콘 16px/32px이다.
- **창 가장자리 여백.** 창 바깥 테두리에 닿는 요소만 안쪽으로 `size-edge`(8px)를 둔다. 대상은 타이틀바 앱 아이콘 앞, 리본 탭 줄·본문 좌우, 상태바 좌우, 창 오른쪽 끝 영역 툴바(Tag 검색 바, Image)의 오른쪽, 탐색 Dock 제목 왼쪽이다. 캡션 버튼과 그 왼쪽 설정 버튼은 Windows 규칙대로 오른쪽 끝에 붙인다. 내부 간격과 행 높이는 바꾸지 않는다. 트리·표 첫 컬럼 안쪽 여백을 줄 때는 `space-3`까지만 쓴다.

## 창 구성

위에서 아래 순서는 다음과 같다.

1. **타이틀바** (`size-titlebar`, `bg-100`). 왼쪽은 앱 아이콘과 `DICOM Tag Explorer - 파일명`, 오른쪽은 `settings` · `window-minimize` · `window-maximize`/`window-restore` · `window-close`이다. 캡션 버튼은 46×32이고 아이콘은 16px이다. 빈 영역 드래그로 이동, 더블클릭으로 최대화한다. Snap과 가장자리 크기 조절은 Windows 동작을 따른다.
2. **리본** 탭 줄(`bg-100`)과 본문(`bg-200`). 탭은 파일 · 편집 · 보기 · 도움말이다. 본문은 그룹 단위로 나누고 그룹 이름은 `caption` `ink-muted`로 아래에 쓴다. 자주 쓰는 명령은 큰 버튼(32px 아이콘 + 라벨), 나머지는 작은 버튼(16px + 라벨)이다. 폭이 모자라면 그룹을 드롭다운 하나로 접는다. 오른쪽 끝 `ribbon-collapse`(Ctrl+F1)로 접으면 탭 줄만 남고, 탭을 누르면 본문이 잠시 펼쳐진다.
3. **작업 영역.** 탐색 Dock, Tag Tree, Hex, Image 배치는 Spec 5장을 따른다.
4. **상태바** (`bg-100`, `caption`). 파일 경로는 가운데 말줄임(`…`)으로 먼저 줄이고, 오른쪽 상태(Transfer Syntax, 레벨·배율)는 자르지 않는다.

## 설정

설정은 타이틀바의 `settings`나 `Ctrl+,`로 여는 모달 창(`radius-md`, `bg-200`)이다. 왼쪽 목록과 오른쪽 내용으로 구성한다.

| 항목 | 아이콘 | 내용 |
|---|---|---|
| 언어 | `language` | English / 한국어. 즉시 바뀐다. DICOM 용어(Tag, VR, VM, Keyword, Transfer Syntax, SOP Class)는 두 언어 모두 영어로 둔다. |
| 테마 | `theme` | 다크(기본) / 라이트. 즉시 바뀐다. |
| 라이선스 | `license` | 서드파티 목록(이름, 버전, 라이선스)을 보여주고, 하나를 고르면 원문을 보여준다. FreeType 크레딧은 목록 맨 위에 둔다. |
| 정보 | `about` | 버전, 저작권, 빌드 정보. |

## 글쓰기

- 명령 이름은 동사로 쓴다. 예: 파일 열기 / Open File, Offset으로 이동 / Go to Offset.
- 오류 문구는 무엇이 잘못됐고 어떻게 하면 되는지를 말한다. 예: "파일을 읽을 수 없습니다. DICM 접두어가 없습니다." / "Can't read the file. The DICM prefix is missing."
- 한국어 문장은 마침표로 끝낸다. 버튼과 메뉴 라벨에는 마침표를 쓰지 않는다.
- 영어 원문이 기준이고 한국어는 번역이다. 한국어는 영어보다 최대 30% 길어도 레이아웃이 깨지지 않게 한다. 리본 라벨은 두 줄까지 허용한다.

## 아이콘

- 52개 모두 자체 제작이다. 그리드는 24×24, 선은 1.75px이고 끝과 이음은 둥글다. 16px과 32px에서 쓴다. 서드파티 라이선스가 없다.
- 원본 SVG는 다크 테마 색으로 그렸다(`icon-ink`, `accent`, `danger`, `warning`, `ink-faint`, `icon-knockout`). 라이트 테마에서는 앱이 `icons.json`(Design System `assets/Icons/icons.json`, 저장소 `src/dicom_tag_explorer/ui/resources/icons/icons.json`. 두 파일은 같다)의 `recolor.light` 표대로 색 문자열을 바꿔서 불러온다. Qt SVG는 `currentColor`를 믿을 수 없어서 이 방식을 쓴다.
- 이름은 `icons.json`이 기준이다. 코드는 `icon("zoom-in")`처럼 이름으로만 가져오고, 없는 이름은 바로 실패시킨다.
- 새 아이콘은 같은 그리드와 선 굵기로 그리고, 위 여섯 색만 쓴다. `icons.json`에 사용처와 함께 등록한다.
