"""Stub launcher used by tests. Records argv, prompt, and context."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

proof = os.environ["LAUNCHER_PROOF"]
context_file = os.environ["LOCAL_PLANNER_CONTEXT_FILE"]
Path(proof).write_text(
    json.dumps(
        {
            "argv": sys.argv[1:],
            "prompt": os.environ.get("LOCAL_PLANNER_PROMPT"),
            "context": Path(context_file).read_text(encoding="utf-8"),
        }
    ),
    encoding="utf-8",
)
print("stub-ok")
