# 커스텀 타이틀바 위젯과 Win32 비클라이언트 메시지 처리(Snap·크기 조절·스냅 레이아웃 유지).
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from . import theme
from .icons import app_icon, icon

# Win32 상수
WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
WM_NCMOUSEMOVE = 0x00A0
WM_NCLBUTTONDOWN = 0x00A1
WM_NCLBUTTONUP = 0x00A2
WM_NCLBUTTONDBLCLK = 0x00A3
WM_NCMOUSELEAVE = 0x02A2
HTCLIENT, HTCAPTION, HTMAXBUTTON = 1, 2, 9
HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT, HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 10, 11, 12, 13, 14, 15, 16, 17
GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = 0x00000080, 0x00040000
WS_CAPTION, WS_THICKFRAME, WS_SYSMENU = 0x00C00000, 0x00040000, 0x00080000
WS_MINIMIZEBOX, WS_MAXIMIZEBOX = 0x00020000, 0x00010000
SWP_FLAGS = 0x0001 | 0x0002 | 0x0004 | 0x0020  # NOSIZE | NOMOVE | NOZORDER | FRAMECHANGED
SM_CXSIZEFRAME, SM_CYSIZEFRAME, SM_CXPADDEDBORDER = 32, 33, 92


class MARGINS(ctypes.Structure):
    _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int), ("t", ctypes.c_int), ("b", ctypes.c_int)]


class NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD)]


MONITOR_DEFAULTTONEAREST = 2
Rect = tuple[int, int, int, int]  # (left, top, right, bottom)


def maximized_client_rect(proposed: Rect, monitors: list[tuple[Rect, Rect]]) -> Rect:
    """최대화된 창의 클라이언트 사각형 = 창이 놓인 모니터의 작업 영역(rcWork).
    monitors는 (rcMonitor, rcWork) 목록이고, 제안된 창 사각형과 가장 많이 겹치는 모니터를 고른다(MonitorFromRect와 같다).
    창 사각형은 경로에 따라 다르다. Qt 최대화(showMaximized)는 프레임 없는 창을 rcWork에 맞추고, 네이티브 최대화
    (Win+Up, 스냅, SC_MAXIMIZE)는 테두리 두께만큼 바깥으로 넓힌다. 테두리 두께를 빼는 방식은 앞의 경우 사방이
    잘리고(테두리 두께만큼 클라이언트가 작아짐) DPI에 따라 두께도 다르므로, 두께와 무관하게 rcWork로 둔다."""
    def overlap(m: Rect) -> int:
        w = min(proposed[2], m[2]) - max(proposed[0], m[0])
        h = min(proposed[3], m[3]) - max(proposed[1], m[1])
        return max(w, 0) * max(h, 0)
    if not monitors:
        return proposed
    return max(monitors, key=lambda mw: overlap(mw[0]))[1]


def _monitor_of(rect: wintypes.RECT) -> list[tuple[Rect, Rect]]:
    u = _user32()
    u.MonitorFromRect.restype = wintypes.HMONITOR
    h = u.MonitorFromRect(ctypes.byref(rect), MONITOR_DEFAULTTONEAREST)
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if not h or not u.GetMonitorInfoW(h, ctypes.byref(mi)):
        return []
    m, w = mi.rcMonitor, mi.rcWork
    return [((m.left, m.top, m.right, m.bottom), (w.left, w.top, w.right, w.bottom))]


def _user32():
    return ctypes.windll.user32


def frame_thickness(hwnd: int) -> tuple[int, int]:
    """(가로, 세로) 크기 조절 테두리 두께(물리 픽셀). 모니터별 DPI를 반영한다."""
    u = _user32()
    try:
        dpi = u.GetDpiForWindow(wintypes.HWND(hwnd))
        pad = u.GetSystemMetricsForDpi(SM_CXPADDEDBORDER, dpi)
        return (u.GetSystemMetricsForDpi(SM_CXSIZEFRAME, dpi) + pad,
                u.GetSystemMetricsForDpi(SM_CYSIZEFRAME, dpi) + pad)
    except Exception:
        return (8, 8)


def enable_min_max_box(hwnd: int) -> None:
    """Floating Dock(Qt Tool 창)에 네이티브 최소화·최대화 버튼을 켠다. 창을 다시 만들지 않으므로 드래그·재도킹이 유지된다.
    Tool 창(WS_EX_TOOLWINDOW)의 캡션에는 닫기 버튼만 그려지므로 그 스타일을 뺀다. 작업 표시줄 버튼(WS_EX_APPWINDOW)이
    없으면 최소화한 창이 화면 왼쪽 아래에 작은 제목줄로 남으므로 함께 켠다."""
    if sys.platform != "win32":
        return
    u = _user32()
    get = u.GetWindowLongPtrW
    get.restype = ctypes.c_ssize_t
    h = wintypes.HWND(hwnd)
    style = get(h, GWL_STYLE) | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
    ex = get(h, GWL_EXSTYLE) & ~WS_EX_TOOLWINDOW | WS_EX_APPWINDOW
    u.SetWindowLongPtrW(h, GWL_STYLE, ctypes.c_ssize_t(style))
    u.SetWindowLongPtrW(h, GWL_EXSTYLE, ctypes.c_ssize_t(ex))
    u.SetWindowPos(h, None, 0, 0, 0, 0, SWP_FLAGS)


