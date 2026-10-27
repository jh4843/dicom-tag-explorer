# 시작 화면. 무거운 모듈을 불러오고 메인 창을 만드는 동안 "Loading… n / 5"와 진행 막대를 보여준다.
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QCursor, QGuiApplication, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from . import theme
from .icons import resources_dir

STEPS = 5
# 크기는 모두 논리 픽셀이다. Qt가 모니터 배율(100%~200%, 소수 배율 포함)에 맞춰 키우므로 화면에서 차지하는 비율이 같다
WIDTH, HEIGHT, LOGO, BAR = 480, 200, 48, 4


class _Logo(QWidget):
    """앱 아이콘을 매번 벡터로 그린다. 비트맵을 늘리지 않아 125%·150% 같은 소수 배율에서도 흐려지지 않는다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(LOGO, LOGO)
        svg = (resources_dir() / "app.svg").read_text(encoding="utf-8")
        self._renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")), self)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._renderer.render(p, QRectF(self.rect()))
        p.end()


class Splash(QWidget):
    def __init__(self, version: str):
        super().__init__(None, Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("splash")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedSize(WIDTH, HEIGHT)
        c = theme.hex_
        self.setStyleSheet(
            f"#splash {{ background: {c('bg-200')}; border: 1px solid {c('line')}; }}"
            f"QLabel {{ background: transparent; color: {c('ink')}; }}"
            f"QLabel[muted='true'] {{ color: {c('ink-muted')}; }}"
            f"QProgressBar {{ background: {c('bg-400')}; border: none; border-radius: {BAR // 2}px; }}"
            f"QProgressBar::chunk {{ background: {c('accent')}; border-radius: {BAR // 2}px; }}")

        name = QLabel("DICOM Tag Explorer")
        name.setFont(theme.font("title"))
        ver = QLabel(f"v{version}")
        ver.setFont(theme.font("caption"))
        ver.setProperty("muted", True)
        title = QVBoxLayout()
        title.setSpacing(theme.px("space-1"))
        title.addWidget(name)
        title.addWidget(ver)
        head = QHBoxLayout()
        head.setSpacing(theme.px("space-5"))
        head.addWidget(_Logo())
        head.addLayout(title)
        head.addStretch(1)

        self.status = QLabel("Loading…")
        self.status.setFont(theme.font("body"))
        self.counter = QLabel()
        self.counter.setFont(theme.font("mono-sm"))
        self.counter.setProperty("muted", True)
        row = QHBoxLayout()
        row.addWidget(self.status)
        row.addStretch(1)
        row.addWidget(self.counter)
        self.bar = QProgressBar()
        self.bar.setRange(0, STEPS)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(BAR)

        lay = QVBoxLayout(self)
        m = theme.px("space-8")
        lay.setContentsMargins(m, m, m, m)
        lay.setSpacing(theme.px("space-4"))
        lay.addLayout(head)
        lay.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(self.bar)
        self.step(1)

    def show_centered(self) -> None:
        """실행한 곳(마우스가 있는 모니터)의 작업 영역 가운데에 띄운다. 좌표는 그 모니터 기준 논리 픽셀이다."""
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.move(area.x() + (area.width() - WIDTH) // 2, area.y() + (area.height() - HEIGHT) // 2)
        self.show()
        self.raise_()
        QApplication.processEvents()

    def step(self, n: int) -> None:
        """n번째 단계(1~STEPS)에 들어간다. 이어지는 작업이 UI 스레드를 막으므로 여기서 바로 다시 그린다."""
        n = max(1, min(STEPS, n))
        self.counter.setText(f"{n} / {STEPS}")
        self.bar.setValue(n)
        if self.isVisible():
            self.repaint()
            QApplication.processEvents()
