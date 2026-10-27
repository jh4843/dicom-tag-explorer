# 창 가장자리 회귀 테스트: 최대화 클라이언트 = 모니터 작업 영역(DPI 무관), 가장자리 요소의 size-edge 여백, 상태 표시줄 말줄임.
from __future__ import annotations

import tempfile

import pytest
from PySide6.QtCore import QCoreApplication, QSettings

from dicom_tag_explorer.ui import theme
from dicom_tag_explorer.ui.titlebar import maximized_client_rect

EDGE = theme.px("size-edge")

# (rcMonitor, rcWork). 사용자 구성과 같은 3모니터: 왼쪽 세로(음수 좌표), 가운데 주 모니터, 오른쪽
LEFT = ((-1200, 0, 0, 1600), (-1200, 0, 0, 1552))
MID = ((0, 0, 1920, 1080), (0, 0, 1920, 1032))
RIGHT = ((1920, 0, 3840, 1080), (1920, 0, 3840, 1032))


@pytest.mark.parametrize("frame", [0, 8, 11, 15])  # 테두리 두께: Qt 최대화(0), 100%(8), 150%(11), 200%(15) DPI
def test_maximized_client_is_work_area_for_any_frame(frame):
    for mon, work in (LEFT, MID, RIGHT):
        proposed = (work[0] - frame, work[1] - frame, work[2] + frame, work[3] + frame)
        assert maximized_client_rect(proposed, [LEFT, MID, RIGHT]) == work


def test_maximized_client_mixed_dpi_monitor():
    # 150% 모니터(2880x1620, 작업 영역 1560)에 놓인 창. 다른 모니터 DPI의 두께로 계산해도 결과는 그 모니터의 rcWork다
    hi = ((1920, 0, 4800, 1620), (1920, 0, 4800, 1560))
    proposed = (1920 - 11, -11, 4800 + 11, 1560 + 11)
    assert maximized_client_rect(proposed, [MID, hi]) == hi[1]
    assert maximized_client_rect(proposed, []) == proposed  # 모니터 정보가 없으면 그대로 둔다


def _window(qapp, w, h):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp())
    QCoreApplication.setOrganizationName("Vieworks")
    QCoreApplication.setApplicationName("DicomTagExplorerTestEdges")
    from dicom_tag_explorer.ui.main_window import MainWindow
    win = MainWindow()
    win.resize(w, h)
    win.show()
    for _ in range(10):
        qapp.processEvents()
    return win


def _x(win, widget) -> tuple[int, int]:
    p = widget.mapTo(win, widget.rect().topLeft())
    return p.x(), p.x() + widget.width()


@pytest.mark.parametrize("size", [(1280, 720), (1920, 1080)])
def test_edge_widgets_inset(qapp, size):
    theme.apply(qapp, "dark")
    win = _window(qapp, *size)
    try:
        W = win.width()
        assert W == size[0]
        tb = win.titlebar
        assert _x(win, tb.icon_label)[0] >= EDGE  # 타이틀바 앱 아이콘 앞
        assert _x(win, tb.btn_close)[1] == W  # 캡션 버튼은 오른쪽 끝에 붙인다 (Fitts)
        rb = win.ribbon
        assert _x(win, rb.tab_buttons[0])[0] >= EDGE  # 리본 탭 줄 왼쪽
        assert _x(win, rb.collapse_btn)[1] <= W - EDGE  # 리본 접기 버튼
        first_group = next(rb.body_lay.itemAt(i).widget() for i in range(rb.body_lay.count())
                           if rb.body_lay.itemAt(i).widget() is not None)
        assert _x(win, first_group)[0] >= EDGE  # 리본 본문 왼쪽
        for toolbar in (win.tag.toolbar, win.image.toolbar):  # 창 오른쪽 끝 영역 툴바
            if toolbar.width() < toolbar.minimumSizeHint().width():
                continue  # 1280 기본 분할의 Image 영역(320 px)은 툴바 최소 폭(약 375 px)보다 좁아 내용이 넘친다(기존 문제)
            right = _x(win, toolbar.max_btn)[1]
            assert W - EDGE - 2 <= right <= W - EDGE, (W, right)  # 살짝만: 여백은 size-edge
        sb = win.statusBar()
        win.path_label.setText("E:\\" + "\\".join(["Generated_folder_name_0000"] * 12) + "\\file.dcm")
        win.ts_label.setText("JPEG Baseline (Process 1)")
        win.zoom_label.setText("L0 z0 / 0.25%")
        for _ in range(5):
            qapp.processEvents()
        assert sb.contentsRect().left() >= EDGE and sb.contentsRect().right() <= W - EDGE
        for lab in (win.ts_label, win.zoom_label):  # 오른쪽 상태는 잘리지 않는다
            left, right = _x(win, lab)
            assert right <= W - EDGE and lab.width() >= lab.fontMetrics().horizontalAdvance(lab.text())
        left, right = _x(win, win.path_label)
        assert left >= EDGE and right <= _x(win, win.ts_label)[0]
        shown = super(type(win.path_label), win.path_label).text()
        assert "…" in shown and shown.startswith("E:\\") and shown.endswith("file.dcm")  # 가운데 말줄임
        assert f"padding: 4px 6px 4px {EDGE}px" in qapp.styleSheet()  # 독 제목 왼쪽
    finally:
        win.close()
