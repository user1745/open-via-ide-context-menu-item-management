# 通过IDE打开·右键菜单项管理（阿懂）

一个 Windows 右键菜单管理工具，用于查看和删除「通过IDE打开」级联菜单里的子菜单项。

## 这是什么

「通过IDE打开」是一个 **级联右键菜单**（static cascading menu）。它注册在三处：

| 场景 | 触发方式 | 注册表父键 |
|---|---|---|
| **文件** | 选中文件后右键 | `*\shell` |
| **文件夹** | 右键文件夹本身 | `Directory\shell` |
| **目录背景** | 在文件夹空白处右键 | `Directory\Background\shell` |

每一处的子菜单项都是各自独立注册的，数量和内容不一定相同，示例：

```
通过IDE打开
├── 通过 Code 打开
├── 通过 Cursor 打开
├── 通过 OpenCode 打开
└── 通过 TRAE CN 打开
```

本工具分别列出这三处的 **全部** 子菜单项（三列不做交集，各显示各的），并支持 **按名称一次性从多处同时删除**（某处没有该项则自动跳过）。

## 功能

- **三列并排展示** 各自上下文的全部子菜单项，双击任意一项即可填入输入框
- **一次输入，多处同步删除**
- **必须输入完整名称**：输入 `通过 Code 打开` 才会命中；只写 `Code`（注册表子键名）不会命中
- 支持 **通配符**：`通过 TRAE* 打开` 可匹配 `通过 TRAE CN 打开`
- **删除前自动备份**：每个将被改动的叶子键先 `reg export` 成 `.reg` 文件
- **一键重启资源管理器** 使改动立即生效
- 完整操作日志，可随时 **清空日志**
- 未匹配时会列出当前可用的完整名称，便于纠正输入

## 使用方法

### 图形界面

双击运行 **`dist\通过IDE打开·右键菜单项管理（阿懂）.exe`**

1. 在「要删除的子菜单项全称」输入框中填写 **完整名称**
   - 例如 `通过 Code 打开`、`通过 OpenCode 打开`
   - 多个名称用 **逗号 / 分号 / 竖线** 分隔；名称中的空格不会被拆开
   - 支持 `*` 和 `?` 通配符
   - 也可以直接 **双击下方列表项** 自动填入
2. 勾选要操作的上下文（默认三处全选；只影响删除范围，不影响列表显示）
3. 点 **预 览** 确认将要删除什么，满意后点 **删 除**
4. 按提示重启资源管理器

> 三个列表框始终显示各自上下文的真实内容，与勾选状态无关。

### 命令行（可选，仅源码方式）

不再单独打包命令行 exe，但 `ide_menu.cli` 仍在源码中保留：

```powershell
python -m ide_menu --list                          列出三处当前的子菜单项
python -m ide_menu -n "通过 Code 打开" --dry-run    预览，不实际删除
python -m ide_menu -n "通过 Code 打开" -y           删除（三处同时）
python -m ide_menu -n "通过 TRAE* 打开" -y          通配符
python -m ide_menu -n "通过 Code 打开" -c Bg        只处理目录背景
python -m ide_menu --help                          完整帮助
```

退出码：`0` 已删除 / `1` 无匹配（未做任何修改）/ `2` 错误。

## 从源码运行 / 构建

需要 **标准 Windows 版 CPython**（PyInstaller 不支持 MSYS2/MinGW 版 Python）。

```powershell
# 运行测试
python -m unittest discover -s tests -v

# 界面自检（打印布局与匹配规则自检后退出，不进入消息循环）
python -m ide_menu --self-test

# 构建 exe（产物在 dist\）
python build.py
```

`build.py` 只产出一个 onefile 可执行文件：

| 文件 | 用途 |
|---|---|
| `dist\通过IDE打开·右键菜单项管理（阿懂）.exe` | 图形界面（无控制台窗口） |

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

每个子项的 **显示名** 存在 `MUIVerb`，**注册表子键名**则是内部标识（如 `Code`、`TRAE SOLO CN`）。
本工具的匹配规则针对 **显示名**，因为那才是用户在右键菜单里看到的文字。

命令行占位符规则：

- `%1` = 选中的文件 / **文件夹**（用于 `*\shell` 和 `Directory\shell`）
- `%V` = 当前文件夹，**仅**用于 `Directory\Background\shell`

备份默认输出到 `%TEMP%\OpenViaIDE-backup\`，用 `reg import <文件>` 即可回滚。

## 目录结构

```
ide_menu/
    __init__.py
    core.py        注册表读写核心（winreg）
    cli.py         命令行界面（仅源码，不单独打包）
    gui.py         tkinter 图形界面
    __main__.py    入口分发
entry_gui.py        可执行文件入口
build.py            PyInstaller 构建脚本
tests/test_core.py  单元测试
```

## 注意事项

- 改动右键菜单后 **需要重启资源管理器** 才会生效。
- 本机装有 **ContextMenuManager** 一类会自动同步注册表的工具，它可能把被删除的子菜单项 **重新写回来**。删除后请确认一次；若被还原，需要在该工具中同步移除。
- 删除操作只影响 `HKCU`（当前用户）下的键，不需要管理员权限。

## 许可

仅供个人使用。