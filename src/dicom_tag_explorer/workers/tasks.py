# QRunnable 작업 래퍼, 결과 Signals, CancelToken, 세대 번호를 제공한다.
from __future__ import annotations

import threading
import traceback
import weakref
from typing import Any, Callable

import shiboken6
from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot

from ..core.indexer import Cancelled


class CancelToken:
    """스레드 간 공유하는 취소 플래그. core 함수는 is_cancelled()만 쓴다."""

    def __init__(self):
        self._ev = threading.Event()

    def cancel(self) -> None:
        self._ev.set()

    def is_cancelled(self) -> bool:
        return self._ev.is_set()


class Generation:
    """세대 번호. 새 요청마다 올리고, 결과의 번호가 현재와 다르면 버린다."""

    def __init__(self):
        self.value = 0

    def next(self) -> int:
        self.value += 1
        return self.value

    def is_current(self, g: int) -> bool:
        return g == self.value


class TaskSignals(QObject):
    done = Signal(object, object)  # (result, tag)
    failed = Signal(str, object)  # (message, tag)


class Task(QRunnable):
    """fn(*args)를 실행하고 결과를 queued connection으로 UI 스레드에 전달한다.
    PySide6의 QThreadPool.start()는 넘긴 runnable을 풀 래퍼의 자식으로 기록하고, 그 기록은 C++ runnable이 삭제될 때만
    풀린다. 그래서 autoDelete로 풀이 실행 뒤 C++ 객체를 지우게 한다(지우지 않으면 끝난 작업과 인자가 풀에 계속 남는다).
    Python 쪽 마지막 참조(_alive)는 C++ 삭제가 끝난 뒤 UI 스레드에서 놓는다(_release)."""

    _alive: set["Task"] = set()
    _alive_lock = threading.Lock()

    def __init__(self, fn: Callable[..., Any], *args, tag: Any = None):
        super().__init__()
        self.setAutoDelete(True)
        self.fn = fn
        self.args = args
        self.tag = tag
        self.signals = TaskSignals()
        self.pool: QThreadPool | None = None
        self.started = False

    @Slot()
    def run(self) -> None:
        self.started = True
        try:
            try:
                res = self.fn(*self.args)
            except Cancelled:
                self.signals.failed.emit("Cancelled", self.tag)  # 정상 취소: traceback을 남기지 않는다
            except Exception as e:  # 워커 예외는 UI에 메시지로 전달
                traceback.print_exc()
                self.signals.failed.emit(f"{type(e).__name__}: {e}", self.tag)
            else:
                self.signals.done.emit(res, self.tag)
        except RuntimeError:
            pass  # 앱 종료 중 신호 객체가 이미 삭제됨


def submit(pool: QThreadPool, fn: Callable[..., Any], *args, on_done=None, on_failed=None,
           tag: Any = None, priority: int = 0) -> Task:
    t = Task(fn, *args, tag=tag)
    if on_done is not None:
        t.signals.done.connect(on_done)
    if on_failed is not None:
        t.signals.failed.connect(on_failed)
    # 사용자 콜백 뒤에 UI 스레드에서 참조를 놓는다 (신호 객체가 전달 전에 해제되지 않게).
    # t를 weakref로만 잡는다. 이 연결은 t.signals(C++)가 쥐므로 t를 직접 잡으면 GC가 끊지 못하는 순환이 된다
    ref = weakref.ref(t)
    t.signals.done.connect(lambda *_: _release_ref(ref))
    t.signals.failed.connect(lambda *_: _release_ref(ref))
    t.pool = pool
    with Task._alive_lock:
        Task._alive.add(t)
    pool.start(t, priority)
    return t


def _release_ref(ref: weakref.ref) -> None:
    t = ref()
    if t is not None:
        _release(t)


def _release(t: Task) -> None:
    """UI 스레드에서 호출한다. 워커가 아직 run()을 마치지 않아 풀이 C++ 객체를 지우기 전이면 잠시 뒤 다시 본다.
    이렇게 해야 Task(와 TaskSignals QObject)의 마지막 참조가 워커 스레드가 아니라 UI 스레드에서 풀린다."""
    if shiboken6.isValid(t):
        QTimer.singleShot(10, lambda: _release(t))
        return
    with Task._alive_lock:
        Task._alive.discard(t)


def take(pool: QThreadPool, t: Task) -> bool:
    """시작 전 작업을 큐에서 꺼내 버린다. tryTake로 꺼낸 runnable은 풀이 지우지 않으므로 여기서 지운다."""
    # 시작한 작업은 끝나면 풀이 C++ 객체를 지우므로 꺼낼 수 없다. 확인 직후 끝나 지워진 경우도 False다
    if t.started:
        return False
    try:
        if not pool.tryTake(t):
            return False
    except RuntimeError:
        return False
    shiboken6.delete(t)
    with Task._alive_lock:
        Task._alive.discard(t)
    return True


def clear_pool(pool: QThreadPool) -> None:
    """시작 전 작업을 버린다(autoDelete라 풀이 C++ 객체를 지운다). 실행 중 작업은 끝까지 돌고 결과는 세대 번호로 걸러진다."""
    pool.clear()
    with Task._alive_lock:
        for t in [t for t in Task._alive if t.pool is pool and not t.started]:
            Task._alive.discard(t)


def global_pool() -> QThreadPool:
    pool = QThreadPool.globalInstance()
    pool.setMaxThreadCount(4)
    return pool
