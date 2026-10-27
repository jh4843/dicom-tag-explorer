# SettingsDialog

타이틀바 `settings` 버튼(Ctrl+,)으로 여는 모달 설정 창으로, 언어·테마·라이선스·정보를 한곳에서 다룬다.

- 크기 720×480 기준, `bg-200`, `radius-md`, `shadow-popup`. 제목 줄 `bg-100` `title` 스타일.
- 왼쪽 목록(168px, `bg-100`): `language` 언어, `theme` 테마, `license` 라이선스, `about` 정보. 선택 항목은 `selection`.
- 언어: English / 한국어 라디오. 즉시 적용하고 QSettings에 저장. 항목 이름 "언어 · Language"는 두 언어를 함께 써서 잘못 고른 사람도 찾을 수 있게 한다.
- 테마: 다크(기본) / 라이트 라디오. 즉시 적용.
- 라이선스: 맨 위 FreeType 크레딧 문구, 그 아래 목록(라이브러리, 버전, 라이선스; 숫자는 `mono-sm`)과 선택 항목 원문(`mono-sm`, 스크롤). 데이터는 빌드가 만든 `THIRD_PARTY_NOTICES.txt`에서 읽는다. `고지 파일 열기`는 exe 옆 파일을 연다.
- 정보: 버전(`VERSION`), 저작권, 빌드 일자와 커밋.
- 소비자가 제공할 것: 현재 언어·테마, 고지 파일 경로, 버전 정보, 변경 콜백.
