# Image 영역. QGraphicsView로 Instance 이미지와 WSI 타일(피라미드) 뷰를 Pan/Zoom/90° 회전한다.
from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass

import numpy as np
from PIL import Image
from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QBrush, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QLabel, QStackedWidget,
    QToolButton, QToolTip, QVBoxLayout, QWidget,
)

from ..core.image_decode import OK, decode_first_frame
from ..core.wsi import Slide, TileError
from ..workers.tasks import Generation, clear_pool, submit
from . import theme
from .common import AreaToolbar, tr_core
from .theme import color

ZOOM_STEP = 1.25
ZOOM_MIN, ZOOM_MAX = 0.01, 16.0
# 타일 캐시 상한 (L-05): QPixmap 32bpp 기준 바이트. 저장되지 않음·실패 표시는 0바이트로 세고 항목 수를 제한한다
CACHE_BYTES = 256 * 1024 * 1024
CACHE_ITEMS = 65536
# 단일 레벨 모드에서 동시에 요청하는 최대 타일 수. 끝나면 다음 묶음을 요청한다 (2.5)
MAX_REQUEST = 128


def tile_reduction(ratio: float, tile_px: int) -> int:
    """화면 픽셀 / 레벨 픽셀 비율에 맞는 타일 축소 단계(2의 거듭제곱). 축소 타일은 화면 크기의 1~2배다."""
    r = 1
    while ratio * r * 2 <= 1 and r * 2 <= tile_px:
        r *= 2
    return r


