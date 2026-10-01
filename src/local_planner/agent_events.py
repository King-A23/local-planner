"""Bounded public progress, independent of model reasoning and database writes."""
from __future__ import annotations

import json
import shlex
import re
import threading
from collections import deque
from typing import Any


def clipped(text: str, limit: int) -> str:
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text
    return data[:max(0, limit - 32)].decode("utf-8", errors="ignore") + "\n…内容已省略"


def public_message(text: str) -> str:
    return re.sub(r"(?:[`*_]\s*)?(?:PROCESS_CLEANUP_COMPLETE|INTENTIONAL_BACKGROUND_PROCESS_RETAINED|PROCESS_CLEANUP_BLOCKED)(?:\s*[`*_])?", "", text).strip()


class EventBuffer:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.items: deque[tuple[dict, int]] = deque()
        self.sequence = 0
        self.size = 0
        self.source = "none"

    def set_source(self, source: str) -> None:
        with self.lock:
            self.source = source

    def emit(self, item_id: str, kind: str, status: str, summary: str, details: str = "") -> None:
        with self.lock:
            self.sequence += 1
            event = {"sequence": self.sequence, "itemId": item_id, "kind": kind,
                     "status": status, "summary": clipped(summary, 2048)}
            if details:
                event["details"] = clipped(details, 8192)
            size = len(json.dumps(event, ensure_ascii=False).encode("utf-8"))
            self.items.append((event, size))
            self.size += size
            while len(self.items) > 500 or self.size > 256 * 1024:
                self.size -= self.items.popleft()[1]

    def payload(self, after: int) -> dict:
        with self.lock:
            first = self.items[0][0]["sequence"] if self.items else self.sequence + 1
            return {"items": [dict(item) for item, _ in self.items if item["sequence"] > after],
                    "nextSequence": self.sequence, "truncated": after < first - 1,
                    "source": self.source}


def structured_command(argv: list[str]) -> tuple[list[str], str]:
    """Only adapt direct invocations. Shells, env and custom wrappers stay intact."""
    from pathlib import Path
    if len(argv) < 2:
        return argv, "none"
    name = Path(argv[0]).name
    next_argv = list(argv)
    if name == "codex" and argv[1] == "exec":
        if "--json" not in argv[2:]:
            next_argv.insert(2, "--json")
        return next_argv, "codex"
    if name == "opencode" and argv[1] == "run":
        # Respect explicitly formatted custom commands rather than overriding them.
        if "--format" in argv:
            pos = argv.index("--format")
            return next_argv, "opencode" if argv[pos + 1:pos + 2] == ["json"] else "none"
        formats = [part for part in argv if part.startswith("--format=")]
        if formats:
            return next_argv, "opencode" if formats == ["--format=json"] else "none"
        next_argv[2:2] = ["--format", "json"]
        return next_argv, "opencode"
    return argv, "none"


def operation_summary(tool: str, command: str) -> str:
    from pathlib import Path
    try:
        words = shlex.split(command)
        if len(words) == 3 and Path(words[0]).name in {"sh", "bash", "zsh"} and words[1] in {"-c", "-lc"}:
            words = shlex.split(words[2])
    except ValueError:
        words = []
    # Recognize the actual planner CLI prefix, never an arbitrary substring.
    start = next((i + 1 for i, word in enumerate(words) if word.endswith("local-planner-backend")), None)
    if start is None:
        start = next((i + 2 for i in range(len(words) - 1)
                      if words[i:i + 2] == ["-m", "local_planner"]), None)
    args = words[start:] if start is not None else []
    if args[:1] in (["context"], ["search"]):
        return "读取计划上下文" if args[0] == "context" else "搜索事项"
    if args[:2] == ["day", "open"]:
        return "读取当天计划"
    if args[:2] == ["inventory", "list"]:
        return "读取待办"
    if args[:2] in (["goal", "show"], ["goal", "list"]):
        return "读取规划"
    if args:
        if "add" in args[:4]: return "添加事项"
        if args[:2] == ["task", "schedule"]: return "调整事项日期"
        if "edit" in args[:3]: return "更新事项详情"
        if "complete" in args[:4]: return "完成事项"
        if "reorder" in args[:4] or "move" in args[:4]: return "调整事项顺序"
    return {"command_execution": "执行命令", "bash": "执行命令", "read": "读取文件",
            "write": "写入文件", "edit": "修改文件", "file_change": "修改文件",
            "web_search": "搜索资料", "mcp_tool_call": "调用工具"}.get(tool, f"调用工具：{tool}")


