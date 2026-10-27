---
name: new-version
description: 새 버전 작업을 시작할 때 사용한다. 버전 번호(SemVer, 예 0.2.0)를 받아 docs/DIR, docs/Spec, docs/Dashboard에 해당 버전 파일을 템플릿으로 생성한다.
---

# new-version

인자: 버전 번호 `X.Y.Z` (`v` 접두사는 있어도 없어도 됨).

## 절차

1. 버전 번호가 SemVer 형식인지 확인한다. 없거나 형식이 틀리면 사용자에게 묻는다.
2. 아래 3개 파일이 이미 있으면 덮어쓰지 말고 중단 후 사용자에게 알린다.
   - `docs/DIR/vX.Y.Z.md`
   - `docs/Spec/vX.Y.Z.md`
   - `docs/Dashboard/vX.Y.Z.html`
3. 이 스킬 폴더의 `templates/DIR.md`, `templates/Spec.md`, `templates/Dashboard.html`을 복사하면서 치환한다.
   - `{{VERSION}}` → `X.Y.Z`
   - `{{DATE}}` → 오늘 날짜 `YYYY-MM-DD`
   - Dashboard의 `{{GATES}}`는 `{"G1":{"approved":"","by":""},"G2":{"approved":"","by":""},"G3":{"approved":"","by":""}}`로 바꾼다.
   - Dashboard의 `{{ITEMS}}`는 `[]`로 바꾼다. DIR 항목이 등록되면 항목마다 카드를 `stage: "대기"`로 추가한다. 카드 필드는 `id`, `name`(짧은 이름), `cat`, `spec`, `tc`, `stage`, `passed`, `note`이다. 이후 카드 이동은 `/gate-update`로 한다.
4. 이전 버전 DIR이 있으면 그 중 미완료(`상태`가 확정·완료가 아닌) 항목과 미결사항을 새 DIR의 "5. 미결사항"에 이월 후보로 나열하고, 실제 이월 여부는 사용자에게 확인한다.
5. `VERSION`, `CHANGELOG.md`는 수정하지 않는다. (G3 통과 시 `/gate-update`가 처리)
6. 생성한 파일 경로를 보고한다.
