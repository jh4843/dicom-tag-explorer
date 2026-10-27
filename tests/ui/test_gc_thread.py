# QA-05 회귀 테스트: 순환 GC가 UI 스레드에서만 돌고, 워커 GC와 PySide6 호출이 겹치는 스트레스에서 죽지 않는다.
from __future__ import annotations

import gc
import os
import subprocess
import sys
import threading
import time
import weakref
from pathlib import Path

from dicom_tag_explorer.app import gc_on_ui_thread

ROOT = Path(__file__).resolve().parents[2]


def test_qa05_cycles_from_worker_collected_on_ui_thread(qapp):
    """자동 GC를 끄고, 워커가 만든 순환 쓰레기는 UI 스레드의 타이머가 거둔다. 자동 GC처럼 할당이 이어지면 수거된다."""
    main_id = threading.get_ident()
    timer = gc_on_ui_thread(qapp)
    collected_in: list[int] = []

    class Node:
        pass

    def worker():
        for _ in range(3000):
            n = Node()
            n.self = n
            weakref.finalize(n, lambda: collected_in.append(threading.get_ident()))

    try:
        assert not gc.isenabled()
        t = threading.Thread(target=worker)
        t.start()
        t.join()
        assert collected_in == []  # 워커 스레드에서는 수집하지 않는다
        hold = []
        end = time.perf_counter() + 20
        while len(collected_in) < 3000 and time.perf_counter() < end:
            hold.extend([i] for i in range(5000))  # 앱이 계속 할당하는 상황
            qapp.processEvents()
        assert len(collected_in) == 3000 and set(collected_in) == {main_id}
    finally:
        timer.stop()
        timer.deleteLater()
        gc.enable()
        gc.collect()


def test_qa05_stress_survives_with_ui_thread_gc():
    """scripts/stress_gc_thread.py app 모드. 같은 스크립트의 auto 모드(기본 GC)는 이 환경에서 수 초 안에 죽는다."""
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "stress_gc_thread.py"), "app", "8"],
                       capture_output=True, text=True, encoding="utf-8", env=env, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    assert r.stdout.startswith("OK app")
