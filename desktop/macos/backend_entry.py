"""PyInstaller entry point; also exposes the existing agent CLI."""
from local_planner.desktop import main

if __name__ == "__main__":
    raise SystemExit(main())
