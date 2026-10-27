# ExplorerTree

좌측 탐색 Pane의 분류 트리로, 파일·WSI·DICOMDIR 탭마다 열린 파일을 노드로 보여준다.

- 행 `size-row`(22px), 들여쓰기 18px, 아이콘 16px과 글자 사이 `space-3`. 이름은 `body` `ink`, 정보 컬럼은 `mono-sm` `ink-muted`로 오른쪽에 둔다.
- 헤더는 `이름`·`정보` 두 컬럼이고 트리·표 공통 헤더 스타일(`bg-300` 바탕, `label` `ink-muted`)을 쓴다. 헤더 경계를 끌어 폭을 바꾸고, 이름 컬럼은 행이 추가되거나 노드를 펼칠 때 내용 폭에 맞춘다. 정보 컬럼은 남은 폭을 채운다.
- 선택 `selection`(포커스 밖이면 `selection-inactive`), hover `bg-400`. 탭 선택은 Ribbon 탭과 같은 `accent` 밑줄.
- 노드 아이콘: 슬라이드 `wsi-slide`, 레벨 `wsi-volume`(이름 `VOLUME L{n} z{k}`), `wsi-label`, `wsi-overview`, `wsi-thumbnail`, 폴더 `folder`, 파일 `dicom-file`, DICOMDIR 루트 `dicomdir`, 레코드 `patient`·`study`·`series`·`image-record`.
- 상태: 열기 실패는 `error` 아이콘 + `danger` 이름, 부분 손상은 `warning` 아이콘 + `warning` 이름, 취소는 `cancelled` + `ink-faint`. 원인은 툴팁에 쓴다. 색만으로 알리지 않고 항상 아이콘을 함께 둔다.
- 소비자가 제공할 것: 노드 종류, 이름, 정보 문자열, 상태, 툴팁(파일 경로, UID).
