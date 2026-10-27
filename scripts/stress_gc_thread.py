# 워커 스레드 GC와 UI 스레드의 PySide6 호출이 겹칠 때의 네이티브 크래시(QA-05)를 재현·확인하는 스트레스 스크립트.
"""사용법: .venv\\Scripts\\python scripts\\stress_gc_thread.py [auto|app] [초]

UI 스레드는 QStandardItem과 QPainter에 임시 QBrush/QFont/QPen을 넘기고, 풀 스레드 3개는 순환 객체를 계속 만든다.
- auto: Python 기본 동작(자동 GC가 할당한 스레드에서 돈다). 이 조합(PySide6 6.11, Python 3.14)에서는 수 초 안에
  access violation으로 죽는다.
- app: 앱과 같이 gc_on_ui_thread()로 GC를 UI 스레드에서만 돌린다. 끝까지 살아 "OK"를 출력하고 0으로 끝나야 한다.
"""
from __future__ import annotations

import faulthandler
import gc
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtCore import QRect, QRunnable, QThreadPool  # noqa: E402
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QStandardItem, QStandardItemModel  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from dicom_tag_explorer.app import gc_on_ui_thread, tune_gil  # noqa: E402


class Churn(QRunnable):
    """순환 쓰레기를 계속 만들어 이 스레드에서 GC가 시작되게 한다."""

    def __init__(self, stop: threading.Event):
        super().__init__()
        self.stop = stop

    def run(self) -> None:
        while not self.stop.is_set():
            junk = []
            for i in range(2000):
                d = {"a": [i], "b": (i, str(i))}
                d["self"] = d
                junk.append(d)


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "app"
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
    faulthandler.enable(all_threads=True)
    tune_gil()
    app = QApplication([])
    gc.set_threshold(50, 10, 10)  # GC를 자주 돌려 겹칠 기회를 늘린다
    if mode == "app":
        gc_on_ui_thread(app)
    stop = threading.Event()
    pool = QThreadPool()
    pool.setMaxThreadCount(3)
    for _ in range(3):
        c = Churn(stop)
        c.setAutoDelete(True)
        pool.start(c)
    model = QStandardItemModel(0, 2)
    img = QImage(200, 200, QImage.Format.Format_ARGB32)
    t0 = time.perf_counter()
    n = 0
    while time.perf_counter() - t0 < secs:
        model.clear()
        for i in range(200):
            a, b = QStandardItem(f"name {i}"), QStandardItem("info")
            b.setForeground(QBrush(QColor("#888888")))
            b.setFont(QFont("Consolas", 9))
            model.appendRow([a, b])
        p = QPainter(img)
        for _ in range(100):
            p.setPen(QPen(QColor("#888888"), 1))
            p.setFont(QFont("Consolas", 9))
            p.drawText(QRect(0, 0, 100, 20), 0, "ab")
        p.end()
        n += 1
        app.processEvents()
    stop.set()
    pool.waitForDone()
    print(f"OK {mode} {n}회 {secs:.0f}초")
    return 0


if __name__ == "__main__":
    sys.exit(main())
