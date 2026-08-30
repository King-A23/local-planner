"""CLI entry. `serve` starts the loopback JSON API and SPA."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m local_planner",
        description="Local Planner — 本机个人日计划。",
    )
    parser.add_argument("command", nargs="*", help="子命令：serve")
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
    if args.command[0] == "serve":
        from local_planner.http.serve import serve

        serve(port=args.port)
        return 0
    print("未实现", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
