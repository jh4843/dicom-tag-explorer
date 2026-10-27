# HexView

파일 원본 바이트를 `Offset | 16바이트 Hex | ASCII`로 보여주는 가상 스크롤 뷰로, 선택한 Tag의 바이트 범위를 하이라이트한다.

- 전체 `mono`(12/17). Offset은 `ink-muted`, 바이트와 ASCII는 `ink`. 8바이트마다 공백 한 칸을 더 둔다.
- 선택 요소의 헤더(Tag+VR+Length)는 `hex-header`, Value는 `hex-value`. 두 색은 밝기가 달라서 색약에서도 경계가 보인다. SQ·Item 선택은 하위 범위 전체가 `hex-value`.
- 클릭·키보드 커서는 `hex-cursor` 1px 테두리. 커서 위치는 상태바에 `mono-sm`으로 `Offset 0x00000A24 (2596)`.
- 위쪽 정보 줄(`bg-300`, `mono-sm`): `(TAG) Keyword │ 시작–끝 │ 헤더 n + 값 m = 전체 bytes`. Undefined Length는 Delimiter까지 포함한 범위다.
- 소비자가 제공할 것: 바이트 소스(보이는 범위만 읽기), 선택 범위(헤더 끝, 전체 끝), 바이트→노드 역매핑 콜백.
