"""PyInstaller 图形版入口（打包为无控制台窗口 exe）。"""

from __future__ import annotations

import multiprocessing
import sys

from ide_menu.gui import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main(sys.argv[1:]))