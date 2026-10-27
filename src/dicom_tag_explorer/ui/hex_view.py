# 보이는 줄만 읽어 그리는 가상 스크롤 Hex 뷰 (Offset | 16바이트 Hex | ASCII).
from __future__ import annotations

from typing import Callable

from typing import Callable as _Fn

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QFontMetrics, QGuiApplication, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractScrollArea, QInputDialog, QLabel, QLineEdit, QStackedWidget, QVBoxLayout, QWidget,
)

from ..core.values import format_offset
from . import theme
from .common import AreaToolbar, mono_font
from .theme import color, hex_

BPL = 16  # bytes per line


def parse_hex_offset(text: str) -> int | None:
    t = text.strip().lower()
    if t.startswith("0x"):
        t = t[2:]
    if not t or any(c not in "0123456789abcdef" for c in t):
        return None
    return int(t, 16)


class HexView(QAbstractScrollArea):
    cursorMoved = Signal(int)  # 커서 오프셋 (클릭·키보드)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(mono_font())
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        self._read: Callable[[int, int], bytes] | None = None
        self.size = 0
        self.cursor = -1
        self.anchor = -1  # Shift 선택 시작
        self.hl: tuple[int, int, int] | None = None  # (start, header_len, total_len)
        self._dragging = False
        self._update_metrics()

    # ---- 데이터 ----
    def set_source(self, read: Callable[[int, int], bytes] | None, size: int) -> None:
        self._read = read
        self.size = size if read else 0
        self.cursor = -1
        self.anchor = -1
        self.hl = None
        self._update_metrics()
        self.verticalScrollBar().setValue(0)
        self.viewport().update()

    def clear(self) -> None:
        self.set_source(None, 0)

    @property
    def lines(self) -> int:
        return (self.size + BPL - 1) // BPL

    def _update_metrics(self) -> None:
        fm = QFontMetrics(self.font())
        self.cw = fm.horizontalAdvance("0")
        self.lh = max(fm.height(), theme.font_line('mono'))
        self.asc = fm.ascent()
        self.off_chars = 10 if self.size > 0xFFFFFFFF else 8
        self.hex_x = (self.off_chars + 2) * self.cw
        self.ascii_x = self.hex_x + (BPL * 3 + 1 + 1) * self.cw
        self.line_w = self.ascii_x + (BPL + 2) * self.cw + 4
        self._update_scrollbars()

    def line_width_px(self) -> int:
        return self.line_w + self.verticalScrollBar().sizeHint().width() + 4

    def _visible_lines(self) -> int:
        return max(1, self.viewport().height() // self.lh)

    def _update_scrollbars(self) -> None:
        vis = self._visible_lines()
        vs = self.verticalScrollBar()
        vs.setRange(0, max(0, self.lines - vis))
        vs.setPageStep(vis)
        vs.setSingleStep(1)
        hs = self.horizontalScrollBar()
        hs.setRange(0, max(0, self.line_w - self.viewport().width()))
        hs.setPageStep(self.viewport().width())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_scrollbars()

    # ---- 하이라이트·스크롤 ----
    def set_highlight(self, start: int, header_len: int, total_len: int, scroll: bool = True) -> None:
        self.hl = (start, header_len, total_len)
        if scroll:
            self.ensure_visible(start)
        self.viewport().update()

    def clear_highlight(self) -> None:
        self.hl = None
        self.viewport().update()

    def ensure_visible(self, offset: int) -> None:
        """줄이 보이지 않으면 위에서 2번째 줄에 오도록 스크롤한다."""
        line = offset // BPL
        top = self.verticalScrollBar().value()
        vis = self._visible_lines()
        if top <= line < top + vis:
            return
        self.verticalScrollBar().setValue(max(0, line - 1))

    # ---- 좌표 ----
    def _offset_at(self, pos: QPoint) -> int | None:
        x = pos.x() + self.horizontalScrollBar().value()
        line = self.verticalScrollBar().value() + pos.y() // self.lh
        col = None
        if self.hex_x <= x < self.ascii_x - 2 * self.cw:
            c = (x - self.hex_x) // self.cw
            if c >= 8 * 3 + 1:
                c -= 1
            col = min(BPL - 1, c // 3)
        elif self.ascii_x + self.cw <= x < self.ascii_x + (BPL + 1) * self.cw:
            col = (x - self.ascii_x - self.cw) // self.cw
        if col is None:
            return None
        off = line * BPL + int(col)
        return off if 0 <= off < self.size else None

    def _hex_cell(self, col: int) -> int:
        return self.hex_x + (col * 3 + (1 if col >= 8 else 0)) * self.cw

    # ---- 그리기 ----
    def paintEvent(self, e):
        p = QPainter(self.viewport())
        p.fillRect(self.viewport().rect(), color("bg-200"))
        if not self._read or self.size == 0:
            return
        p.setFont(self.font())
        p.translate(-self.horizontalScrollBar().value(), 0)
        top = self.verticalScrollBar().value()
        vis = self._visible_lines() + 1
        first = top * BPL
        data = self._read(first, vis * BPL)
        sel = None
        if self.anchor >= 0 and self.cursor >= 0 and self.anchor != self.cursor:
            sel = (min(self.anchor, self.cursor), max(self.anchor, self.cursor))
        sel_bg = color("selection")
        text_c = color("ink")
        header_bg, value_bg = color("hex-header"), color("hex-value")
        cursor_c = color("hex-cursor")
        ink = color("ink")
        for li in range(vis):
            base = first + li * BPL
            if base >= self.size:
                break
            y = li * self.lh
            chunk = data[li * BPL:(li + 1) * BPL]
            p.setPen(color("ink-muted"))
            p.drawText(0, y + self.asc + 1, format_offset(base, self.size))
            for i, b in enumerate(chunk):
                off = base + i
                bg = None
                selected = bool(sel and sel[0] <= off <= sel[1])
                if selected:
                    bg = sel_bg
                elif self.hl:
                    s, h, t = self.hl
                    if s <= off < s + h:
                        bg = header_bg
                    elif s + h <= off < s + t:
                        bg = value_bg
                hx = self._hex_cell(i)
                ax = self.ascii_x + (i + 1) * self.cw
                if bg is not None:
                    w = 2 * self.cw if i == BPL - 1 else 3 * self.cw
                    p.fillRect(QRect(hx, y, w, self.lh), bg)
                    p.fillRect(QRect(ax, y, self.cw, self.lh), bg)
                # 선택 → HighlightedText(ink), Hex 하이라이트 바탕 → ink, 그 외 → 기본 글자색
                # 선택·Hex 하이라이트 바탕 위 글자는 ink (가독성 규칙)
                p.setPen(ink if bg is not None else text_c)
                p.drawText(hx, y + self.asc + 1, f"{b:02X}")
                p.drawText(ax, y + self.asc + 1, chr(b) if 0x20 <= b <= 0x7E else ".")
                if off == self.cursor:
                    p.setPen(QPen(cursor_c, 1))
                    p.drawRect(QRect(hx - 1, y, 2 * self.cw + 1, self.lh - 1))
                    p.drawRect(QRect(ax, y, self.cw, self.lh - 1))
            p.setPen(text_c)
            p.drawText(self.ascii_x, y + self.asc + 1, "|")
            p.drawText(self.ascii_x + (len(chunk) + 1) * self.cw, y + self.asc + 1, "|")

    # ---- 입력 ----
    def move_cursor(self, off: int, select: bool = False) -> None:
        if self.size == 0:
            return
        off = max(0, min(self.size - 1, off))
        if select:
            if self.anchor < 0:
                self.anchor = self.cursor if self.cursor >= 0 else off
        else:
            self.anchor = -1
        self.cursor = off
        self.ensure_visible(off)
        self.viewport().update()
        self.cursorMoved.emit(off)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            off = self._offset_at(e.position().toPoint())
            if off is not None:
                shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                if not shift:
                    self.anchor = off
                    self.cursor = off
                    self.viewport().update()
                    self.cursorMoved.emit(off)
                else:
                    self.move_cursor(off, True)
                self._dragging = True
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._dragging:
            off = self._offset_at(e.position().toPoint())
            if off is not None and off != self.cursor:
                self.cursor = off
                self.viewport().update()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._dragging and self.anchor == self.cursor:
            self.anchor = -1
        self._dragging = False
        super().mouseReleaseEvent(e)

    def wheelEvent(self, e):
        steps = -e.angleDelta().y() // 40
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + steps)

    def keyPressEvent(self, e):
        if e.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection()
            return
        if e.key() == Qt.Key.Key_G and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.goto_dialog()
            return
        if self.size == 0:
            return super().keyPressEvent(e)
        cur = self.cursor if self.cursor >= 0 else self.verticalScrollBar().value() * BPL
        shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        ctrl = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
        page = self._visible_lines() * BPL
        k = e.key()
        target = {
            Qt.Key.Key_Left: cur - 1,
            Qt.Key.Key_Right: cur + 1,
            Qt.Key.Key_Up: cur - BPL,
            Qt.Key.Key_Down: cur + BPL,
            Qt.Key.Key_PageUp: cur - page,
            Qt.Key.Key_PageDown: cur + page,
            Qt.Key.Key_Home: 0 if ctrl else cur - cur % BPL,
            Qt.Key.Key_End: self.size - 1 if ctrl else cur - cur % BPL + BPL - 1,
        }.get(k)
        if target is None:
            return super().keyPressEvent(e)
        if k in (Qt.Key.Key_Up, Qt.Key.Key_PageUp) and target < 0:
            target = cur % BPL if k == Qt.Key.Key_Up else 0
        self.move_cursor(target, shift)
        if k in (Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            vs = self.verticalScrollBar()
            vs.setValue(vs.value() + (-1 if k == Qt.Key.Key_PageUp else 1) * self._visible_lines())

    def selection(self) -> tuple[int, int] | None:
        if self.anchor >= 0 and self.cursor >= 0 and self.anchor != self.cursor:
            return (min(self.anchor, self.cursor), max(self.anchor, self.cursor))
        if self.cursor >= 0:
            return (self.cursor, self.cursor)
        return None

    def copy_selection(self) -> None:
        s = self.selection()
        if not s or not self._read:
            return
        n = min(s[1] - s[0] + 1, 16 << 20)
        data = self._read(s[0], n)
        QGuiApplication.clipboard().setText(" ".join(f"{b:02X}" for b in data))

    def goto_dialog(self) -> None:
        if self.size == 0:
            return
        label = self.tr("Offset to go to (hex, 0 - {0})").format(f"{self.size - 1:X}")
        text = ""
        while True:
            text, ok = QInputDialog.getText(self, self.tr("Go to Offset"), label, QLineEdit.EchoMode.Normal, text)
            if not ok:
                return
            off = parse_hex_offset(text)
            if off is not None and 0 <= off < self.size:
                break
            err = self.tr("Invalid value. Enter a hex value between 0 and {0}.").format(f"{self.size - 1:X}")
            label = f"<span style='color:{hex_('danger')}'>{err}</span><br>" + self.tr("Offset to go to (hex)")
        self.anchor = -1
        line = off // BPL
        self.verticalScrollBar().setValue(max(0, line - 1))
        self.move_cursor(off)


class RawPanel(QWidget):
    """RAW 영역. 툴바 + Deflate 안내줄 + 정보 줄 + Hex 뷰/안내 스택."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.toolbar = AreaToolbar(lambda: "RAW")
        self.toolbar.lay.addStretch(1)
        self.toolbar.finish()
        lay.addWidget(self.toolbar)
        self.deflate_note = QLabel()
        self.deflate_note.setProperty("role", "danger")
        self.deflate_note.setContentsMargins(6, 2, 6, 2)
        self.deflate_note.hide()
        lay.addWidget(self.deflate_note)
        self.info = QLabel("")
        self.info.setFont(mono_font("mono-sm"))
        self.info.setProperty("role", "info")
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.info)
        self.stack = QStackedWidget()
        self.hex = HexView()
        self.msg = QLabel("")
        self.msg.setProperty("role", "page")
        self.msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg.setWordWrap(True)
        self.stack.addWidget(self.hex)
        self.stack.addWidget(self.msg)
        lay.addWidget(self.stack, 1)
        self._msg_fn: _Fn[[], str] | None = None
        self._info_fn: _Fn[[], str] | None = None
        self.show_message("")
        theme.notifier().changed.connect(lambda *_: self.hex.viewport().update())
        self.retranslate()

    def retranslate(self) -> None:
        self.deflate_note.setText(self.tr("Tags and byte positions cannot be linked in a Deflate-compressed file."))
        if self._msg_fn is not None:
            self.msg.setText(self._msg_fn())
        if self.info.isVisible():
            self.info.setText(self._info_fn() if self._info_fn else self._size_text())

    def changeEvent(self, e):
        if e.type() == QEvent.Type.LanguageChange:
            self.retranslate()
        super().changeEvent(e)

    def show_message(self, text) -> None:
        """text는 문자열 또는 번역 문자열을 돌려주는 함수(언어가 바뀌면 다시 부른다)."""
        self.hex.clear()
        self.info.setText("")
        self.info.setVisible(False)
        self.deflate_note.hide()
        self._msg_fn = text if callable(text) else (lambda t=text: t)
        self.msg.setText(self._msg_fn())
        self.stack.setCurrentIndex(1)

    def show_bytes(self, read, size: int, deflate: bool = False) -> None:
        self.hex.set_source(read, size)
        self.deflate_note.setVisible(deflate)
        self.info.setVisible(True)
        self.set_info(None)
        self.stack.setCurrentIndex(0)

    def set_info(self, text) -> None:
        """text는 문자열, 함수 또는 None(파일 크기 표시)."""
        self._info_fn = None if text is None else (text if callable(text) else (lambda t=text: t))
        self.info.setText(self._info_fn() if self._info_fn else self._size_text())

    def _size_text(self) -> str:
        return self.tr("File size {0} bytes").format(f"{self.hex.size:,}")

    def min_width(self) -> int:
        return self.hex.line_width_px()