class CaptionButton(QToolButton):
    """46×32 캡션 버튼. 닫기 버튼은 hover 때 흰 글리프로 바꾼다."""

    def __init__(self, icon_name: str, close: bool = False, parent=None):
        super().__init__(parent)
        self.icon_name = icon_name
        self.is_close = close
        self.setObjectName("CaptionClose" if close else "CaptionButton")
        self.setFixedSize(QSize(46, theme.px("size-titlebar")))
        self.setIconSize(QSize(theme.px("size-icon-sm"), theme.px("size-icon-sm")))
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAutoRaise(True)
        self._hover = False
        self.refresh_icon()

    def set_native_hover(self, on: bool) -> None:
        """HTMAXBUTTON 영역은 OS가 비클라이언트 메시지로 보내므로 hover를 직접 표시한다."""
        if self._hover != on:
            self._hover = on
            self.setProperty("hover", on)
            self.style().unpolish(self)
            self.style().polish(self)
            self.refresh_icon()

    def refresh_icon(self) -> None:
        white = self.is_close and (self._hover or self.underMouse())
        self.setIcon(icon(self.icon_name, "neutral-0" if white else None))

    def enterEvent(self, e):
        super().enterEvent(e)
        if self.is_close:
            self.refresh_icon()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        self.set_native_hover(False)
        if self.is_close:
            self.refresh_icon()


class TitleBar(QWidget):
    settingsClicked = Signal()

    def __init__(self, window: QWidget):
        super().__init__(window)
        self.win = window
        self.setObjectName("TitleBar")
        self.setFixedHeight(theme.px("size-titlebar"))
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(theme.px("size-edge"), 0, 0, 0)  # 창 가장자리 여백. 캡션 버튼은 오른쪽 끝에 붙인다
        lay.setSpacing(theme.px("space-3"))
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(16, 16)
        lay.addWidget(self.icon_label)
        self.title_label = QLabel("DICOM Tag Explorer")
        lay.addWidget(self.title_label)
        self.file_label = QLabel()
        self.file_label.setProperty("role", "muted")
        self.file_label.setMinimumWidth(40)
        self.file_label.setContentsMargins(theme.px("space-2"), 0, 0, 0)  # "DICOM Tag Explorer - 파일명"
        lay.addWidget(self.file_label, 1)
        self.btn_settings = CaptionButton("settings")
        self.btn_min = CaptionButton("window-minimize")
        self.btn_max = CaptionButton("window-maximize")
        self.btn_close = CaptionButton("window-close", close=True)
        for b in (self.btn_settings, self.btn_min, self.btn_max, self.btn_close):
            lay.addWidget(b)
        lay.setSpacing(0)
        self.btn_settings.clicked.connect(self.settingsClicked.emit)
        self.btn_min.clicked.connect(window.showMinimized)
        self.btn_max.clicked.connect(self.toggle_maximize)
        self.btn_close.clicked.connect(window.close)
        self._file = ""
        theme.notifier().changed.connect(self.apply_theme)
        self.apply_theme()
        self.retranslate()

    # ---- 표시 ----
    def apply_theme(self, *_):
        self.icon_label.setPixmap(app_icon().pixmap(16, 16))
        for b in (self.btn_settings, self.btn_min, self.btn_max, self.btn_close):
            b.refresh_icon()
        self.setStyleSheet(
            f"#TitleBar {{ background: {theme.hex_('bg-100')}; }}"
            f"#TitleBar QLabel {{ color: {theme.hex_('ink')}; }}"
            f"#TitleBar QLabel[role=\"muted\"] {{ color: {theme.hex_('ink-muted')}; }}"
            f"#CaptionButton, #CaptionClose {{ border: none; border-radius: 0; background: transparent; }}"
            f"#CaptionButton:hover, #CaptionButton[hover=\"true\"] {{ background: {theme.hex_('caption-hover')}; }}"
            f"#CaptionClose:hover {{ background: {theme.hex_('caption-close-hover')}; }}"
            f"#CaptionButton:focus, #CaptionClose:focus {{ border: 2px solid {theme.hex_('focus')}; }}")

    def retranslate(self) -> None:
        for b, text in ((self.btn_settings, self.tr("Settings (Ctrl+,)")), (self.btn_min, self.tr("Minimize")),
                        (self.btn_max, self.tr("Restore") if self.win.isMaximized() else self.tr("Maximize")),
                        (self.btn_close, self.tr("Close"))):
            b.setToolTip(text)
            b.setAccessibleName(text)

    def changeEvent(self, e):
        if e.type() == QEvent.Type.LanguageChange:
            self.retranslate()
        super().changeEvent(e)

    def set_file(self, name: str) -> None:
        self._file = name
        self._elide()

    def _elide(self) -> None:
        text = f"- {self._file}" if self._file else ""
        fm = QFontMetrics(self.file_label.font())
        self.file_label.setText(fm.elidedText(text, Qt.TextElideMode.ElideRight, max(40, self.file_label.width())))
        self.file_label.setToolTip(self._file)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide()

    def update_maximized(self) -> None:
        self.btn_max.icon_name = "window-restore" if self.win.isMaximized() else "window-maximize"
        self.btn_max.refresh_icon()
        self.retranslate()

    def toggle_maximize(self) -> None:
        if self.win.isMaximized():
            self.win.showNormal()
        else:
            self.win.showMaximized()

    def mouseDoubleClickEvent(self, e):
        # Windows 밖(또는 HTCAPTION 처리가 안 될 때)의 대비. Windows에서는 OS가 처리한다
        if sys.platform != "win32":
            self.toggle_maximize()

    # ---- 히트 테스트 ----
    def hit_test(self, local: QPoint) -> int:
        """타이틀바 좌표(논리)에 대한 Win32 히트 코드."""
        if self.btn_max.geometry().contains(local):
            return HTMAXBUTTON
        for b in (self.btn_settings, self.btn_min, self.btn_close):
            if b.geometry().contains(local):
                return HTCLIENT
        return HTCAPTION


