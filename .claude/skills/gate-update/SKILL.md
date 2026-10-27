---
name: gate-update
description: 요구사항(DIR) 카드가 Gate(G1~G3)를 통과해 다음 열로 옮겨가거나, Gate 전체가 승인될 때 사용한다. docs/Dashboard/vX.Y.Z.html의 JSON 데이터를 갱신하고 G3 통과 시 VERSION과 CHANGELOG.md를 갱신한다.
---

# gate-update

인자는 버전, 대상 DIR ID(여러 개 가능) 또는 Gate 이름, 변경 내용이다. 버전이 없으면 `docs/Dashboard/`에서 가장 높은 버전을 쓴다.

Dashboard는 요구사항 카드가 열을 이동하는 칸반이다. 화면은 파일 안의 두 JSON 블록으로만 그려진다. **HTML 본문과 스크립트는 수정하지 않는다.**

- `<script id="items">`는 DIR별 카드 배열이다. 필드는 `id`, `name`, `cat`, `spec`, `tc`, `stage`, `passed`, `note`이다.
- `<script id="gates">`는 Gate 전체 승인 정보이다. `G1`, `G2`, `G3` 각각에 `approved`(일자)와 `by`(승인자)가 있다.

## 열(stage)의 의미

| stage | 의미 | 다음 열로 옮기는 조건 |
|-------|------|------------------------|
| `대기` | 접수만 됨 | DIR에 등록되고 사양 작업이 시작됨 |
| `G1` | 요구사항·사양 작업 중 | DIR 확정, SPEC·TC 추적 완료, Gate G1 승인 |
| `G2` | 구현 중 | 해당 SPEC 구현 완료, 해당 TC의 pytest 통과 |
| `G3` | QA 중 | 해당 TC 스모크 결과 PASS (Spec 7장) |
| `완료` | G3 통과 | - |

## 절차

1. 해당 Dashboard 파일을 읽는다.
2. 카드를 옮길 때는 `stage`를 다음 열로 바꾸고, `passed`에 `"G#": "YYYY-MM-DD"`를 추가한다. 통과한 Gate 번호를 키로 쓴다.
3. 보류나 막힘이 있으면 `stage`는 그대로 두고 `note`에 짧게 적는다. 해소되면 `note`를 비운다.
4. Gate 전체를 승인할 때는 `gates.G#.approved`와 `by`를 채운다.
5. `#updated`를 오늘 날짜로 바꾼다.
6. 브라우저로 열어 콘솔 오류 없이 그려지는지 확인한다. JSON 문법 오류가 있으면 화면이 비어 보인다.

## 규칙

- 카드는 한 번에 한 열씩만 옮긴다. 열을 건너뛰지 않는다.
- 근거(SPEC 구현, pytest 결과, Spec 7장 PASS)를 확인한 카드만 옮긴다.
- G1과 G3의 전체 승인(`gates`)은 대화에서 사용자 승인이 확인되어야 한다. 확인되지 않았으면 사용자에게 묻는다.
- 작업 로그는 남기지 않는다. 이력은 `passed` 일자와 git 이력으로 대신한다.

## G3 완료 시 추가 작업

1. `VERSION` 내용을 `X.Y.Z`로 바꾼다.
2. `CHANGELOG.md`의 `[Unreleased]` 내용을 `## [X.Y.Z] - YYYY-MM-DD` 섹션으로 옮기고 빈 `[Unreleased]`를 남긴다.
3. `THIRD_PARTY_LICENSES.md`가 최신인지 확인한다.
