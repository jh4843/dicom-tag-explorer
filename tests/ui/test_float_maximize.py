# Floating Explorer 창에 네이티브 최소화·최대화 버튼을 켜는 Win32 스타일 변경 회귀 테스트.
from __future__ import annotations

import ctypes
import sys

import pytest

from dicom_tag_explorer.ui.titlebar import (
    GWL_EXSTYLE, GWL_STYLE, WS_EX_APPWINDOW, WS_EX_TOOLWINDOW, WS_MAXIMIZEBOX, WS_MINIMIZEBOX, WS_SYSMENU,
    enable_min_max_box,
)

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Win32 전용")


def test_enable_min_max_box_turns_tool_window_into_maximizable():
    u = ctypes.windll.user32
    u.CreateWindowExW.restype = ctypes.c_void_p
    u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    WS_CAPTION, WS_THICKFRAME = 0x00C00000, 0x00040000
    hwnd = u.CreateWindowExW(WS_EX_TOOLWINDOW, "STATIC", "float", WS_CAPTION | WS_THICKFRAME,
                             0, 0, 200, 100, None, None, None, None)
    assert hwnd
    try:
        enable_min_max_box(hwnd)
        style, ex = u.GetWindowLongPtrW(ctypes.c_void_p(hwnd), GWL_STYLE), u.GetWindowLongPtrW(ctypes.c_void_p(hwnd), GWL_EXSTYLE)
        assert style & WS_MINIMIZEBOX and style & WS_MAXIMIZEBOX and style & WS_SYSMENU and style & WS_THICKFRAME
        assert not ex & WS_EX_TOOLWINDOW and ex & WS_EX_APPWINDOW
    finally:
        u.DestroyWindow(ctypes.c_void_p(hwnd))