class NativeFrame:
    """프레임 없는 메인 창의 Win32 메시지 처리. MainWindow.nativeEvent가 위임한다."""

    def __init__(self, window: QWidget, titlebar: TitleBar):
        self.win = window
        self.bar = titlebar
        self._installed = False

    def install(self) -> None:
        """창 핸들이 생긴 뒤 Win32 스타일을 다시 켜고 그림자용 1px 여백을 준다."""
        if sys.platform != "win32" or self._installed:
            return
        hwnd = int(self.win.winId())
        u = _user32()
        get = u.GetWindowLongPtrW
        get.restype = ctypes.c_ssize_t
        style = get(wintypes.HWND(hwnd), GWL_STYLE)
        style |= WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
        u.SetWindowLongPtrW(wintypes.HWND(hwnd), GWL_STYLE, ctypes.c_ssize_t(style))
        try:
            m = MARGINS(0, 0, 1, 0)
            ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(wintypes.HWND(hwnd), ctypes.byref(m))
        except Exception:
            pass
        u.SetWindowPos(wintypes.HWND(hwnd), None, 0, 0, 0, 0, SWP_FLAGS)
        self._installed = True

    def handle(self, message: int) -> tuple[bool, int]:
        msg = wintypes.MSG.from_address(int(message))
        m = msg.message
        if m == WM_NCCALCSIZE and msg.wParam:
            # 최대화 판정은 Win32 상태로 한다. 네이티브 최대화에서는 이 메시지가 Qt의 windowState보다 먼저 온다
            if _user32().IsZoomed(msg.hWnd):
                p = NCCALCSIZE_PARAMS.from_address(msg.lParam)
                r = p.rgrc[0]
                r.left, r.top, r.right, r.bottom = maximized_client_rect(
                    (r.left, r.top, r.right, r.bottom), _monitor_of(r))
            return True, 0
        if m == WM_NCHITTEST:
            return True, self._hit(msg)
        if m in (WM_NCMOUSEMOVE, WM_NCMOUSELEAVE):
            self.bar.btn_max.set_native_hover(m == WM_NCMOUSEMOVE and msg.wParam == HTMAXBUTTON)
            return False, 0
        if m in (WM_NCLBUTTONDOWN, WM_NCLBUTTONDBLCLK) and msg.wParam == HTMAXBUTTON:
            return True, 0
        if m == WM_NCLBUTTONUP and msg.wParam == HTMAXBUTTON:
            self.bar.toggle_maximize()
            return True, 0
        return False, 0

    def _hit(self, msg) -> int:
        x = ctypes.c_short(msg.lParam & 0xFFFF).value
        y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
        rect = wintypes.RECT()
        _user32().GetWindowRect(msg.hWnd, ctypes.byref(rect))
        if not self.win.isMaximized():
            fx, fy = frame_thickness(int(msg.hWnd))
            left, right = x < rect.left + fx, x >= rect.right - fx
            top, bottom = y < rect.top + fy, y >= rect.bottom - fy
            if top and left:
                return HTTOPLEFT
            if top and right:
                return HTTOPRIGHT
            if bottom and left:
                return HTBOTTOMLEFT
            if bottom and right:
                return HTBOTTOMRIGHT
            if left:
                return HTLEFT
            if right:
                return HTRIGHT
            if top:
                return HTTOP
            if bottom:
                return HTBOTTOM
        dpr = self.win.devicePixelRatioF() or 1.0
        # 클라이언트 좌표로 바꾼다 (최대화 상태는 클라이언트가 창 사각형 안쪽 rcWork에 있다, WM_NCCALCSIZE)
        pt = wintypes.POINT(x, y)
        _user32().ScreenToClient(msg.hWnd, ctypes.byref(pt))
        local_win = QPoint(round(pt.x / dpr), round(pt.y / dpr))
        local = self.bar.mapFrom(self.win, local_win)
        if self.bar.rect().contains(local):
            return self.bar.hit_test(local)
        return HTCLIENT
