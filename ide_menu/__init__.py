"""通过IDE打开 · 右键菜单子项管理工具。

包结构：
    core  注册表读写核心
    cli   命令行界面（仅源码，不单独打包 exe）
    gui   图形界面（tkinter）
"""

__version__ = "1.3.0"
__all__ = ["core", "cli", "gui"]