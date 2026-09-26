"""Own agent process groups so desktop shutdown cannot leave workers behind."""

from __future__ import annotations

import signal
import os
import subprocess
import threading
from contextlib import contextmanager
from collections.abc import Iterator

_lock = threading.Lock()
_active: set[subprocess.Popen] = set()
_stopping = False


def stop_agents() -> None:
    global _stopping
    with _lock:
        _stopping = True
        for process in _active:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


@contextmanager
def agent_process(argv: list[str], **kwargs) -> Iterator[subprocess.Popen]:
    with _lock:
        if _stopping:
            raise OSError("应用正在退出，无法启动计划助手")
        process = subprocess.Popen(argv, start_new_session=True, **kwargs)
        _active.add(process)
    try:
        yield process
    finally:
        with _lock:
            try:
                # A launcher may exit before its children; own the whole group.
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            _active.discard(process)
        process.wait()
