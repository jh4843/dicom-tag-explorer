# Third-Party Licenses

배포물에 포함되는 외부 라이브러리와 라이선스 대장. 의존성 추가·제거 시 `/license-check` 결과를 반영해 갱신한다.

v0.1.0 기준 판정이다(근거는 `docs/Spec/v0.1.0.md` 3장). `보류`는 정책 목록에 없는 라이선스라 사용자 결정을 기다리는 항목이며, 결정 전에는 빌드 검사(DIR-019)에서 실패 처리된다.

## 런타임 (배포물에 포함)

| 라이브러리 | 버전 | 라이선스 | 판정 | 용도 | 비고 | 확인일 |
|------------|------|----------|------|------|------|--------|
| pydicom | 3.0.1 | MIT (사설 사전 일부 BSD-3, GDCM 유래) | 허용 | DICOM 값 해석, 픽셀 디코딩 | dist-info LICENSE 확인 | 2026-10-26 |
| wsidicom | 0.29.0 | Apache-2.0 | 허용 | WSI 슬라이드, 타일 읽기 | dist-info LICENCE 확인 | 2026-10-26 |
| PySide6-Essentials | 6.11.0 | LGPL-3.0-only (LGPL/GPL 중 선택) | 조건부(LGPL) | Qt 바인딩 (Core/Gui/Widgets/Svg) | wheel에 LGPL 원문 없음, 별도 첨부. PySide6 메타 패키지와 Addons는 쓰지 않음 | 2026-10-26 |
| shiboken6 | 6.11.0 | LGPL-3.0-only (선택) | 조건부(LGPL) | PySide6 런타임 | 위와 같음 | 2026-10-26 |
| Qt (PySide6-Essentials 번들) | 6.11.0 | LGPL-3.0 + 서드파티(FreeType FTL 선택, HarfBuzz MIT, libjpeg-turbo, libpng, PCRE2 BSD-3, zlib 등) | 조건부(LGPL) | Qt DLL과 플러그인 | 허용 Qt 모듈만 번들. FreeType FTL 선택, LIC-02 승인(2026-10-26). 고지 파일·정보 창에 크레딧 문구 | 2026-10-26 |
| Pillow | 12.1.1 | MIT-CMU | 허용 | JPEG/JPEG 2000 디코딩 | 번들 libjpeg-turbo, openjpeg, freetype(FTL 선택) 등 원문이 LICENSE에 포함 | 2026-10-26 |
| numpy | 2.4.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | 허용 | 픽셀 배열 | 번들 OpenBLAS BSD-3, GCC runtime GPL-3.0+ WITH GCC-exception-3.1(예외조항 있음) | 2026-10-26 |
| marshmallow | 3.26.2 | MIT | 허용 | wsidicom 의존 | | 2026-10-26 |
| dicomweb-client | 0.59.3 | MIT | 허용 | wsidicom 의존 (기능 미사용) | 메타 License 필드는 파일 참조, 원문 MIT | 2026-10-26 |
| requests | 2.32.5 | Apache-2.0 | 허용 | dicomweb-client 의존 | | 2026-10-26 |
| urllib3 | 2.6.2 | MIT | 허용 | requests 의존 | | 2026-10-26 |
| idna | 3.11 | BSD-3-Clause | 허용 | requests 의존 | | 2026-10-26 |
| charset-normalizer | 3.4.4 | MIT | 허용 | requests 의존 | | 2026-10-26 |
| certifi | 2026.1.4 | MPL-2.0 | 조건부(미수정) | requests 의존 (CA 번들) | LIC-01 승인(2026-10-26). 수정 금지, 고지 파일에 원문과 소스 위치 기재 | 2026-10-26 |
| retrying | 1.4.2 | Apache-2.0 | 허용 | dicomweb-client 의존 | NOTICE.txt 고지 포함 | 2026-10-26 |
| fsspec | 2026.4.0 | BSD-3-Clause | 허용 | wsidicom 의존 | | 2026-10-26 |
| universal-pathlib | 0.2.6 | MIT | 허용 | wsidicom 의존 | | 2026-10-26 |
| packaging | 25.0 | Apache-2.0 OR BSD-2-Clause | 허용 | marshmallow 의존 | | 2026-10-26 |
| Python 런타임 | 3.14.2 | PSF-2.0 (+ OpenSSL Apache-2.0, libffi MIT 등) | 허용 | 인터프리터 | Windows 빌드 추가 조건(Microsoft Distributable Code)은 LIC-03 | 2026-10-26 |
| Microsoft Visual C++ 런타임 | 14.x | Microsoft Distributable Code | 조건부(EULA) | Python·Qt·numpy 런타임 DLL | LIC-03 승인(2026-10-26). EULA에 MS 보호 조항 포함, 법무 검토 | 2026-10-26 |

## 빌드·개발 전용 (배포물에 포함하지 않음, PyInstaller 부트로더 제외)

| 라이브러리 | 버전 | 라이선스 | 판정 | 용도 | 비고 | 확인일 |
|------------|------|----------|------|------|------|--------|
| PyInstaller | 6.19.0 | GPL-2.0-or-later + Bootloader Exception | 허용 (빌드 도구) | exe 빌드 | 부트로더는 예외조항으로 결합 배포 가능, rthooks Apache-2.0 | 2026-10-26 |
| pyinstaller-hooks-contrib | 2026.3 | GPL-2.0-or-later (훅), Apache-2.0 (rthooks) | 허용 (빌드 도구) | PyInstaller 훅 | GPL 훅은 빌드 때만 실행. exe에 번들되는 rthooks는 Apache-2.0 | 2026-10-26 |
| altgraph / pefile / pywin32-ctypes | 0.17.5 / 2024.8.26 / 0.2.3 | MIT / MIT / BSD-3-Clause | 허용 (빌드 전용) | PyInstaller 의존 | | 2026-10-26 |
| pytest | 9.0.3 | MIT | 허용 (개발 전용) | 단위 테스트 | | 2026-10-26 |
| setuptools | 82.0.1 | MIT | 허용 (빌드 전용) | PyInstaller 의존 | | 2026-10-26 |
| pluggy / iniconfig / colorama / pygments | 1.6.0 / 2.3.0 / 0.4.6 / 2.19.2 | MIT / MIT / BSD-3-Clause / BSD-2-Clause | 허용 (개발 전용) | pytest 의존 | | 2026-10-26 |

## 채택하지 않음

| 라이브러리 | 버전 | 라이선스 | 판정 | 비고 | 확인일 |
|------------|------|----------|------|------|--------|
| imagecodecs | 2026.3.6 | BSD-3-Clause (번들 코덱 혼재) | 금지 | 번들 `jpg_0xc3`가 research only, `heif`·`jetraw`·`libjxs` 라이선스 파일이 비어 있음 | 2026-10-26 |
| pylibjpeg-libjpeg | - | GPL-3.0 | 금지 | | 2026-10-26 |
| PyQt6 | 6.11.0 | GPL-3.0 / 상용 | 금지 | PySide6 사용 | 2026-10-26 |
| PySide6-Addons | 6.11.0 | LGPL/GPL (GPL 전용 Qt 모듈 포함) | 금지 | 필요 없음. Charts 등 GPL 전용 모듈 | 2026-10-26 |

판정 값은 `허용`, `조건부(LGPL)`, `조건부(미수정)`, `조건부(EULA)`, `금지`, `보류`(사용자 결정 대기) 중 하나. 기준은 CLAUDE.md의 라이선스 정책을 따른다.
