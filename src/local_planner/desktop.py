"""Bundled desktop sidecar and CLI, using the existing HTTP/domain lifecycle."""

from __future__ import annotations

import argparse
import errno
import json
import os
import signal
import socket
import sys
import threading

import uvicorn

from local_planner.http.serve import serve
from local_planner.processes import stop_agents

DESKTOP_PORT = 18787


def bind_listener(port: int) -> socket.socket:
    """Reserve the real IPv4 listener; never connect to an unrelated service."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind(("127.0.0.1", port))
        except OSError as exc:
            if exc.errno != errno.EADDRINUSE or port == 0:
                raise
            listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        return listener
    except BaseException:
        listener.close()
        raise


def watch_parent() -> None:
    """The native parent keeps stdin open; EOF also covers a crashed/killed app."""
    while sys.stdin.buffer.read(1):
        pass
    stop_agents()
    os.kill(os.getpid(), signal.SIGTERM)
    # Bound shutdown even when a request or a library cannot finish.
    threading.Event().wait(8)
    os._exit(0)


class DesktopServer(uvicorn.Server):
    async def startup(self, sockets=None) -> None:
        await super().startup(sockets)
        if self.started:
            print(json.dumps({"event": "ready", "url": f"http://127.0.0.1:{self.config.port}/"}), flush=True)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] != "desktop-serve":
        # Frozen sys.executable is this executable, not a Python interpreter.
        from local_planner.__main__ import main as cli_main
        return cli_main(argv)

    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("--port", type=int, default=DESKTOP_PORT)
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("端口必须在 0 到 65535 之间")
    # A desktop build always serves its bundled UI, never the Vite dev server.
    os.environ.pop("LOCAL_PLANNER_DEV", None)
    threading.Thread(target=watch_parent, name="desktop-parent", daemon=True).start()
    try:
        with bind_listener(args.port) as listener:
            port = listener.getsockname()[1]

            def run(app, **kwargs):
                config = uvicorn.Config(
                    app, **kwargs, loop="asyncio", http="h11", ws="none",
                    lifespan="on", timeout_graceful_shutdown=3,
                )
                DesktopServer(config).run(sockets=[listener])

            serve(port, runner=run)
        return 0
    finally:
        stop_agents()


if __name__ == "__main__":
    raise SystemExit(main())
