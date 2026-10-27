# 작업(Task)과 그 인자(DicomFile 등)가 끝난 뒤 해제되는지 확인하는 누수 회귀 테스트.
from __future__ import annotations

import gc
import tempfile
import threading
import time
import weakref

from PySide6.QtCore import QCoreApplication, QSettings, QThreadPool

from dicom_factory import encapsulated_file, mono_file, nested_file
from dicom_tag_explorer.workers.tasks import Task, clear_pool, submit, take


def pump(app, cond, timeout=10.0) -> bool:
    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    return cond()


def settle(app) -> None:
    """지연 해제(C++ 삭제 확인 뒤 참조 놓기)가 끝나도록 이벤트를 돌리고 GC를 부른다."""
    pump(app, lambda: not Task._alive, 5)
    gc.collect()


def test_open_close_all_releases_files_and_tasks(qapp, tmp_path):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp())
    QCoreApplication.setOrganizationName("Vieworks")
    QCoreApplication.setApplicationName("DicomTagExplorerTestLeak")
    from dicom_tag_explorer.ui.main_window import MainWindow
    paths = [mono_file(tmp_path / f"m{i}.dcm") for i in range(4)]
    paths += [encapsulated_file(tmp_path / "e.dcm"), nested_file(tmp_path / "n.dcm")]
    w = MainWindow()
    w.show()
    files, tasks = [], []
    orig_init = Task.__init__

    def spy(self, *a, **k):
        orig_init(self, *a, **k)
        tasks.append(weakref.ref(self))

    Task.__init__ = spy
    try:
        for _ in range(3):
            w.open_paths(paths, add_recent=False)
            assert pump(qapp, lambda: w.batch is not None and w.batch.finished)
            assert len(w.files) == len(paths)
            files += [weakref.ref(f) for f in w.files.values()]
            w.close_all()
            settle(qapp)
        assert tasks
        assert sum(r() is not None for r in files) == 0
        assert sum(r() is not None for r in tasks) == 0
    finally:
        Task.__init__ = orig_init
        w.close()


class _Arg:
    """작업 인자 대용. weakref로 해제를 확인한다."""


def test_finished_taken_and_cleared_tasks_are_released(qapp):
    pool = QThreadPool()
    pool.setMaxThreadCount(1)
    gate = threading.Event()
    refs = []

    def job(arg, wait=False):
        if wait:
            gate.wait(5)
        return None

    try:
        blocker = submit(pool, job, _Arg(), True)  # 이 작업이 끝날 때까지 나머지는 큐에 남는다
        queued = [submit(pool, job, _Arg()) for _ in range(3)]
        refs += [weakref.ref(t) for t in (blocker, *queued)] + [weakref.ref(t.args[0]) for t in (blocker, *queued)]
        assert take(pool, queued[0])  # 시작 전 작업을 꺼낸다 (열기 취소)
        clear_pool(pool)  # 나머지 시작 전 작업을 버린다 (타일 풀)
        gate.set()
        pool.waitForDone(5000)
        del blocker, queued
        settle(qapp)
        assert sum(r() is not None for r in refs) == 0
        done = [weakref.ref(submit(pool, job, _Arg())) for _ in range(5)]  # 정상 완료
        pool.waitForDone(5000)
        settle(qapp)
        assert sum(r() is not None for r in done) == 0
    finally:
        gate.set()
        pool.waitForDone(5000)


def test_take_on_finished_task_returns_false(qapp):
    # QA-06: 이미 끝나 풀이 C++ 객체를 지운 작업에 take()를 불러도 예외 없이 False를 돌려준다 (열기 취소)
    pool = QThreadPool()
    try:
        t = submit(pool, lambda: None)
        pool.waitForDone(5000)
        assert take(pool, t) is False
    finally:
        pool.waitForDone(5000)
