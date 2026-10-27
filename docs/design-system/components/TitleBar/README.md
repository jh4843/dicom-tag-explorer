# TitleBar

프레임 없는 메인 창의 커스텀 타이틀바로, 앱 이름·현재 파일과 설정·최소화·최대화/복원·닫기 버튼을 담는다.

- 높이 `size-titlebar`(32px), 바탕 `bg-100`. 제목은 `body`, 파일명은 `ink-muted`로 이어 쓰고 넘치면 말줄임한다.
- 앱 아이콘 앞은 창 가장자리 여백 `size-edge`(8px)다. 캡션 버튼은 오른쪽 끝에 붙인다(여백 없음).
- 최대화하면 창 내용(클라이언트 영역)이 그 모니터의 작업 영역(작업 표시줄 제외)과 정확히 같아야 한다. 화면 밖으로 넘치거나 안쪽이 비면 안 된다.
- 오른쪽 캡션 버튼은 순서 고정이다: `settings` → `window-minimize` → `window-maximize`(최대화 상태면 `window-restore`) → `window-close`. 각 46×32px, 아이콘 16px `icon-ink`.
- hover는 `caption-hover`, 닫기만 `caption-close-hover`에 글리프 `#ffffff`. 키보드 포커스는 `focus` 2px 안쪽 테두리.
- 빈 영역 드래그로 이동, 더블클릭으로 최대화/복원. Qt 구현은 프레임 없는 창에 `WM_NCHITTEST`를 처리해 Aero Snap(Win11 스냅 레이아웃 포함)과 가장자리 크기 조절을 유지한다.
- 버튼에는 `aria-label`(Qt: `setAccessibleName`)과 툴팁을 단다. 문자열은 tr 대상이다.
- 소비자가 제공할 것: 현재 파일명, 최대화 여부, 각 버튼의 동작.
