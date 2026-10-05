#!/usr/bin/env python3
"""Build a self-contained native .app for this Mac's CPU architecture."""

from __future__ import annotations

import argparse
import platform
import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "desktop" / "macos"
BUILD = ROOT / "build" / "macos"
DIST = ROOT / "dist" / "macos"
APP = DIST / "Local Planner.app"


def run(*args: str | Path, cwd: Path = ROOT) -> None:
    subprocess.run([str(arg) for arg in args], cwd=cwd, check=True)


def minimum_macos(bundle: Path) -> str:
    """The bundled Python/dylibs may require newer macOS than our Swift shell."""
    versions = [(13, 0)]
    magic = {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"}
    for path in bundle.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        with path.open("rb") as source:
            if source.read(4) not in magic:
                continue
        result = subprocess.run(["xcrun", "vtool", "-show-build", str(path)], check=True, capture_output=True, text=True)
        found = re.findall(r"\bminos\s+(\d+(?:\.\d+)+)", result.stdout)
        found += re.findall(r"LC_VERSION_MIN_MACOSX\s+cmdsize\s+\d+\s+version\s+(\d+(?:\.\d+)+)", result.stdout)
        versions.extend(tuple(int(part) for part in version.split(".")) for version in found)
    return ".".join(str(part) for part in max(versions))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="Install into ~/Applications (refuses to overwrite)")
    args = parser.parse_args()
    if sys.platform != "darwin" or sys.version_info < (3, 12):
        parser.error("需要 macOS 和 Python 3.12+")
    target = Path.home() / "Applications" / APP.name
    if args.install and target.exists():
        parser.error(f"已有应用，未覆盖：{target}。请先退出并移走旧版本。")
    BUILD.mkdir(parents=True, exist_ok=True)
    DIST.mkdir(parents=True, exist_ok=True)
    run("npm", "ci", cwd=ROOT / "web")
    run("npm", "run", "build", cwd=ROOT / "web")
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
        "--name", "local-planner-backend", "--distpath", BUILD / "backend-dist",
        "--workpath", BUILD / "pyinstaller", "--specpath", BUILD,
        "--paths", ROOT / "src", "--collect-data", "local_planner",
        "--add-data", f"{ROOT / 'web/dist'}:local_planner/web/dist",
        "--hidden-import", "uvicorn.logging", "--hidden-import", "uvicorn.loops.asyncio",
        "--hidden-import", "uvicorn.protocols.http.h11_impl",
        "--hidden-import", "uvicorn.lifespan.on", SOURCE / "backend_entry.py")
    if APP.exists():
        shutil.rmtree(APP)
    resources = APP / "Contents" / "Resources"
    macos = APP / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    resources.mkdir(parents=True)
    shutil.copy2(SOURCE / "Info.plist", APP / "Contents" / "Info.plist")
    shutil.copytree(BUILD / "backend-dist/local-planner-backend", resources / "backend", symlinks=True)
    run("xcrun", "swiftc", "-swift-version", "5", "-O", "-target",
        f"{platform.machine()}-apple-macosx13.0", "-framework", "AppKit", "-framework", "WebKit",
        SOURCE / "LocalPlanner.swift", SOURCE / "NavigationFailure.swift", SOURCE / "AgentCompletionMonitor.swift",
        "-o", macos / "LocalPlanner")
    run("xcrun", "swiftc", SOURCE / "MakeIcon.swift", "-o", BUILD / "make-icon")
    run(BUILD / "make-icon", BUILD / "AppIcon.iconset")
    run("iconutil", "-c", "icns", BUILD / "AppIcon.iconset", "-o", resources / "AppIcon.icns")
    plist_path = APP / "Contents" / "Info.plist"
    info = plistlib.loads(plist_path.read_bytes())
    info["LSMinimumSystemVersion"] = minimum_macos(APP)
    plist_path.write_bytes(plistlib.dumps(info))
    run("codesign", "--force", "--deep", "--sign", "-", APP)
    run("codesign", "--verify", "--deep", "--strict", APP)
    archive = DIST / f"Local-Planner-macOS-{platform.machine()}.zip"
    if archive.exists():
        archive.unlink()
    run("ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", APP, archive)
    if args.install:
        target.parent.mkdir(parents=True, exist_ok=True)
        run("ditto", APP, target)
        print(f"已安装：{target}")
    print(f"应用：{APP}\n压缩包：{archive}\n最低 macOS：{info['LSMinimumSystemVersion']}")


if __name__ == "__main__":
    main()
