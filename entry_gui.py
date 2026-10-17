"""PyInstaller 图形版入口（打包为无控制台窗口 exe）。"""

from __future__ import annotations

import multiprocessing
import sys

from ide_menu import core
from ide_menu.gui import APP_TITLE, main

if __name__ == "__main__":
    multiprocessing.freeze_support()

    # 兜底：正常情况下 --uac-admin 已经让 Windows 在启动前就弹 UAC，
    # 这里只覆盖「用 python 直接跑」或「打包时漏了 --uac-admin」的情况。
    argv = sys.argv[1:]
    if "--self-test" not in argv and not core.is_admin():
        if not core.require_admin(gui_title=APP_TITLE, gui=True):
            pass  # 用户拒绝提权 -> 以当前身份继续，至少 HKCU 部分还能用
        else:
            raise SystemExit(0)  # 已重新以管理员身份拉起，本进程退出

    raise SystemExit(main(argv))