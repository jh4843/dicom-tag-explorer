# SearchField

Tag Tree 위 오른쪽의 통합 검색 바로, 모든 컬럼을 검색하고 상세 검색 패널로 컬럼별 조건을 더한다.

- 입력창 폭 300px, 높이 24px, 바탕 `bg-300`, 테두리 `line-strong`, 모서리 `radius-sm`. 포커스 `focus` 2px.
- 이전·다음(`prev`/`next`), 결과 수 `현재 / 전체`(`mono-sm` `ink-muted`), `Show only` 체크박스(한국어 `일치 항목만`, 상세 패널 옵션과 같은 `QCheckBox` 스타일), `상세`(`search-advanced`) 순서로 오른쪽 정렬한다. `Show only`를 켜면 Tag Tree에 일치 행과 그 상위 행만 남는다(SPEC-041).
- 0건이면 입력창 바탕 `danger-bg`, 테두리와 결과 수 `danger`. 색과 함께 `0 / 0` 숫자로도 알린다.
- 상세 패널은 바로 아래에 펼쳐지는 3열 그리드다. TAG·VR·VM·Offset·Length 입력은 `mono`. Value는 한 줄 전체를 쓴다. 옵션은 대소문자 구분, 정규식. 형식이 틀린 필드는 `danger` 테두리와 툴팁.
- 일치 행은 Tag Tree에서 `search-match`, 현재 위치는 선택 행(`selection`)이다.
- 소비자가 제공할 것: 검색 실행 콜백, 결과 수, 필드 검증 결과.
