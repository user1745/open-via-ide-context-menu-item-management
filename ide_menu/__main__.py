"""包入口：``python -m ide_menu``。

默认启动图形界面；带任何子命令时走命令行。
"""

from __future__ import annotations

import sys
from typing import Sequence

USAGE = """\
用法:
  python -m ide_menu              启动图形界面
  python -m ide_menu --list       列出三处当前的子菜单项
  python -m ide_menu -n '通过 Code 打开'
                                  删除子菜单项（必须输入全称，其余参数见 --help）
  python -m ide_menu --help       查看命令行帮助
"""


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cli_flags = {
        "-l", "--list", "-n", "--name", "-c", "--context",
        "-p", "--prune-empty", "-b", "--no-backup", "-B", "--backup-dir",
        "--dry-run", "-y", "--yes", "--restart", "--open-backups", "--json",
        "-h", "--help", "--version",
    }
    if any(a in cli_flags for a in args):
        from .cli import main as cli_main

        return cli_main(args)

    if args and args[0] in ("-h", "--help"):
        print(USAGE)
        return 0

    from .gui import main as gui_main

    return gui_main(args)


if __name__ == "__main__":
    raise SystemExit(main())