def array_to_qimage(a: np.ndarray) -> QImage:
    """워커에서 호출한다. QPixmap은 만들지 않는다."""
    a = np.ascontiguousarray(a)
    h, w = a.shape[:2]
    if a.ndim == 2:
        return QImage(a.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
    return QImage(a.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


def decode_job(path, transfer_syntax: str, has_pixel_data: bool):
    """워커: 첫 프레임 디코딩 → (상태, QImage, 상세)."""
    r = decode_first_frame(path, transfer_syntax, has_pixel_data)
    return (r.status, array_to_qimage(r.array) if r.status == OK else None, r.detail)


def tile_job(slide: Slide, level: int, x: int, y: int, z, path, reduce: int = 1):
    try:
        r = slide.read_tile(level, x, y, z, path)
    except TileError as e:
        return ("fail", None, str(e))
    except Exception as e:  # wsidicom/디코더 오류
        return ("fail", None, f"{type(e).__name__}: {e}")
    if r.sparse:
        return ("sparse", None, "")
    a = r.array
    if reduce > 1:  # 축소 표시용. 박스 평균으로 줄여 캐시 메모리를 화면 크기 수준으로 묶는다
        a = np.asarray(Image.fromarray(a).reduce(reduce))
    return ("ok", array_to_qimage(a), "")


class TileCache:
    """메모리 상한 LRU. 항목 크기는 QPixmap 가로 × 세로 × 4 바이트."""

    def __init__(self, max_bytes: int = CACHE_BYTES, max_items: int = CACHE_ITEMS):
        self.max_bytes = max_bytes
        self.max_items = max_items
        self._d: OrderedDict = OrderedDict()
        self.bytes = 0

    @staticmethod
    def cost(val) -> int:
        return val.width() * val.height() * 4 if isinstance(val, QPixmap) else 0

    def __contains__(self, k) -> bool:
        return k in self._d

    def __len__(self) -> int:
        return len(self._d)

    def get(self, k):
        v = self._d.get(k)
        if v is not None:
            self._d.move_to_end(k)
        return v

    def put(self, k, val) -> None:
        if k in self._d:
            self.bytes -= self.cost(self._d.pop(k))
        self._d[k] = val
        self.bytes += self.cost(val)
        while self._d and (self.bytes > self.max_bytes or len(self._d) > self.max_items):
            _, old = self._d.popitem(last=False)
            self.bytes -= self.cost(old)

    def items(self):
        return list(self._d.items())

    def clear(self) -> None:
        self._d.clear()
        self.bytes = 0

    def capacity(self, tile_w: int, tile_h: int) -> int:
        """타일 크기 기준 캐시 용량(장)."""
        return max(1, min(self.max_items, self.max_bytes // max(1, tile_w * tile_h * 4)))


@dataclass
class TileReq:
    gen: int
    task: object = None


class TileLayer(QGraphicsItem):
    """현재 레벨의 보이는 타일을 그린다. 장면 단위는 레벨 0 픽셀이다."""

    def __init__(self, view: "ImageView"):
        super().__init__()
        self.view = view
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption, True)

    def boundingRect(self) -> QRectF:
        return self.view.scene_rect()

    def paint(self, p: QPainter, option, widget=None):
        v = self.view
        if v.slide is None:
            return
        info = v.slide.levels[v.level]
        d = info.downsample
        tw, th = info.tile_size
        W, H = v.slide.levels[0].size
        r = option.exposedRect
        img = QRectF(0, 0, W, H)
        # 읽는 중 타일은 바탕 한 번으로 칠한다 (C++ 호출 수를 줄여 워커와의 GIL 경합을 줄인다)
        p.fillRect(r.intersected(img), color("tile-loading"))
        x0, y0, x1, y1 = v.tile_range(r)
        cache = v.cache
        base = (id(v.slide), v.level)
        items = [(k, st) for k, st in cache.items()
                 if k[:2] == base and k[4] == v.z and k[5] == v.path and x0 <= k[2] <= x1 and y0 <= k[3] <= y1]
        # 다른 축소 단계 타일은 새 단계가 읽히는 동안 밑그림으로 쓰고, 현재 단계를 위에 그린다
        items.sort(key=lambda it: it[0][6] == v.reduction)
        for k, st in items:
            tx, ty, rd = k[2], k[3], k[6]
            if rd != v.reduction and not isinstance(st, QPixmap):
                continue
            rect = QRectF(tx * tw * d, ty * th * d, tw * d, th * d).intersected(img)
            if isinstance(st, QPixmap):
                p.drawPixmap(rect, st, QRectF(0, 0, rect.width() / d / rd, rect.height() / d / rd))
            elif st == "sparse":
                p.fillRect(rect, color("tile-sparse"))
                p.fillRect(rect, QBrush(color("tile-hatch"), Qt.BrushStyle.BDiagPattern))
            else:  # ("fail", 원인)
                p.fillRect(rect, color("tile-sparse"))
                pen = QPen(color("danger"))
                pen.setCosmetic(True)
                pen.setWidth(2)
                p.setPen(pen)
                p.drawLine(rect.topLeft(), rect.bottomRight())
                p.drawLine(rect.topRight(), rect.bottomLeft())


class ImageView(QGraphicsView):
    viewChanged = Signal()  # 배율·레벨 표시 갱신
    tilesPending = Signal(int)

    def __init__(self, tile_pool: QThreadPool, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.pool = tile_pool
        self.gen = Generation()
        self.rotation = 0
        self._fitted = False
        self.pix_item: QGraphicsPixmapItem | None = None
        self.slide: Slide | None = None
        self.multi_level = False
        self.level = 0
        self.label_prefix = ""
        self.z = None
        self.path = None
        self.reduction = 1  # 타일 축소 단계 (tile_reduction)
        self.cache = TileCache()
        self.inflight: dict[tuple, TileReq] = {}
        self.layer: TileLayer | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._update_tiles)
        self.horizontalScrollBar().valueChanged.connect(self._schedule)
        self.verticalScrollBar().valueChanged.connect(self._schedule)

    # ---- 내용 ----
    def scene_rect(self) -> QRectF:
        if self.slide is not None:
            W, H = self.slide.levels[0].size
            return QRectF(0, 0, W, H)
        if self.pix_item is not None:
            return self.pix_item.boundingRect()
        return QRectF()

    def clear_content(self) -> None:
        self._stop_tiles()
        self.scene().clear()
        self.pix_item = None
        self.layer = None
        if self.slide is not None:
            self.slide = None  # 닫기는 소유자(ImagePanel)가 한다
        self.cache.clear()

    def set_image(self, img: QImage) -> None:
        self.clear_content()
        self.pix_item = self.scene().addPixmap(QPixmap.fromImage(img))
        self.pix_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.scene().setSceneRect(self.pix_item.boundingRect())
        self.reset_view()

    def set_slide(self, slide: Slide, multi_level: bool, label_prefix: str = "") -> None:
        self.clear_content()
        self.slide = slide
        self.multi_level = multi_level
        self.label_prefix = label_prefix
        self.z = slide.default_z
        self.path = slide.default_path
        self.level = len(slide.levels) - 1 if multi_level else 0
        self.layer = TileLayer(self)
        self.scene().addItem(self.layer)
        self.scene().setSceneRect(self.scene_rect())
        self.reset_view()

    # ---- 보기 ----
    def scale_factor(self) -> float:
        t = self.transform()
        return math.hypot(t.m11(), t.m12())

    def fit_scale(self) -> float:
        r = self.scene_rect()
        if r.isEmpty():
            return 1.0
        vw, vh = max(1, self.viewport().width()), max(1, self.viewport().height())
        w, h = (r.height(), r.width()) if self.rotation % 180 else (r.width(), r.height())
        return min(vw / w, vh / h)

    def _apply(self, scale: float) -> None:
        lo = min(ZOOM_MIN, self.fit_scale())
        scale = max(lo, min(ZOOM_MAX, scale))
        self.resetTransform()
        self.rotate(self.rotation)
        self.scale(scale, scale)
        self._schedule(force=True)

    def reset_view(self) -> None:
        self.rotation = 0
        self.fit()

    def fit(self) -> None:
        self._apply(self.fit_scale())
        self.centerOn(self.scene_rect().center())
        self._fitted = True  # 사용자가 바꾸기 전까지 크기 변경 시 다시 맞춘다

    def one_to_one(self) -> None:
        self._fitted = False
        c = self.mapToScene(self.viewport().rect().center())
        self._apply(1.0)
        self.centerOn(c)

    def zoom(self, factor: float, anchor_mouse: bool = False) -> None:
        self._fitted = False
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse if anchor_mouse
                                     else QGraphicsView.ViewportAnchor.AnchorViewCenter)
        s = self.scale_factor()
        target = max(min(ZOOM_MIN, self.fit_scale()), min(ZOOM_MAX, s * factor))
        k = target / s
        if abs(k - 1) > 1e-9:
            self.scale(k, k)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._schedule(force=True)

    def rotate_by(self, deg: int) -> None:
        c = self.mapToScene(self.viewport().rect().center())
        self.rotation = (self.rotation + deg) % 360
        if self._fitted:
            self.fit()
            return
        s = self.scale_factor()
        self.resetTransform()
        self.rotate(self.rotation)
        self.scale(s, s)
        self.centerOn(c)  # 뷰 중앙 기준 회전
        self._schedule(force=True)

    def wheelEvent(self, e):
        dy = e.angleDelta().y()
        if dy == 0:
            return
        self.zoom(ZOOM_STEP if dy > 0 else 1 / ZOOM_STEP, anchor_mouse=True)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._fitted and not self.scene_rect().isEmpty():
            self.fit()
        self._schedule(force=True)

    def mousePressEvent(self, e):
        self._fitted = False
        super().mousePressEvent(e)

    def zoom_text(self) -> str:
        if self.slide is None and self.pix_item is None:
            return ""
        pct = self.scale_factor() * 100
        pct_s = f"{pct:.0f}%" if pct >= 1 else f"{pct:.2f}%"
        if self.slide is not None:
            lab = f"L{self.level}" if self.multi_level else self.label_prefix
            if self.multi_level and len(self.slide.focal_planes) >= 2:
                lab += f" z{self.slide.focal_planes.index(self.z) if self.z in self.slide.focal_planes else 0}"
            if self.multi_level and len(self.slide.optical_paths) >= 2:
                lab += f" OP {self.path}"
            return f"{lab} / {pct_s}".strip()
        return pct_s

    # ---- 타일 ----
    def _schedule(self, *_, force: bool = False) -> None:
        self.viewChanged.emit()
        if self.slide is None:
            return
        if force or not self._timer.isActive():
            self._timer.start()

    def _key(self, tx, ty):
        return (id(self.slide), self.level, tx, ty, self.z, self.path, self.reduction)

    def tile_range(self, r: QRectF) -> tuple[int, int, int, int]:
        info = self.slide.levels[self.level]
        tw, th = info.tile_size[0] * info.downsample, info.tile_size[1] * info.downsample
        nx, ny = info.tiles
        x0 = max(0, int(r.left() // tw))
        y0 = max(0, int(r.top() // th))
        x1 = min(nx - 1, int(r.right() // tw))
        y1 = min(ny - 1, int(r.bottom() // th))
        return x0, y0, x1, y1

    def tile_state(self, tx, ty):
        k = self._key(tx, ty)
        st = self.cache.get(k)
        if st is not None:
            self.cache.move_to_end(k)
        return st

    def _stop_tiles(self) -> None:
        self.gen.next()
        clear_pool(self.pool)
        self.inflight.clear()
        self.tilesPending.emit(0)

    def _update_tiles(self) -> None:
        if self.slide is None:
            return
        if self.multi_level:
            self.level = self.slide.best_level(self.scale_factor())
        g = self.gen.next()
        clear_pool(self.pool)  # 시작 전 요청을 버린다
        self.inflight = {k: r for k, r in self.inflight.items() if getattr(r.task, "started", False)}
        vis = self.mapToScene(self.viewport().rect()).boundingRect().intersected(self.scene_rect())
        if vis.isEmpty():
            self.tilesPending.emit(0)
            return
        x0, y0, x1, y1 = self.tile_range(vis)
        c = vis.center()
        info = self.slide.levels[self.level]
        tw, th = info.tile_size[0] * info.downsample, info.tile_size[1] * info.downsample
        ratio = self.scale_factor() * info.downsample * self.devicePixelRatioF()
        self.reduction = tile_reduction(ratio, max(info.tile_size))
        need = [(tx, ty) for ty in range(y0, y1 + 1) for tx in range(x0, x1 + 1)]
        need.sort(key=lambda t: ((t[0] + .5) * tw - c.x()) ** 2 + ((t[1] + .5) * th - c.y()) ** 2)
        budget = len(need)
        if not self.multi_level:
            # 축소하면 수천 장이 보일 수 있다. 캐시 절반 이하만 대상으로 해 서로 밀어내며 다시 읽지 않게 하고,
            # 동시 요청은 MAX_REQUEST장으로 묶는다 (나머지는 _on_tile에서 다음 묶음으로 요청)
            rw, rh = (-(-s // self.reduction) for s in info.tile_size)
            need = need[:self.cache.capacity(rw, rh) // 2]
            budget = MAX_REQUEST - len(self.inflight)
        for tx, ty in need:
            k = self._key(tx, ty)
            if k in self.cache:
                continue
            req = self.inflight.get(k)
            if req is not None:
                req.gen = g  # 실행 중이고 여전히 보이는 타일은 새 세대로 넘긴다
                continue
            if budget <= 0:
                break
            budget -= 1
            req = TileReq(g)
            req.task = submit(self.pool, tile_job, self.slide, self.level, tx, ty, self.z, self.path, self.reduction,
                              on_done=self._on_tile, tag=(k, req))
            self.inflight[k] = req
        self.tilesPending.emit(len(self.inflight))
        self.viewChanged.emit()  # 레벨이 바뀌었을 수 있다
        if self.layer is not None:
            self.layer.update()

    def _on_tile(self, result, tag) -> None:
        k, req = tag
        if self.inflight.get(k) is req:
            del self.inflight[k]
        if not self.gen.is_current(req.gen) or k[0] != id(self.slide):
            self.tilesPending.emit(len(self.inflight))
            return  # 늦게 끝난 이전 세대 결과는 버린다
        status, img, detail = result
        if status == "ok":
            val = QPixmap.fromImage(img)
        elif status == "sparse":
            val = "sparse"
        else:
            val = ("fail", detail)
        self.cache.put(k, val)
        self.tilesPending.emit(len(self.inflight))
        if self.layer is not None:
            self.layer.update()
        if not self.inflight and not self.multi_level:
            self._schedule()  # 다음 묶음 (남은 타일이 없으면 요청 없이 끝난다)

    def viewportEvent(self, e):
        if e.type() == e.Type.ToolTip and self.slide is not None:
            sp = self.mapToScene(e.pos())
            info = self.slide.levels[self.level]
            tx = int(sp.x() // (info.tile_size[0] * info.downsample))
            ty = int(sp.y() // (info.tile_size[1] * info.downsample))
            st = self.cache.get(self._key(tx, ty))
            if isinstance(st, tuple):
                QToolTip.showText(e.globalPos(), self.tr("Tile ({0}, {1}) read failed: {2}").format(tx, ty, tr_core(st[1])), self)
            else:
                QToolTip.hideText()
            return True
        return super().viewportEvent(e)


class ImagePanel(QWidget):
    statusChanged = Signal(str)  # 상태바 배율 표시
    tilesPending = Signal(int)

    TOOL_COMMANDS = ("view.image_fit", "view.image_actual", "view.zoom_out", "view.zoom_in", None,
                     "view.rotate_left", "view.rotate_right")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tile_pool = QThreadPool(self)
        self.tile_pool.setMaxThreadCount(4)
        self.slide: Slide | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.toolbar = AreaToolbar(lambda: self.tr("Image"), edge_right=True)
        self.view = ImageView(self.tile_pool)
        self.zoom_label = QLabel("")
        self.zoom_label.setProperty("role", "muted")
        self.zoom_label.setFont(theme.font("mono-sm"))
        self.zoom_label.setMinimumWidth(110)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.toolbar)

        self.stack = QStackedWidget()
        self.msg = QLabel("")
        self.msg.setProperty("role", "page")  # 안내문은 캔버스(bg-000)가 아니라 bg-200 위에 ink로 쓴다
        self.msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg.setWordWrap(True)
        self.stack.addWidget(self.msg)
        self.stack.addWidget(self.view)
        lay.addWidget(self.stack, 1)
        self.setMinimumWidth(320)
        self._msg_fn = lambda: ""
        self.view.viewChanged.connect(self._on_view_changed)
        self.view.tilesPending.connect(self.tilesPending.emit)
        theme.notifier().changed.connect(self.apply_theme)
        self.apply_theme()

    def bind_actions(self, reg) -> None:
        """레지스트리의 Image 명령을 툴바 버튼으로 둔다 (단축키는 레지스트리가 Image 영역 범위로 처리)."""
        tb = self.toolbar.lay
        tb.addStretch(1)
        for name in self.TOOL_COMMANDS:
            if name is None:
                tb.addWidget(self.zoom_label)
                continue
            b = QToolButton()
            b.setAutoRaise(True)
            b.setDefaultAction(reg[name])
            b.setIconSize(QSize(theme.px("size-icon-sm"), theme.px("size-icon-sm")))
            tb.addWidget(b)
        self.toolbar.finish()

    def _on_view_changed(self) -> None:
        t = self.view.zoom_text()
        self.zoom_label.setText(t)
        self.statusChanged.emit(t)

    def _close_slide(self) -> None:
        self.view.clear_content()
        if self.slide is not None:
            try:
                self.slide.close()
            except Exception:
                pass
            self.slide = None

    def show_message(self, text, tooltip: str = "") -> None:
        """text는 문자열 또는 번역 문자열을 돌려주는 함수(언어가 바뀌면 다시 부른다)."""
        self._close_slide()
        self._msg_fn = text if callable(text) else (lambda t=text: t)
        self.msg.setText(self._msg_fn())
        self.msg.setToolTip(tooltip)
        self.stack.setCurrentWidget(self.msg)
        self._on_view_changed()

    def changeEvent(self, e):
        if e.type() == QEvent.Type.LanguageChange:
            self.msg.setText(self._msg_fn())
        super().changeEvent(e)

    def show_image(self, img: QImage) -> None:
        self._close_slide()
        self.stack.setCurrentWidget(self.view)
        self.view.set_image(img)

    def show_slide(self, slide: Slide, multi_level: bool, label: str = "") -> None:
        self._close_slide()
        self.slide = slide
        self.stack.setCurrentWidget(self.view)
        self.view.set_slide(slide, multi_level, label)

    def apply_theme(self, *_) -> None:
        self.view.setBackgroundBrush(color("bg-000"))  # 두 테마 모두 어두운 캔버스
        self.view.viewport().update()
