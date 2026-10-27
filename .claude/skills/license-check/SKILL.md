---
name: license-check
description: 새 라이브러리(Python 패키지, 코덱, 폰트, 아이콘 등)를 추가하거나 버전을 올리기 전에 사용한다. 상업적 무료 사용 가능 여부를 판정하고 THIRD_PARTY_LICENSES.md에 기록한다.
---

# license-check

인자: 패키지 이름(여러 개 가능), 선택적으로 버전.

## 절차

1. 각 패키지의 라이선스를 **1차 출처**에서 확인한다.
   - PyPI 메타데이터(`pip show <pkg>` 또는 pypi.org), 저장소의 LICENSE 파일
   - 메타데이터와 LICENSE 파일이 다르면 LICENSE 파일을 따르고 차이를 기록한다.
2. **런타임 의존성과 번들된 네이티브 라이브러리**까지 확인한다. (`pip show`의 Requires, wheel에 포함된 .dll)
   - 플러그인·코덱 패키지를 특히 주의한다. (예: `pylibjpeg-libjpeg`는 GPL-3.0)
3. CLAUDE.md 라이선스 정책으로 판정한다.
   - `허용` / `조건부(LGPL)` / `금지`
   - 확인 불가, 라이선스 미표기, 이중 라이선스 해석이 애매한 경우는 `금지`로 두고 사용자에게 보고한다.
4. 결과를 표로 보고한다. `라이브러리 | 버전 | 라이선스 | 판정 | 근거 URL | 비고`
5. 사용자가 채택을 결정하면 `THIRD_PARTY_LICENSES.md`와 해당 버전 Spec의 "기술 스택 및 라이선스" 표에 기록한다.

## 참고 (확인 시점 기준, 반드시 재확인)

| 패키지 | 라이선스 | 판정 |
|--------|----------|------|
| pydicom | MIT | 허용 |
| wsidicom | Apache-2.0 | 허용 |
| PySide6 | LGPL-3.0 | 조건부 |
| numpy | BSD-3-Clause | 허용 |
| Pillow | MIT-CMU (HPND) | 허용 |
| imagecodecs | BSD-3-Clause | 허용 |
| pylibjpeg-openjpeg | MIT | 허용 |
| pylibjpeg-libjpeg | GPL-3.0 | 금지 |
| PyQt6 | GPL-3.0 / 상용 | 금지 (PySide6 사용) |
| PyInstaller | GPL-2.0 + bootloader 예외 | 허용 (빌드 도구) |
| pytest | MIT | 허용 (개발 전용) |
