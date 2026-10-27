# DICOM Tag Explorer 자체 제작 SVG 아이콘과 매니페스트를 생성하는 스크립트
import json
import sys
from pathlib import Path

OUT = Path(sys.argv[1])
# 원본은 다크 테마 색이다. 라이트 테마는 icons.json의 recolor 표로 로드 시 치환한다.
INK = "#C9D1DC"      # icon-ink
ACC = "#4C9DFF"      # accent
ERR = "#FF6B6B"      # danger
WRN = "#F2B33D"      # warning
MUTED = "#7D8796"    # ink-faint
KNOCK = "#12151A"    # icon-knockout (채운 도형 위의 글리프, 앞면 판)


def svg(body, stroke=INK):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
        f'fill="none" stroke="{stroke}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
        f"{body}</svg>\n"
    )


def p(d, **kw):
    attrs = "".join(f' {k.replace("_", "-")}="{v}"' for k, v in kw.items())
    return f'<path d="{d}"{attrs}/>'


DOC = "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"
DOC_FOLD = "M14 3v5h5"
FOLDER = "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"
LENS = '<circle cx="11" cy="11" r="6"/>' + p("M15.5 15.5 20 20")


def gear_path(teeth=8, ro=9.0, ri=7.0, cx=12.0, cy=12.0):
    """톱니 teeth개의 톱니바퀴 외곽선 경로를 만든다."""
    import math
    pts = []
    step = 2 * math.pi / teeth
    for k in range(teeth):
        a = k * step - math.pi / 2
        for da, r in ((-0.30, ri), (-0.18, ro), (0.18, ro), (0.30, ri)):
            pts.append((cx + r * math.cos(a + da * step * 1.6), cy + r * math.sin(a + da * step * 1.6)))
    return "M" + "L".join(f"{x:.2f} {y:.2f}" for x, y in pts) + "z"

