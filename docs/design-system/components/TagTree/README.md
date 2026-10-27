# TagTree

DICOM 요소를 TAG·VR·VM·Length·Name·Value·Offset 7컬럼 트리로 보여주는 우측 상단 뷰로, 선택 행 가독성 규칙의 기준 화면이다.

- 헤더 `bg-300`, `label` 스타일, `ink-muted`. 행 `size-row`(22px), 바탕 `bg-200`. 교대 행 색은 쓰지 않고 hover만 `bg-400`.
- TAG·VR·VM·Length·Offset은 `mono`, Name·Value는 `ui`. Length는 오른쪽 정렬, Offset은 `ink-muted`.
- 선택 행 `selection` 위의 모든 글자는 `ink`다. Offset의 `ink-muted`, 의사 노드의 회색, 오류색도 선택되면 `ink`로 바뀐다. 포커스가 다른 곳에 있으면 `selection-inactive` + `ink`.
- 검색 일치 행 `search-match` + `ink`. 일치 행이 선택되면 `selection`이 이긴다.
- Preamble·DICM·Delimiter 의사 노드: 기울임체 + `ink-muted`. 크기는 줄이지 않는다.
- 긴 Value(UID, 다중값)는 칸 끝에서 `…`로 말줄임하고 툴팁에 전체. 반쯤 잘린 글자를 남기지 않는다.
- 소비자가 제공할 것: 요소 색인(지연 생성 모델), 선택·검색 일치 상태, 툴팁 텍스트.
