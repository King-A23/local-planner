"""CLI entry: serve, backup, and agent domain commands."""

from __future__ import annotations

import argparse
import sqlite3
import sys

from local_planner.cli.dispatch import dispatch_domain
from local_planner.cli.envelope import UsageError, dump_envelope, failure
from local_planner.runtime import LockTimeout


def _print_root_help() -> None:
    text = """usage: python -m local_planner <command> ...

Process:
  serve [--port N]     Start the loopback web app
  backup [path]        Copy planner.sqlite (WAL-safe)

Agent (JSON on stdout):
  meta
  context
  capabilities          Discover supported interaction commands and rules
  search --query TEXT   Search unfinished titles and notes (up to 50 results)
  calendar --from DATE --to DATE
  day open [DATE]
  day todo add DATE --title TEXT [--start HH:MM] [--end HH:MM]
  day todo complete DATE TASK_ID
  day todo uncomplete DATE TASK_ID
  day todo reorder DATE [TASK_ID ...] [--automatic]
  day todo time DATE TASK_ID [--start HH:MM] [--end HH:MM]
  day errand add DATE --title TEXT [--start HH:MM] [--end HH:MM]
  day errand reorder DATE [ERRAND_ID ...] [--automatic]
  inventory list
  inventory add --title TEXT [--target-date DATE]
  inventory complete TASK_ID
  recurrence list
  recurrence add --kind {plan,errand} --title TEXT --frequency {daily,weekly} [--weekdays mon,tue,...] --start-date DATE [--start HH:MM] [--end HH:MM]
  recurrence update SERIES_ID [fields ...]
  recurrence pause|resume|stop SERIES_ID
  recurrence delete SERIES_ID
  task schedule TASK_ID --date DATE
  task unschedule TASK_ID
  task rename TASK_ID --title TEXT
  task edit TASK_ID [--title TEXT] [--notes TEXT | --clear-notes] --expected-title TEXT --expected-notes TEXT
  task delete TASK_ID
  task target TASK_ID [--date DATE | --clear]
  errand complete ERRAND_ID
  errand uncomplete ERRAND_ID
  errand rename ERRAND_ID --title TEXT
  errand edit ERRAND_ID [--title TEXT] [--notes TEXT | --clear-notes] --expected-title TEXT --expected-notes TEXT
  errand delete ERRAND_ID
  errand time ERRAND_ID [--start HH:MM] [--end HH:MM]

DATE is YYYY-MM-DD, today or tomorrow (Asia/Shanghai server clock).
Reorder requires every item ID, including completed items; --automatic takes no IDs.
Edit preserves omitted fields and rejects stale expected values. Notes: at most 10000 characters.
--pretty / --human apply to agent commands.
"""
    sys.stdout.write(text)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        _print_root_help()
        return 0
    if argv[0] == "serve":
        parser = argparse.ArgumentParser(prog="python -m local_planner serve")
        parser.add_argument("--port", type=int, default=None)
        args = parser.parse_args(argv[1:])
        from local_planner.http.serve import serve

        try:
            serve(port=args.port)
        except LockTimeout as exc:
            print(exc.message, file=sys.stderr)
            return 3
        except SystemExit as exc:
            return int(exc.code or 1)
        return 0
    if argv[0] == "backup":
        if len(argv) > 2:
            print("用法：python -m local_planner backup [路径]", file=sys.stderr)
            return 1
        dest = argv[1] if len(argv) > 1 else None
        from local_planner.backup import backup

        try:
            written = backup(dest)
        except LockTimeout as exc:
            print(exc.message, file=sys.stderr)
            return 3
        except FileNotFoundError as exc:
            print(f"找不到数据库：{exc}", file=sys.stderr)
            return 1
        except FileExistsError as exc:
            print(f"目标已存在：{exc}", file=sys.stderr)
            return 1
        except (OSError, sqlite3.Error, ValueError) as exc:
            print(f"备份失败：{exc}", file=sys.stderr)
            return 1
        print(f"已备份到 {written}")
        return 0
    try:
        return dispatch_domain(argv)
    except UsageError as exc:
        dump_envelope(failure(exc.command, exc.code, exc.message), pretty=False)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