# name: (category, 사용처, svg)
ICONS = {
    # 파일·메뉴
    "open-file": ("file", "파일 > 파일 열기 (Ctrl+O)", svg(p(DOC) + p(DOC_FOLD) + p("M12 17v-6M9.5 13.5 12 11l2.5 2.5"))),
    "open-folder": ("file", "파일 > 폴더 열기 (Ctrl+Shift+O)", svg(p(FOLDER) + p("M12 16v-5M9.5 13 12 10.5 14.5 13"))),
    "close-file": ("file", "파일 > 닫기 (Ctrl+W)", svg(p(DOC) + p(DOC_FOLD) + p("M10 13l4 4M14 13l-4 4"))),
    "close-all": ("file", "파일 > 모두 닫기 (Ctrl+Shift+W)", svg(
        p("M9 7V4a1 1 0 0 1 1-1h6l3 3v11a1 1 0 0 1-1 1h-3")
        + p("M13 7H6a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V9z")
        + p("M8 13.5l4 4M12 13.5l-4 4"))),
    "recent": ("file", "파일 > 최근 파일", svg('<circle cx="12" cy="12" r="8.5"/>' + p("M12 7.5V12l3 2"))),
    "copy": ("file", "편집 > 복사 (Ctrl+C), 우클릭 메뉴", svg(
        '<rect x="8" y="8" width="12" height="12" rx="2"/>'
        + p("M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"))),
    "goto-offset": ("file", "Offset으로 이동 (Ctrl+G)", svg(p("M4 6v12M8 12h12M16 8l4 4-4 4"))),
    "about": ("file", "설정 > 정보 (버전)", svg(
        '<circle cx="12" cy="12" r="8.5"/>' + p("M12 11v5")
        + f'<circle cx="12" cy="8" r="0.9" fill="{INK}" stroke="none"/>')),
    "settings": ("window", "타이틀바 설정 버튼, 설정 창 (언어·테마·라이선스) (Ctrl+,)", svg(p(gear_path()) + '<circle cx="12" cy="12" r="3"/>')),
    "language": ("file", "설정 > 언어 (English / 한국어)", svg(
        '<circle cx="12" cy="12" r="8.5"/><ellipse cx="12" cy="12" rx="3.6" ry="8.5"/>' + p("M3.5 12h17M5 7.5h14M5 16.5h14"))),
    "theme": ("file", "설정 > 테마 (다크 / 라이트)", svg(
        '<circle cx="12" cy="12" r="8.5"/>' + p("M12 3.5a8.5 8.5 0 0 1 0 17z", fill=INK, stroke="none"))),
    "help": ("file", "리본 도움말 탭, 도움말 (F1)", svg(
        '<circle cx="12" cy="12" r="8.5"/>' + p("M9.6 9.4a2.5 2.5 0 0 1 4.9.7c0 1.7-2.5 2.1-2.5 3.8")
        + f'<circle cx="12" cy="16.9" r="0.95" fill="{INK}" stroke="none"/>')),
    "license": ("file", "설정 > 라이선스 (서드파티 고지)", svg(
        p(DOC) + p(DOC_FOLD) + '<circle cx="12" cy="13.2" r="2.6"/>' + p("M10.4 15.3 9.8 19l2.2-1.1 2.2 1.1-.6-3.7"))),
    # 검색
    "search": ("search", "통합 검색 입력창 (Ctrl+F)", svg(LENS)),
    "search-advanced": ("search", "상세 검색 토글 (Ctrl+Shift+F)", svg(
        p("M4 7h10M18 7h2M4 17h2M10 17h10")
        + '<circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>')),
    "prev": ("search", "이전 일치 (Shift+F3)", svg(p("M6 15l6-6 6 6"))),
    "next": ("search", "다음 일치 (F3)", svg(p("M6 9l6 6 6-6"))),
    "clear": ("search", "상세 검색 Clear", svg('<circle cx="12" cy="12" r="8.5"/>' + p("M9 9l6 6M15 9l-6 6"))),
    # 보기·이미지
    "zoom-in": ("view", "Image 확대 (Ctrl+=)", svg(LENS + p("M8.5 11h5M11 8.5v5"))),
    "zoom-out": ("view", "Image 축소 (Ctrl+-)", svg(LENS + p("M8.5 11h5"))),
    "zoom-fit": ("view", "Image 맞춤 (Ctrl+0)", svg(
        p("M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4")
        + '<rect x="9" y="9" width="6" height="6" rx="1"/>')),
    "zoom-actual": ("view", "Image 1:1 (Ctrl+Alt+0)", svg(
        '<rect x="3" y="5" width="18" height="14" rx="2"/>'
        + p("M7.5 10l1.5-1.2v6.7M15 10l1.5-1.2v6.7")
        + f'<circle cx="12" cy="10.5" r="0.85" fill="{INK}" stroke="none"/>'
        + f'<circle cx="12" cy="14" r="0.85" fill="{INK}" stroke="none"/>')),
    "rotate-left": ("view", "좌회전 90° (Ctrl+Shift+R)", svg(p("M4.5 12a7.5 7.5 0 1 0 2.2-5.3L4.5 9") + p("M4.5 4.5V9H9"))),
    "rotate-right": ("view", "우회전 90° (Ctrl+R)", svg(p("M19.5 12a7.5 7.5 0 1 1-2.2-5.3L19.5 9") + p("M19.5 4.5V9H15"))),
    "maximize": ("view", "영역 최대화 (F11)", svg(
        '<rect x="3" y="4" width="18" height="16" rx="2"/>' + p("M8 12V8h4M16 12v4h-4M8 8l8 8"))),
    "restore": ("view", "영역 복원 (F11, Esc)", svg(
        '<rect x="4" y="8" width="12" height="12" rx="1.5"/>'
        + p("M8 8V5.5A1.5 1.5 0 0 1 9.5 4h9A1.5 1.5 0 0 1 20 5.5v9a1.5 1.5 0 0 1-1.5 1.5H16"))),
    # 창·Dock
    "window-minimize": ("window", "타이틀바 최소화 (작업 표시줄로)", svg(p("M6 12h12"))),
    "window-maximize": ("window", "타이틀바 최대화", svg('<rect x="6" y="6" width="12" height="12" rx="1.5"/>')),
    "window-restore": ("window", "타이틀바 이전 크기로 복원", svg(
        '<rect x="6" y="9" width="9" height="9" rx="1.2"/>' + p("M9 9V7.2A1.2 1.2 0 0 1 10.2 6h6.6A1.2 1.2 0 0 1 18 7.2v6.6a1.2 1.2 0 0 1-1.2 1.2H15"))),
    "window-close": ("window", "타이틀바 닫기", svg(p("M6.5 6.5l11 11M17.5 6.5l-11 11"))),
    "ribbon-collapse": ("window", "리본 접기 (Ctrl+F1)", svg(p("M8 14l4-4 4 4"))),
    "ribbon-expand": ("window", "리본 펼치기 (Ctrl+F1)", svg(p("M8 10l4 4 4-4"))),
    "dock-float": ("window", "탐색 Dock Floating 전환", svg(
        '<rect x="3" y="8" width="12" height="12" rx="1.5"/>'
        + '<rect x="9" y="4" width="12" height="10" rx="1.5" fill=KNOCK/>')),
    "close": ("window", "Dock 닫기, 패널 닫기", svg(p("M6 6l12 12M18 6 6 18"))),
    "stop": ("window", "상태바 작업 취소 (Esc)", svg(
        '<circle cx="12" cy="12" r="8.5"/>' + f'<rect x="9" y="9" width="6" height="6" rx="1" fill="{INK}" stroke="none"/>')),
    # 탐색 트리 (파일·WSI·DICOMDIR)
    "folder": ("tree", "파일 탭 폴더 노드", svg(p(FOLDER))),
    "dicom-file": ("tree", "파일 탭 DICOM 파일, Non-WSI 파일", svg(
        p("M15 3H8a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z") + p("M15 3v5h5")
        + f'<rect x="2.5" y="11.5" width="15" height="7.5" rx="1.5" fill="{ACC}" stroke="none"/>'
        # ".dcm" 글자를 선으로 직접 그린다 (폰트 의존 없음)
        + '<circle cx="4.6" cy="17.4" r="0.75" fill=KNOCK stroke="none"/>'
        + '<ellipse cx="6.95" cy="16.3" rx="1.2" ry="1.5" stroke=KNOCK stroke-width="1.15"/>'
        + p("M8.15 13.4v4.4"
            "M11.55 14.75a1.3 1.5 0 1 0 0 2.3"
            "M12.6 17.8v-3.2M12.6 15.5a.9.9 0 0 1 1.8 0v2.3M14.4 15.5a.9.9 0 0 1 1.8 0v2.3",
            stroke=KNOCK, stroke_width="1.15"))),
    "wsi-slide": ("tree", "WSI 탭 슬라이드(WSI 이미지) 노드", svg(
        '<rect x="2.5" y="8" width="19" height="8" rx="1.5"/>' + p("M7.5 8v8")
        + p("M13 10.3c2.1-.5 4.6.3 4.9 1.7.3 1.5-1.9 2.3-3.9 2-2.1-.3-3.2-1.1-3-2.1.1-.7.8-1.3 2-1.6z",
            stroke=ACC, fill=ACC, fill_opacity="0.22"))),
    "wsi-volume": ("tree", "VOLUME 레벨 Instance (피라미드)", svg(
        p("M12 4l8 4-8 4-8-4z", stroke=ACC) + p("M4 12l8 4 8-4M4 16l8 4 8-4"))),
    "wsi-label": ("tree", "LABEL Instance", svg(
        '<rect x="4" y="5" width="16" height="14" rx="1.5"/>'
        + p("M7.5 9v6M10 9v6M11.8 9v6M14.5 9v6M16.5 9v6", stroke_width="1.3"))),
    "wsi-overview": ("tree", "OVERVIEW Instance", svg(
        '<rect x="3" y="6" width="18" height="12" rx="1.5"/>' + p("M3 15l5-4 4 3 3-2 6 4")
        + '<circle cx="15.5" cy="9.5" r="1.2"/>')),
    "wsi-thumbnail": ("tree", "THUMBNAIL Instance", svg(
        '<rect x="4" y="4" width="7" height="7" rx="1"/><rect x="13" y="4" width="7" height="7" rx="1"/>'
        '<rect x="4" y="13" width="7" height="7" rx="1"/><rect x="13" y="13" width="7" height="7" rx="1"/>')),
    "dicomdir": ("tree", "DICOMDIR 루트 노드, 파일 > DICOMDIR 열기", svg(
        # 루트(DICOMDIR) → PATIENT → STUDY 계단식 계층 트리
        f'<rect x="2.5" y="2.5" width="7" height="5" rx="1.2" fill="{ACC}" stroke="{ACC}"/>'
        + '<rect x="8.5" y="9.5" width="7" height="5" rx="1.2"/>'
        + '<rect x="14.5" y="16.5" width="7" height="5" rx="1.2"/>'
        + p("M6 7.5V12h2.5M12 14.5V19h2.5"))),
    "patient": ("tree", "DICOMDIR PATIENT 레코드", svg('<circle cx="12" cy="8.5" r="3.5"/>' + p("M5 20a7 7 0 0 1 14 0"))),
    "study": ("tree", "DICOMDIR STUDY 레코드", svg(
        '<rect x="5" y="4.5" width="14" height="16" rx="2"/>'
        + p("M9 4.5v-.7a.8.8 0 0 1 .8-.8h4.4a.8.8 0 0 1 .8.8v.7M8.5 10h7M8.5 13.5h7M8.5 17h4"))),
    "series": ("tree", "DICOMDIR SERIES 레코드", svg(
        '<rect x="7" y="3.5" width="13" height="13" rx="1.5"/>' + p("M4.5 7.5V19A1.5 1.5 0 0 0 6 20.5h11.5"))),
    "image-record": ("tree", "DICOMDIR IMAGE 레코드", svg(
        '<rect x="4" y="4" width="16" height="16" rx="2"/><circle cx="9" cy="9" r="1.5"/>' + p("M20 15l-4.5-4.5L5 20"))),
    # Tag Tree
    "sequence": ("tag", "Tag Tree SQ 노드", svg(p("M8 4H5v16h3M16 4h3v16h-3") + p("M9.5 9h5M9.5 12h5M9.5 15h5", stroke=ACC))),
    "item": ("tag", "Tag Tree Item 노드", svg('<rect x="4" y="7" width="16" height="10" rx="2"/>' + p("M8 12h8", stroke=ACC))),
    # 상태
    "error": ("status", "열기 실패, 디코딩 실패, 파일 없음", svg(
        f'<circle cx="12" cy="12" r="9" fill="{ERR}" stroke="none"/>'
        + p("M12 7.5v5.5", stroke=KNOCK, stroke_width="2")
        + '<circle cx="12" cy="16.4" r="1.1" fill=KNOCK stroke="none"/>')),
    "warning": ("status", "부분 손상(중간까지 파싱)", svg(
        p("M10.3 3.9 2.6 17.3a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z", fill=WRN, stroke=WRN)
        + p("M12 9v4.5", stroke=KNOCK, stroke_width="2")
        + '<circle cx="12" cy="16.8" r="1.1" fill=KNOCK stroke="none"/>')),
    "cancelled": ("status", "읽기 취소된 파일", svg('<circle cx="12" cy="12" r="8.5"/>' + p("M6 6l12 12"), stroke=MUTED)),
}

