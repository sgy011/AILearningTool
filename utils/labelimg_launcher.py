from __future__ import annotations

import os
import subprocess
import sys
import time
import shutil
from pathlib import Path
from typing import Optional, List


def _which_python() -> str:
    return sys.executable or "python"


def launch_labelimg(*, images_dir: str, save_dir: Optional[str] = None) -> tuple[int, list[str]]:
    """
    启动桌面 GUI 标注工具 LabelImg。
    说明：LabelImg 是本机图形界面程序，适用于"服务器与操作者同一台机器"的部署方式。
    """
    img = Path(images_dir).expanduser().resolve()
    if not img.exists() or not img.is_dir():
        raise RuntimeError("images_dir 不存在或不是目录")
    out = Path(save_dir).expanduser().resolve() if save_dir else None
    if out:
        out.mkdir(parents=True, exist_ok=True)

    py = _which_python()

    if sys.platform == "win32":
        # Windows：生成临时 .bat，用 os.startfile 启动（最可靠，完全脱离 Flask 进程）
        import tempfile
        img_s = str(img)
        out_s = str(out) if out else ""
        # 显式传3个参数：image_dir, class_file（空字符串覆盖默认值）, save_dir
        # 防止 labelImg argparser 把 class_file 默认值解析成图片目录导致 PermissionError
        if out_s:
            argv_str = f"['labelImg', r'''{img_s}''', '', r'''{out_s}''']"
        else:
            argv_str = f"['labelImg', r'''{img_s}''', '']"
        code = (
            "import sys\n"
            "from labelImg.labelImg import main\n"
            f"sys.argv = {argv_str}\n"
            "main()\n"
        )
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            tmpfile = f.name
        bat = tmpfile.replace('.py', '.bat')
        with open(bat, 'w', encoding='utf-8') as f:
            f.write(
                f'@echo off\n'
                f'"{py}" "{tmpfile}"\n'
                f'pause\n'
            )
        try:
            os.startfile(bat)
        except Exception as e:
            raise RuntimeError(f"启动失败：{e}") from e
        time.sleep(0.5)
        return 0, [bat]

    # 非 Windows：尝试找 labelImg 可执行文件，否则用 Python 直接启动
    exe = shutil.which("labelImg") or shutil.which("labelImg.exe")
    if exe:
        args: List[str] = [exe, str(img)]
        if out:
            args.append(str(out))
    else:
        img_s = str(img)
        out_s = str(out) if out else ""
        if out_s:
            argv_str = f"['labelImg', r'''{img_s}''', '', r'''{out_s}''']"
        else:
            argv_str = f"['labelImg', r'''{img_s}''', '']"
        code = (
            "import sys\n"
            "from labelImg.labelImg import main\n"
            f"sys.argv = {argv_str}\n"
            "main()\n"
        )
        args = [py, "-c", code]

    env = os.environ.copy()
    kw: dict = {}
    if sys.platform == "win32":
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        si = subprocess.STARTUPINFO()
        si.dwFlags = subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 5
        kw["startupinfo"] = si
    else:
        kw["start_new_session"] = True

    try:
        p = subprocess.Popen(args, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
    except FileNotFoundError as e:
        raise RuntimeError(f"未找到 Python 可执行文件：{py}") from e
    except Exception as e:
        raise RuntimeError(
            "启动 LabelImg 失败。请先安装依赖：\n"
            f'  "{py}" -m pip install labelImg PyQt5 lxml\n'
            "然后重启服务再试。"
        ) from e

    time.sleep(0.6)
    rc = p.poll()
    if rc is not None:
        raise RuntimeError(
            "启动 LabelImg 失败（进程立即退出）。\n"
            f"执行命令：{args}\n"
            f"退出码：{rc}\n"
            "请先安装：\n"
            + f'  "{py}" -m pip install labelImg PyQt5 lxml\n'
            + "若已安装，请确认服务使用的 Python 环境与 labelImg 安装环境一致。"
        )
    return int(p.pid or 0), args
