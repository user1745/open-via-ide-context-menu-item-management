#!/usr/bin/env python
"""PyInstaller 构建脚本。

产出一个单文件 exe：
    dist/通过IDE打开·右键菜单项管理（阿懂）.exe   图形界面（无控制台窗口）—— 双击即用

> 早期版本还打包过 ``ide-menu-cli.exe``，现已按需求移除，源码里的 ``ide_menu.cli``
> 仍保留，可通过 ``python -m ide_menu`` 使用。

用法:
    python build.py            # 正常构建
    python build.py --clean    # 先清干净再构建
"""

from __future__ import annotations

import argparse
import inspect
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))

#: 应用名称（与 ide_menu.gui.APP_TITLE 保持一致），同时用作 exe 文件名
APP_NAME = "通过IDE打开·右键菜单项管理（阿懂）"

#: (入口脚本, 输出名, 是否无控制台)
TARGETS: list[tuple[str, str, bool]] = [
    ("entry_gui.py", APP_NAME, True),
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


def _rmtree_capture(path: str) -> list[str]:
    """删除目录，返回删除失败的条目。

    之前用的是 ``shutil.rmtree(..., ignore_errors=True)``：如果 dist 里的 exe
    还在运行，删除会静默失败，旧产物就和新产物混在同一个 dist 里。所以这里
    收集失败项并交给调用方报错。
    """
    failed: list[str] = []
    if not os.path.isdir(path):
        return failed
    print(f"删除 {os.path.basename(path)}/ ...")

    def _handler(func, p, exc):
        detail = exc[1] if isinstance(exc, tuple) else exc
        failed.append(f"{p}  ({detail})")

    if "onexc" in inspect.signature(shutil.rmtree).parameters:  # Python >= 3.12
        shutil.rmtree(path, onexc=lambda f, p, e: _handler(f, p, (None, e, None)))
    else:  # pragma: no cover - Python 3.10 / 3.11
        shutil.rmtree(path, onerror=_handler)
    if os.path.isdir(path):
        failed.append(f"{path}  (目录仍然存在)")
    return failed


def _warn_running_in_dist() -> None:
    """如果 dist 里的 exe 正在运行，先提醒用户——否则清理一定不完整。"""
    dist = os.path.join(ROOT, "dist")
    if not os.path.isdir(dist):
        return
    names = {
        os.path.splitext(f)[0].lower()
        for f in os.listdir(dist)
        if f.lower().endswith(".exe")
    }
    if not names:
        return
    try:
        out = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"],
            capture_output=True, text=True, errors="replace", timeout=20,
        ).stdout
    except Exception:
        return
    for line in out.splitlines():
        parts = [p.strip('" ') for p in line.split('","')]
        if len(parts) < 2:
            continue
        image, pid = parts[0], parts[1]
        if os.path.splitext(os.path.basename(image))[0].lower() in names:
            print(f"  ! 正在运行: {image}  (pid {pid})  —— 会占用 dist，导致清理不完整")


def main() -> int:
    ap = argparse.ArgumentParser(description="构建 exe")
    ap.add_argument("--clean", action="store_true", help="构建前删除 build/ 与 dist/")
    args = ap.parse_args()

    py = find_python()
    print(f"使用 Python: {py}\n")

    if args.clean:
        _warn_running_in_dist()
        failures: list[str] = []
        for d in ("build", "dist"):
            failures += _rmtree_capture(os.path.join(ROOT, d))
        for f in os.listdir(ROOT):
            if f.endswith(".spec"):
                try:
                    os.remove(os.path.join(ROOT, f))
                    print(f"删除 {f}")
                except OSError as exc:
                    failures.append(f"{f}  ({exc})")
        if failures:
            print("\n清理不完整，以下文件没能删除（通常是被正在运行的 exe 占用）：", file=sys.stderr)
            for f in failures:
                print(f"  - {f}", file=sys.stderr)
            print(f"\n请先关闭“{APP_NAME}”，再重新构建。", file=sys.stderr)
            return 2
        print("清理完成。\n")

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