CATEGORY_LABELS = {
    "file": "파일·편집", "search": "검색", "view": "보기·이미지", "window": "창·작업",
    "tree": "탐색 트리", "tag": "Tag Tree", "status": "상태",
}

OUT.mkdir(parents=True, exist_ok=True)
for name, (_, _, body) in ICONS.items():
    (OUT / f"{name}.svg").write_text(body.replace("=KNOCK", f'="{KNOCK}"'), encoding="utf-8")

manifest = {
    "version": 1,
    "grid": "24x24 viewBox, 선 1.75px, round cap/join. 16·20·24px로 표시",
    "theme": "dark",
    "colors": {"icon-ink": INK, "accent": ACC, "danger": ERR, "warning": WRN, "ink-faint": MUTED, "icon-knockout": KNOCK},
    "recolor": {"light": {INK: "#2F3640", ACC: "#0A66D1", ERR: "#C62828", WRN: "#9A5B00", MUTED: "#6B7480", KNOCK: "#FFFFFF"}},
    "license": "VIEWORKS 자체 제작. 서드파티 라이선스 없음",
    "categories": CATEGORY_LABELS,
    "icons": {n: {"file": f"{n}.svg", "category": c, "usage": u} for n, (c, u, _) in ICONS.items()},
}
(OUT / "icons.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(len(ICONS), "icons")
