"""PyInstaller 命令行版入口（打包为带控制台 exe）。"""

from __future__ import annotations

import multiprocessing
import sys

from ide_menu.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main(sys.argv[1:]))