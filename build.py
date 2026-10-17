#!/usr/bin/env python
"""PyInstaller 构建脚本。

产出两个单文件 exe：
    dist/通过IDE打开-菜单管理器.exe   图形界面（无控制台窗口）—— 双击即用
    dist/ide-menu-cli.exe            命令行界面

用法:
    python build.py            # 正常构建
    python build.py --clean    # 先清干净再构建
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))

#: (入口脚本, 输出名, 是否无控制台)
TARGETS: list[tuple[str, str, bool]] = [
    ("entry_gui.py", "通过IDE打开-菜单管理器", True),
    ("entry_cli.py", "ide-menu-cli", False),
]

COMMON_ARGS = [
    "--onefile",
    "--clean",
    "--noconfirm",
    "--log-level", "WARN",
    "--hidden-import", "winreg",
    "--hidden-import", "tkinter",
    "--hidden-import", "tkinter.scrolledtext",
    "--exclude-module", "unittest",
    "--exclude-module", "pydoc",
    "--exclude-module", "doctest",
    "--exclude-module", "test",
]


def find_python() -> str:
    """必须是标准 Windows CPython —— MSYS2/MinGW 版 Python 无法正确打包。"""
    exe = sys.executable.lower()
    if "msys" in exe or "mingw" in exe:
        raise SystemExit(
            f"当前 Python 来自 MSYS2/MinGW ({sys.executable})，PyInstaller 不支持。\n"
            "请改用标准 Windows 版 Python，例如：\n"
            r'  C:\Users\dongj\AppData\Local\Programs\Python\Python314\python.exe build.py'
        )
    return sys.executable


def run(cmd: list[str]) -> None:
    print("$", " ".join(cmd))
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit(f"构建失败（退出码 {r.returncode}）")


def main() -> int:
    ap = argparse.ArgumentParser(description="构建 exe")
    ap.add_argument("--clean", action="store_true", help="构建前删除 build/ 与 dist/")
    args = ap.parse_args()

    py = find_python()
    print(f"使用 Python: {py}\n")

    if args.clean:
        for d in ("build", "dist"):
            p = os.path.join(ROOT, d)
            if os.path.isdir(p):
                print(f"删除 {d}/ ...")
                shutil.rmtree(p, ignore_errors=True)
        for f in os.listdir(ROOT):
            if f.endswith(".spec"):
                os.remove(os.path.join(ROOT, f))
                print(f"删除 {f}")

    os.chdir(ROOT)
    for entry, name, windowed in TARGETS:
        cmd = [py, "-m", "PyInstaller", *COMMON_ARGS]
        cmd += ["--windowed" if windowed else "--console"]
        cmd += ["--name", name, os.path.join(ROOT, entry)]
        run(cmd)
        print()

    print("构建完成。产物：")
    for _entry, name, _w in TARGETS:
        exe = os.path.join(ROOT, "dist", name + ".exe")
        size = os.path.getsize(exe) / 1024 / 1024 if os.path.exists(exe) else 0
        print(f"  dist/{name}.exe   ({size:.1f} MB)" if size else f"  dist/{name}.exe   [缺失]")
    return 0


if __name__ == "__main__":
    _t0 = time.time()
    _code = main()
    print(f"\n耗时 {time.time() - _t0:.1f}s")
    raise SystemExit(_code)