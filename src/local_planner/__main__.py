"""CLI entry. Product commands are not implemented in this scaffold."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m local_planner",
        description="Local Planner — 本机个人日计划。",
        epilog="serve 尚未实现。",
    )
    parser.add_argument(
        "command",
        nargs="*",
        help="子命令（尚未实现）",
    )
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    print("未实现", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
