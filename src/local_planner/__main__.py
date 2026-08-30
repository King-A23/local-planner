"""CLI entry. `serve` starts the loopback JSON API and SPA; `backup` copies sqlite."""

from __future__ import annotations

import argparse
import sqlite3
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m local_planner",
        description="Local Planner — 本机个人日计划。",
    )
    parser.add_argument("command", nargs="*", help="子命令：serve、backup")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="覆盖 LOCAL_PLANNER_PORT（默认 8787）",
    )
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    name = args.command[0]
    if name == "serve":
        from local_planner.http.serve import serve

        serve(port=args.port)
        return 0
    if name == "backup":
        if len(args.command) > 2:
            print("用法：python -m local_planner backup [路径]", file=sys.stderr)
            return 1
        dest = args.command[1] if len(args.command) > 1 else None
        from local_planner.backup import backup

        try:
            written = backup(dest)
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
    print("未实现", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
