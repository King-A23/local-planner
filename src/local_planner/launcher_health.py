"""Local-only checks. Never run a prompt, a custom command, or read credentials."""

import os
import shlex
import shutil
import subprocess
from pathlib import Path

from local_planner.launchers import Launcher
from local_planner.processes import agent_process


def check_launcher(launcher: Launcher) -> dict:
    def result(status: str, message: str) -> dict:
        return {"status": status, "message": message}

    try:
        argv = shlex.split(launcher.command)
    except ValueError:
        return result("invalid", "命令格式有误，请在高级配置中修改")
    if not argv:
        return result("invalid", "请先填写助手命令")
    executable = shutil.which(argv[0])
    if executable is None:
        return result("missing", "未找到此工具。安装后重新检测，或在高级配置中填写完整路径。")
    if Path(argv[0]).name != "codex":
        return result("installed", "已找到工具；请确认已在该工具中登录并设置模型。")
    # Only the documented status subcommand is allowed; never execute template args.
    try:
        with agent_process([executable, "login", "status"], stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=os.environ.copy()) as process:
            stdout, stderr = process.communicate(timeout=5)
            code = process.returncode
    except subprocess.TimeoutExpired:
        return result("unknown", "工具响应较慢，暂时无法确认登录状态，请重试")
    except OSError:
        return result("unknown", "工具无法启动，请检查安装后重试")
    if code == 0:
        return result("ready", "已安装，默认账户已登录。未检测远端模型或额度。")
    if "not logged in" in (stdout + stderr).lower():
        return result("login_required", "尚未登录。请先在终端执行 codex login，再重新检测。")
    return result("unknown", "已安装，但无法确认登录状态。请在终端检查 codex login status。")
