# 通过 IDE 打开 · 右键菜单项管理

一个 Windows 右键菜单管理工具，用于查看和删除「通过IDE打开」级联菜单里的子菜单项。

## 这是什么

「通过IDE打开」是一个 **级联右键菜单**（static cascading menu）。它注册了三处：

| 场景 | 触发方式 |
|---|---|
| **文件** | 选中文件后右键 |
| **文件夹** | 右键文件夹本身 |
| **目录背景** | 在文件夹空白处右键 |

三处菜单结构完全一致，都包含同样的子菜单项，例如：

```
通过IDE打开
├── 通过 Code 打开
├── 通过 Cursor 打开
├── 通过 OpenCode 打开
└── 通过 TRAE CN 打开
```

本工具列出这三处的全部子菜单项，并支持 **按名称一次性从三处同时删除**（某处没有该项则自动跳过）。

## 功能

- **三列并排展示** 三处的子菜单项，双击任意一项即可填入输入框
- **一次输入，三处同步删除**
- 支持 **通配符**：`TRAE*` 可匹配 `TRAE SOLO CN`
- 支持 **按显示名匹配**：输入 `TRAE CN` 也能命中注册表子键 `TRAE SOLO CN`
- **删除前自动备份**：每个将被改动的叶子键先 `reg export` 成 `.reg` 文件
- **一键重启资源管理器** 使改动立即生效
- 全部改动写入日志区，可回溯

## 使用方法

### 图形界面

双击运行 **`dist\通过IDE打开-菜单管理器.exe`**

1. 在「要删除的子菜单项名称」输入框中填写名称
   - 多个名称用 **逗号 / 分号 / 竖线** 分隔，例如 `Code, Cursor`
   - 名称本身可以含空格，例如 `TRAE SOLO CN`
   - 支持 `*` 和 `?` 通配符
   - 也可以直接 **双击下方列表项** 自动填入
2. 勾选要操作的上下文（默认三处全选）
3. 点 **预 览** 确认将要删除什么，满意后点 **删 除**
4. 按提示重启资源管理器

### 命令行

```
dist\ide-menu-cli.exe --list                  列出三处当前的子菜单项
dist\ide-menu-cli.exe -n Code                 删除 Code（三处同时）
dist\ide-menu-cli.exe -n "Code,Cursor"        删除多个
dist\ide-menu-cli.exe -n "TRAE*" --dry-run    预览，不实际删除
dist\ide-menu-cli.exe -n Code --context Bg    只删除目录背景中的 Code
dist\ide-menu-cli.exe -n "TRAE CN" -m         按显示名匹配
dist\ide-menu-cli.exe --help                  完整帮助
```

退出码：`0` 已删除 / `1` 无匹配（未做任何修改）/ `2` 错误。

## 从源码运行 / 构建

需要 **标准 Windows 版 CPython**（PyInstaller 不支持 MSYS2/MinGW 版 Python）。

```powershell
# 运行测试
python -m unittest discover -s tests -v

# 界面自检（无头打印布局后退出）
python -m ide_menu --self-test

# 构建 exe（产物在 dist\）
python build.py
```

`build.py` 会产出两个 onefile 可执行文件：

| 文件 | 用途 |
|---|---|
| `dist\通过IDE打开-菜单管理器.exe` | 图形界面（无控制台窗口） |
| `dist\ide-menu-cli.exe` | 命令行 |

## 工作原理

该菜单项本身没有命令，只有一个指向叶子键的指针（`ExtendedSubCommandsKey`）：

```
HKCU\Software\Classes\*\shell\OpenViaIDE
                                └─ ExtendedSubCommandsKey = OpenViaIDE_File
HKCU\Software\Classes\Directory\shell\OpenViaIDE
                                └─ ExtendedSubCommandsKey = OpenViaIDE_Dir
HKCU\Software\Classes\Directory\Background\shell\OpenViaIDE
                                └─ ExtendedSubCommandsKey = OpenViaIDE_Bg
```

三个叶子键 `OpenViaIDE_File` / `OpenViaIDE_Dir` / `OpenViaIDE_Bg` 下才是真正的子菜单项。

命令行占位符规则：

- `%1` = 选中的文件 / **文件夹**（用于 `*\shell` 和 `Directory\shell`）
- `%V` = 当前文件夹，**仅**用于 `Directory\Background\shell`

备份默认输出到 `%TEMP%\OpenViaIDE-backup\`，用 `reg import <文件>` 即可回滚。

## 目录结构

```
ide_menu/
    __init__.py
    core.py        注册表读写核心（winreg）
    cli.py         命令行界面
    gui.py         tkinter 图形界面
    __main__.py    入口分发
entry_gui.py        GUI 可执行文件入口
entry_cli.py        CLI 可执行文件入口
build.py            PyInstaller 构建脚本
tests/test_core.py  单元测试
```

## 注意事项

- 改动右键菜单后 **需要重启资源管理器** 才会生效。
- 本机装有 **ContextMenuManager** 一类会自动同步注册表的工具，它可能把被删除的子菜单项 **重新写回来**。删除后请确认一次；若被还原，需要在该工具中同步移除。
- 删除操作只影响 `HKCU`（当前用户）下的键，不需要管理员权限。

## 许可

仅供个人使用。