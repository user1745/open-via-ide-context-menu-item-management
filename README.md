# 通过IDE打开·右键菜单项管理 (阿董)

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

双击运行 **`dist\通过IDE打开·右键菜单项管理 (阿董).exe`**

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
| `dist\通过IDE打开·右键菜单项管理 (阿董).exe` | 图形界面（无控制台窗口） |

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

### HKCR 合并视图（重要）

`ExtendedSubCommandsKey` 里的名字是相对 **HKCR** 解析的。HKCR 是
`HKLM\Software\Classes` 与 `HKCU\Software\Classes` 的**合并视图**，子键取**并集**。

所以同一个叶子键可能一半在 HKLM、一半在 HKCU，本工具的处理方式：

- **读取**两个配置单元并合并，值冲突时以 HKLM 优先（与系统顺序一致）；
- 界面里每一栏显示的是该上下文**自己那份合并后的完整列表**（各多少项就显示多少项）；
- **删除**时会对该项实际存在的每个配置单元都删一遍，避免残留另一半；
- 写 HKLM 需要管理员权限，不足时日志输出 `NEEDADMIN` 并提示以管理员身份重试。

本机实例：文件 / 目录背景各有 6 项（HKLM 的 CLion、Antigravity、ChatGPT
+ HKCU 的 Code、Cursor、OpenCode），文件夹因 HKLM 侧不存在而只有 3 项。

每个子项的 **显示名** 存在 `MUIVerb`，**注册表子键名**则是内部标识（如 `Code`）。
本工具的匹配规则针对 **显示名**，因为那才是用户在右键菜单里看到的文字。

> 注：注册表里可能存在「子键名与显示名对不上」的既有脏数据
> （例如子键 `Antigravity` 的显示名是「通过 CLion 打开」）。
> 由于显示名与实际启动的程序是一致的，菜单看起来是正常的，
> 而按显示名匹配也恰好不受这种脏数据影响。

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

- 改动右键菜单后 **需要重启资源管理器** 才会生效（界面提供按钮，不会自动重启）。
- 本机装有 **ContextMenuManager** 一类会自动同步注册表的工具，它可能把被删除的子菜单项 **重新写回来**。删除后请确认一次；若被还原，需要在该工具中同步移除。
- 删除 **HKCU** 下的键不需要管理员权限；删除 **HKLM** 下的键需要以管理员身份运行本程序，否则日志会给出 `NEEDADMIN` 提示。

## 许可

仅供个人使用。

---

## 新增：添加应用到「通过 IDE 打开」

界面顶部新增两个分页：**删除子菜单项** / **添加应用**。

「添加应用」页可以把一个新的可执行程序加入三个位置的「通过 IDE 打开」菜单。

### 使用方法

1. **程序路径** —— 点「浏览…」选择一个 `.exe`，或直接把完整路径粘贴/输入到输入框。
2. **应用名称** —— 默认自动取 exe 的文件名（去掉 `.exe`）。
   例如 `clion64.exe` → `CLion`（即 `D:\JetBrains\CLion 2026.1.1in\clion64.exe`）。
   若某个 exe 的文件名不合适（版本号、带后缀等），可点「从版本信息读取」，
   从 PE 版本信息的 `ProductName` → `FileDescription` → `InternalName` 依次取值。
3. **写入位置** ——
   - `当前用户（HKCU）`：不需要管理员权限，推荐；
   - `所有用户（HKLM）`：对全机生效，**需要以管理员身份运行本程序**，否则会提示权限不足。
4. 点「预 览」查看将要写入的内容，确认无误后点「添加到三个菜单」。

### 会写些什么

对 `文件` / `文件夹` / `目录背景` 三个上下文各写一条，形式为：

```
<hive>\Software\Classes\OpenViaIDE_<上下文>\shell\<子键名>\
    MUIVerb   = "通过 （应用名） 打开"
    Icon      = "C:\...\app.exe,0"
    command\
        ""   = "\"C:\...\app.exe\" \"%1\""      (Bg 上下文用 "%V")
```

- **图标**直接取该 exe 自身的第一个图标资源（注册表写法 `路径,0`）。
- **占位符**沿用既有规则：`%1` 用于文件 / 文件夹，`%V` 仅用于目录背景。
- **子键名**由应用名清洗而来（非法字符替换为 `_`），若已存在则自动追加 `_2`、`_3`…。
  子键名只是注册表内部标识，实际显示与匹配都以 **MUIVerb 全称** 为准。
- **自动去重**：若同一上下文里已存在「同名 + 同命令」的项，会跳过并提示，不会产生重复项。
- 写入前同样会导出 `.reg` 备份。

### 注意事项

- 添加后菜单不会立刻出现，需要重启资源管理器（界面上有「重启资源管理器」按钮）。
- `ContextMenuManager` 等后台工具可能会把 HKLM 下的条目改写回去。
