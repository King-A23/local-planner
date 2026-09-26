"""JSON envelope for the agent CLI. stdout is exactly one JSON value plus newline."""

from __future__ import annotations

import json
import sys
from typing import Any


class UsageError(Exception):
    code = "UsageError"

    def __init__(self, message: str, command: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.command = command


def dump_envelope(payload: dict[str, Any], *, pretty: bool) -> None:
    if pretty:
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write(text + "\n")


def success(
    command: str, today: str, data: dict[str, Any]
) -> dict[str, Any]:
    return {
        "ok": True,
        "v": 1,
        "command": command,
        "today": today,
        "data": data,
    }


def failure(
    command: str | None,
    code: str,
    message: str,
    *,
    today: str | None = None,
    date: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "ok": False,
        "v": 1,
        "command": command,
        "error": {"code": code, "message": message},
    }
    if today is not None:
        body["today"] = today
    if date is not None:
        body["error"]["date"] = date
    return body
