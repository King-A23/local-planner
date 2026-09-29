"""In-process run supervision, independent of any browser request."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from local_planner.domain.errors import Conflict, NotFound
from local_planner.runtime import LockTimeout, interprocess_lock

ACTIVE = {"starting", "running", "paused", "stopping"}


class RunControl:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.process: subprocess.Popen | None = None
        self.status = "starting"
        self.cancelled = False
        self.started = time.monotonic()
        self.paused_at: float | None = None
        self.paused_seconds = 0.0
        self.finished_at: float | None = None

    def elapsed(self) -> float:
        with self.lock:
            end = self.finished_at or self.paused_at or time.monotonic()
            return max(0.0, end - self.started - self.paused_seconds)

    def attach(self, process: subprocess.Popen) -> None:
        with self.lock:
            self.process = process
            if self.cancelled:
                self._signal(signal.SIGKILL)
            else:
                self.status = "running"

    def detach(self) -> None:
        with self.lock:
            self.process = None
            if self.paused_at is not None:
                self.paused_seconds += time.monotonic() - self.paused_at
                self.paused_at = None
            # Receipt collection is still part of this run; cannot start another.
            if not self.cancelled:
                self.status = "starting"

    def _signal(self, sig: int) -> None:
        if self.process is not None:
            try:
                os.killpg(self.process.pid, sig)
            except ProcessLookupError:
                pass

    def pause(self, root: Path) -> None:
        with self.lock:
            if self.status == "paused":
                return
            if self.status != "running" or self.process is None or self.process.poll() is not None:
                raise Conflict("执行正在准备或收尾，请稍后再试")
            # Never suspend a CLI while it owns the planner database lock.
            try:
                with interprocess_lock(root, timeout=0.5):
                    self._signal(signal.SIGSTOP)
                    self.paused_at = time.monotonic()
                    self.status = "paused"
            except LockTimeout:
                raise Conflict("正在保存计划，请稍后再暂停") from None

    def resume(self) -> None:
        with self.lock:
            if self.status == "running":
                return
            if self.status != "paused":
                raise Conflict("当前执行没有暂停")
            self._signal(signal.SIGCONT)
            self.paused_seconds += time.monotonic() - (self.paused_at or time.monotonic())
            self.paused_at = None
            self.status = "running"

    def stop(self) -> None:
        with self.lock:
            if self.status not in ACTIVE:
                return
            self.cancelled = True
            self.status = "stopping"
            # SIGKILL also terminates stopped groups; no transient resumed writes.
            self._signal(signal.SIGKILL)

    def finish(self, status: str) -> None:
        with self.lock:
            self.finished_at = self.paused_at or time.monotonic()
            self.paused_at = None
            self.status = status
            self.process = None


class AgentRuns:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.lock = threading.RLock()
        self.runs: dict[str, dict[str, Any]] = {}
        self.threads: list[threading.Thread] = []
        self.closed = False

    def start(
        self,
        request_id: str,
        launcher_id: str,
        prompt: str,
        work: Callable[[RunControl], dict],
        *,
        surface: str = "today",
        date: str | None = None,
        goal_id: str | None = None,
        mode: str = "execution",
        draft_id: str | None = None,
        selected_phase_id: str | None = None,
    ) -> dict:
        with self.lock:
            if self.closed:
                raise Conflict("应用正在退出")
            for run in self.runs.values():
                if run["requestId"] == request_id:
                    if (
                        run["launcherId"] != launcher_id
                        or run["prompt"] != prompt
                        or run["surface"] != surface
                        or run["date"] != date
                        or run["goalId"] != goal_id
                        or run["mode"] != mode
                        or run["draftId"] != draft_id
                        or run["selectedPhaseId"] != selected_phase_id
                    ):
                        raise Conflict("请求已提交，请刷新执行状态")
                    return self._payload(run)
                if run["control"].status in ACTIVE:
                    raise Conflict("已有助手正在执行，请先继续或停止当前执行")
            # This separate lock also prevents a second server from starting an agent.
            lease = interprocess_lock(self.root / "agent-execution", timeout=0)
            try:
                lease.__enter__()
            except LockTimeout:
                raise Conflict("另一个应用窗口正在执行助手，请在原窗口操作") from None
            run_id = str(uuid.uuid4())
            control = RunControl()
            run = {"id": run_id, "requestId": request_id, "launcherId": launcher_id,
                   "prompt": prompt, "surface": surface, "date": date,
                   "goalId": goal_id, "mode": mode, "draftId": draft_id,
                   "selectedPhaseId": selected_phase_id, "control": control, "result": None}
            self.runs[run_id] = run
            while len(self.runs) > 20:
                del self.runs[next(iter(self.runs))]

            def execute() -> None:
                try:
                    result = work(control)
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception("agent run failed")
                    result = {"ok": False, "status": "failed", "message": "无法确认执行结果。已有改动可能保留，请检查当前计划。"}
                finally:
                    lease.__exit__(None, None, None)
                with self.lock:
                    run["result"] = result
                    control.finish(result["status"])

            thread = threading.Thread(target=execute, name=f"planner-agent-{run_id}", daemon=True)
            self.threads = [item for item in self.threads if item.is_alive()]
            self.threads.append(thread)
            thread.start()
            return self._payload(run)

    def _payload(self, run: dict) -> dict:
        control = run["control"]
        with control.lock:
            return {key: run[key] for key in ("id", "requestId", "launcherId", "prompt", "surface", "date", "goalId", "mode", "draftId", "selectedPhaseId", "result")} | {
                "status": control.status, "elapsedSeconds": round(control.elapsed(), 1),
            }

    def get(self, run_id: str | None = None) -> dict | None:
        with self.lock:
            if run_id is None:
                run = next(reversed(self.runs.values()), None)
            else:
                run = self.runs.get(run_id)
                if run is None:
                    raise NotFound("找不到这次执行；应用可能已重新启动")
            return self._payload(run) if run else None

    def control(self, run_id: str, action: str) -> dict:
        with self.lock:
            run = self.runs.get(run_id)
            if run is None:
                raise NotFound("找不到这次执行")
            control = run["control"]
            if action == "pause":
                control.pause(self.root)
            elif action == "resume":
                control.resume()
            else:
                control.stop()
            return self._payload(run)

    def close(self) -> None:
        with self.lock:
            self.closed = True
            for run in self.runs.values():
                run["control"].stop()
        for thread in self.threads:
            thread.join(timeout=20)
