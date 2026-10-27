# QApplication을 만들고 메인 창을 띄운다. 전역 예외를 로그 파일에 기록한다.
from __future__ import annotations

import faulthandler
import gc
import logging
import sys
import traceback

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from . import __version__
from .appdata import app_settings, init_settings_path, log_dir

_fault_stream = None


def _setup_logging() -> None:
    path = log_dir() / "app.log"
    logging.basicConfig(filename=path, level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # windowed exe에서는 stdout/stderr가 None이다. 워커의 traceback 출력이 실패하지 않게 로그로 보낸다
    if sys.stderr is None or sys.stdout is None:
        stream = open(path, "a", encoding="utf-8", buffering=1)
        if sys.stderr is None:
            sys.stderr = stream
        if sys.stdout is None:
            sys.stdout = stream

    # 네이티브 크래시 시 Python 스레드 스택을 로그에 남긴다
    global _fault_stream
    _fault_stream = open(path, "a", encoding="utf-8", buffering=1)
    faulthandler.enable(file=_fault_stream, all_threads=True)

    def hook(exc_type, exc, tb):
        logging.getLogger("vw").error("처리되지 않은 예외\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        if sys.__stderr__ is not None:
            sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = hook


def tune_gil() -> None:
    """UI 스레드 응답성. Qt는 모델·paint 콜백마다 GIL을 다시 잡는데, 워커가 순수 Python 작업 중이면
    콜백마다 전환 간격(기본 5 ms)만큼 기다린다. 0.5 ms로 줄이면 L0 첫 렌더링 정지가 1.6 s → 0.04 s가 된다."""
    sys.setswitchinterval(0.0005)


GC_INTERVAL_MS = 100


def gc_on_ui_thread(app: QApplication) -> QTimer:
    """순환 GC를 UI 스레드에서만 돌린다 (QA-05).
    자동 GC는 할당한 스레드에서 시작되므로 워커(파일 열기 등)에서도 돈다. 그때 UI 스레드가 PySide6 호출에 임시 값
    객체를 넘기는 중이면(QStandardItem.setForeground(QBrush()), QPainter.setPen(QPen(...)) 등) access violation이 난다
    (PySide6 6.11, Python 3.14에서 재현, scripts/stress_gc_thread.py). 자동 GC를 끄고 타이머가 같은 임계값으로 수집한다."""
    gc.disable()
    timer = QTimer(app)
    timer.setInterval(GC_INTERVAL_MS)
    timer.timeout.connect(_collect_if_due)
    timer.start()
    return timer


def _collect_if_due() -> None:
    if gc.get_count()[0] >= gc.get_threshold()[0]:
        # 자동 GC와 같은 한 단계(3.14 증분 GC). collect(0)을 섞으면 오래된 세대 쓰레기를 끝내 거두지 못했다
        gc.collect(1)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    _setup_logging()
    tune_gil()
    logging.getLogger("vw").info("시작 v%s", __version__)
    app = QApplication(argv)
    app.setApplicationName("DicomTagExplorer")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Vieworks")
    gc_on_ui_thread(app)
    init_settings_path()
    from .ui import i18n, theme
    from .ui.icons import app_icon
    from .ui.splash import Splash
    app.setWindowIcon(app_icon())
    # 시작 화면이 깜빡이지 않도록 메인 창을 만들기 전에 저장된 테마·언어를 적용한다 (Spec 2.8.6).
    # main_window는 무거운 라이브러리를 끌고 오므로 같은 키를 여기서 직접 읽는다
    s = app_settings()
    th = str(s.value("ui/theme", theme.DEFAULT))
    theme.apply(app, th if th in theme.THEMES else theme.DEFAULT)
    i18n.apply(app, str(s.value("ui/language", i18n.DEFAULT)))  # 모르는 언어는 apply가 기본값으로 바꾼다
    splash = Splash(__version__)
    splash.show_centered()
    import numpy, pydicom  # noqa: F401,E401  단계 1: 무거운 import를 단계로 나눠 진행률을 움직인다
    splash.step(2)
    import wsidicom  # noqa: F401
    splash.step(3)
    from .ui.main_window import MainWindow
    splash.step(4)
    w = MainWindow()
    splash.step(5)
    w.show()
    splash.close()
    return app.exec()
