"""
一键启动前后端（支持本地开发 / 云服务器）。

用法示例：
  # 本地开发（前后端都起）
  python start_dev.py

  # 云服务器（默认只起后端，监听 0.0.0.0，关闭 debug）
  python start_dev.py --cloud

  # 云服务器 + 前端开发服务（不常用）
  python start_dev.py --cloud --with-frontend-dev
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional


ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "frontend"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动前后端服务（开发/云服务器）")
    parser.add_argument("--cloud", action="store_true", help="云服务器模式（默认仅后端，且关闭 Flask debug）")
    parser.add_argument("--with-frontend-dev", action="store_true", help="在 --cloud 模式下额外启动前端 dev 服务")
    parser.add_argument("--backend-only", action="store_true", help="只启动后端")
    parser.add_argument("--frontend-only", action="store_true", help="只启动前端")
    parser.add_argument("--backend-host", default=None, help="后端 host（覆盖 .env 的 FLASK_HOST）")
    parser.add_argument("--backend-port", type=int, default=None, help="后端 port（覆盖 .env 的 FLASK_PORT）")
    parser.add_argument("--frontend-host", default="127.0.0.1", help="前端 host（vite --host）")
    parser.add_argument("--frontend-port", type=int, default=5173, help="前端 port（vite --port）")
    return parser.parse_args()


def build_backend_env(args: argparse.Namespace) -> Dict[str, str]:
    env = os.environ.copy()
    if args.cloud:
        # 云服务器模式：默认对外监听，并关闭 debug（可被显式参数覆盖）
        env.setdefault("FLASK_HOST", "0.0.0.0")
        env.setdefault("FLASK_DEBUG", "0")

    if args.backend_host:
        env["FLASK_HOST"] = args.backend_host
    if args.backend_port is not None:
        env["FLASK_PORT"] = str(args.backend_port)
    return env


def ensure_frontend_ready() -> None:
    if not FRONTEND_DIR.exists():
        raise RuntimeError(f"未找到前端目录: {FRONTEND_DIR}")
    if resolve_npm_executable() is None:
        raise RuntimeError("未找到 npm，请先安装 Node.js 后重试。")


def resolve_npm_executable() -> Optional[str]:
    """
    在不同平台解析可执行 npm 命令。
    Windows 下优先 npm.cmd，避免直接调用 npm 触发 WinError 2。
    """
    if os.name == "nt":
        return shutil.which("npm.cmd") or shutil.which("npm")
    return shutil.which("npm")


def create_process(
    cmd: List[str],
    cwd: Path,
    env: Optional[Dict[str, str]] = None,
) -> subprocess.Popen:
    kwargs = {
        "cwd": str(cwd),
        "env": env if env is not None else os.environ.copy(),
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    return subprocess.Popen(cmd, **kwargs)


def terminate_process(proc: subprocess.Popen, name: str) -> None:
    if proc.poll() is not None:
        return
    print(f"[stop] 正在停止{name} ...")
    try:
        if os.name == "nt":
            proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
        else:
            proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
        proc.wait(timeout=3)


def main() -> int:
    args = parse_args()
    if args.backend_only and args.frontend_only:
        print("参数冲突：--backend-only 与 --frontend-only 不能同时使用。")
        return 2

    if args.cloud:
        start_backend = True
        start_frontend = args.with_frontend_dev and not args.backend_only
        if args.frontend_only:
            print("参数冲突：--cloud 模式下不支持仅前端。请移除 --frontend-only。")
            return 2
    else:
        start_backend = not args.frontend_only
        start_frontend = not args.backend_only

    procs: List[tuple[str, subprocess.Popen]] = []
    try:
        if start_backend:
            backend_env = build_backend_env(args)
            backend_cmd = [sys.executable, str(ROOT / "app.py")]
            proc = create_process(backend_cmd, ROOT, backend_env)
            procs.append(("后端", proc))
            host = backend_env.get("FLASK_HOST", os.getenv("FLASK_HOST", "127.0.0.1"))
            port = backend_env.get("FLASK_PORT", os.getenv("FLASK_PORT", "5000"))
            print(f"[start] 后端已启动: http://{host}:{port}")

        if start_frontend:
            ensure_frontend_ready()
            npm_exe = resolve_npm_executable()
            if not npm_exe:
                raise RuntimeError("未找到 npm，请先安装 Node.js 后重试。")
            frontend_cmd = [
                npm_exe,
                "run",
                "dev",
                "--",
                "--host",
                str(args.frontend_host),
                "--port",
                str(args.frontend_port),
            ]
            proc = create_process(frontend_cmd, FRONTEND_DIR)
            procs.append(("前端", proc))
            print(f"[start] 前端已启动: http://{args.frontend_host}:{args.frontend_port}")

        if not procs:
            print("没有可启动的服务。")
            return 1

        if args.cloud:
            print("[info] 当前为云服务器模式。按 Ctrl+C 可停止所有已启动服务。")
        else:
            print("[info] 按 Ctrl+C 可同时停止所有已启动服务。")
        while True:
            for name, proc in procs:
                code = proc.poll()
                if code is not None:
                    print(f"[exit] {name}已退出，退出码: {code}")
                    return code
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n[info] 收到中断信号，开始退出...")
        return 0
    except Exception as exc:
        print(f"[error] 启动失败: {exc}")
        return 1
    finally:
        for name, proc in reversed(procs):
            terminate_process(proc, name)


if __name__ == "__main__":
    raise SystemExit(main())