class PublicEvents:
    """Normalize documented JSONL items; never forward reasoning or raw payloads."""
    def __init__(self, source: str, buffer: EventBuffer | None) -> None:
        self.source = source
        self.buffer = buffer
        self.reply = ""
        self.failed = False
        self.error = ""
        self.pending = ""
        self.discarding_line = False
        self.recognized = False
        self.messages: dict[str, str] = {}
        if buffer:
            buffer.set_source(source)

    def emit(self, item_id: str, kind: str, status: str, summary: str, details: str = "") -> None:
        self.recognized = True
        if self.buffer:
            self.buffer.emit(item_id, kind, status, summary, details)

    def feed(self, text: str, *, final: bool = False) -> None:
        if self.source == "none":
            return
        for part in text.splitlines(keepends=True):
            if not self.discarding_line:
                self.pending += part
                if len(self.pending) > 1024 * 1024:
                    self.pending = ""
                    self.discarding_line = True
            if part.endswith("\n"):
                if not self.discarding_line:
                    self.line(self.pending)
                self.pending = ""
                self.discarding_line = False
        if final and self.pending and not self.discarding_line:
            self.line(self.pending)
            self.pending = ""
        if final and self.buffer and not self.recognized:
            self.buffer.set_source("none")

    def line(self, line: str) -> None:
        try:
            event = json.loads(line)
            if not isinstance(event, dict): return
            if self.source == "codex": self.codex(event)
            else: self.opencode(event)
        except (ValueError, TypeError, KeyError, AttributeError):
            # Version-specific/partial/unknown events are observational only.
            return

    def codex(self, event: dict[str, Any]) -> None:
        event_type = event.get("type", "")
        if event_type in {"turn.started", "turn.completed", "turn.failed", "error"}:
            label = {"turn.started": "助手开始处理", "turn.completed": "助手处理结束",
                     "turn.failed": "助手处理失败", "error": "助手发生错误"}[event_type]
            self.emit(event_type, "status", "failed" if event_type in {"turn.failed", "error"} else "completed", label)
            if event_type in {"turn.failed", "error"}:
                self.failed = True
                error = event.get("error") or {}
                message = error.get("message", "") if isinstance(error, dict) else ""
                self.error = clipped(message if isinstance(message, str) and message else label, 2048)
            return
        if event_type not in {"item.started", "item.updated", "item.completed"}: return
        item = event.get("item") or {}
        kind = item.get("type")
        item_id = str(item.get("id", ""))
        if kind == "agent_message":
            text = item.get("text", "")
            if not isinstance(text, str) or not text: return
            text = public_message(text)
            if not text: return
            self.emit(item_id, "message", "completed", text)
            if item.get("phase") != "commentary" and event_type == "item.completed":
                self.reply = text
            return
        if kind not in {"command_execution", "file_change", "mcp_tool_call", "web_search", "todo_list"}: return
        command = item.get("command", "")
        output = item.get("aggregated_output", "")
        if not isinstance(command, str) or not isinstance(output, str): return
        status = "running" if event_type != "item.completed" else "completed"
        if item.get("status") == "failed" or item.get("exit_code") not in {None, 0}: status = "failed"
        summary = "更新操作步骤" if kind == "todo_list" else operation_summary(kind, command)
        if kind == "mcp_tool_call": summary = f"调用工具：{item.get('tool', '工具')}"
        details = "\n".join(part for part in [command, output] if part)
        if kind == "file_change":
            changes = item.get("changes", [])
            if isinstance(changes, list):
                details = "\n".join(str(change.get("path", "")) for change in changes if isinstance(change, dict))
        if kind == "mcp_tool_call":
            details = json.dumps({"arguments": item.get("arguments"), "result": item.get("result"),
                                  "error": item.get("error")}, ensure_ascii=False)
        self.emit(item_id, "operation", status, summary, details)

    def opencode(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        part = event.get("part") or {}
        item_id = str(part.get("id") or part.get("callID") or event.get("timestamp") or kind)
        if kind == "text":
            text = part.get("text", "")
            if not isinstance(text, str) or not text: return
            text = public_message(text)
            if not text: return
            self.messages[item_id] = text
            self.reply = "\n".join(self.messages.values())
            self.emit(item_id, "message", "completed", text)
        elif kind == "tool_use":
            state = part.get("state") or {}
            tool = part.get("tool", "工具")
            inputs = state.get("input") or {}
            command = inputs.get("command", "") if isinstance(inputs, dict) else ""
            output = state.get("output", "")
            if not isinstance(command, str) or not isinstance(output, str): return
            status = {"running": "running", "pending": "running", "error": "failed"}.get(state.get("status"), "completed")
            self.emit(item_id, "operation", status, operation_summary(tool, command), "\n".join(p for p in [command, output] if p))
            # A tool boundary separates an explanation from the eventual reply.
            self.messages.clear()
            self.reply = ""
        elif kind in {"step_start", "step_finish", "error"}:
            self.emit(item_id, "status", "failed" if kind == "error" else "completed",
                      {"step_start": "助手开始处理", "step_finish": "助手处理结束", "error": "助手发生错误"}[kind])
            if kind == "error":
                self.failed = True
                self.error = "助手发生错误"
