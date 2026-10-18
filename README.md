<div align="center">

# 通过 IDE 打开 · 右键菜单项管理

**Windows 右键菜单管理工具：查看、备份、删除或添加「通过 IDE 打开」级联菜单项。**

[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-informational.svg)](https://learn.microsoft.com/windows/)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![GUI](https://img.shields.io/badge/GUI-Tkinter-purple.svg)](https://docs.python.org/3/library/tkinter.html)
[![Build](https://img.shields.io/badge/Build-PyInstaller-blue.svg)](https://pyinstaller.org/)

</div>

## 目录

- [核心特性](#核心特性)
- [工作原理](#工作原理)
- [安装与运行](#安装与运行)
- [使用方法](#使用方法)
- [命令行接口](#命令行接口)
- [从源码构建](#从源码构建)
- [项目结构](#项目结构)
- [权限与安全](#权限与安全)
- [常见问题](#常见问题)
- [许可证](#许可证)

## 核心特性

| 特性 | 说明 |
| --- | --- |
| 三种上下文 | 分别管理文件、文件夹和目录背景中的级联菜单 |
| 独立列表 | 三列展示各自真实存在的全部子菜单项，不做交集 |
| 批量删除 | 一次输入完整菜单名称，可同时处理多个上下文 |
| 通配符 | 支持 `*` 和 `?` 匹配菜单显示名称 |
| 自动备份 | 删除前对实际修改的注册表叶子键导出 `.reg` 备份 |
| 添加应用 | 将新的 exe 添加到三个「通过 IDE 打开」菜单 |
| 原生界面 | Tkinter GUI，支持日志、预览、刷新和资源管理器重启 |
| 命令行 | 支持列出、预览、删除和自检 |

## 工作原理

「通过 IDE 打开」是一个 Windows 级联右键菜单。它通过 `ExtendedSubCommandsKey` 指向三个叶子键：

```text
文件：        HKCU/HKLM\Software\Classes\*\shell\OpenViaIDE_File
文件夹：      HKCU/HKLM\Software\Classes\Directory\shell\OpenViaIDE_Dir
目录背景：    HKCU/HKLM\Software\Classes\Directory\Background\shell\OpenViaIDE_Bg
```

工具读取并合并 `HKCU` 与 `HKLM` 的注册表内容，按菜单显示名排序。删除时会检查两个配置单元，尽量避免只删除一半导致残留。

> `HKCR` 是 `HKCU\Software\Classes` 与 `HKLM\Software\Classes` 的合并视图；写入或删除 HKLM 内容需要管理员权限。

## 安装与运行

### 使用打包 exe

从 Release 或本地 `dist\` 目录运行：

```text
通过IDE打开·右键菜单项管理 (阿董).exe
```

程序会根据清单请求管理员权限，以便处理位于 HKLM 的系统级菜单项。

### 从源码运行

需要标准 Windows 版 CPython；不支持 MSYS2/MinGW 版 Python：

```powershell
git clone https://github.com/user1745/open-via-ide-context-menu-item-management.git
cd open-via-ide-context-menu-item-management
python -m ide_menu --self-test
python entry_gui.py
```

## 使用方法

### 查看与删除

1. 在「删除子菜单项」页查看文件、文件夹和目录背景三列。
2. 输入完整显示名称，例如 `通过 Code 打开`。
3. 多个名称可用逗号、分号或竖线分隔；支持 `通过 TRAE* 打开`。
4. 点击「预览」确认命中项。
5. 确认后点击「删除」，需要时重启资源管理器使改动生效。

必须输入菜单显示名称，而不是注册表内部子键名。

### 添加应用

1. 选择或输入 `.exe` 路径。
2. 确认应用名称和写入范围。
3. 预览将写入的三处菜单项。
4. 点击「添加到三个菜单」，然后重启资源管理器。

程序会自动使用 exe 图标、生成安全的注册表子键名，并在写入前导出备份。

## 命令行接口

```powershell
python -m ide_menu --list
python -m ide_menu -n "通过 Code 打开" --dry-run
python -m ide_menu -n "通过 Code 打开" -y
python -m ide_menu -n "通过 TRAE* 打开" -y
python -m ide_menu -n "通过 Code 打开" -c Bg
python -m ide_menu --self-test
```

退出码：`0` 表示已删除或自检通过，`1` 表示无匹配且未修改，`2` 表示发生错误。

## 从源码构建

```powershell
python -m unittest discover -s tests -v
python -m ide_menu --self-test
python build.py
```

`build.py` 使用 PyInstaller 生成 onefile GUI exe，并写入管理员权限清单。

## 项目结构

```text
├── ide_menu/
│   ├── core.py          # 注册表读写、匹配、备份与权限逻辑
│   ├── cli.py           # 命令行接口
│   ├── gui.py           # Tkinter 图形界面
│   └── __main__.py      # 入口分发
├── entry_gui.py         # GUI 入口
├── build.py             # PyInstaller 构建脚本
├── tests/               # 单元测试
├── requirements.txt
└── README.md
```

## 权限与安全

- 修改注册表前会创建 `.reg` 备份；默认备份目录为 `%TEMP%\OpenViaIDE-backup\`。
- 删除 HKCU 项通常不需要管理员权限；删除或添加 HKLM 项需要管理员权限。
- 本工具不会自动重启资源管理器，改动生效前请保存其他程序中的工作。
- 第三方注册表同步工具可能把已删除项目重新写回，需要在对应工具中同步清理。

## 常见问题

### 菜单没有立即变化

重启资源管理器；如果仍未变化，检查项目是否同时存在于 HKCU 和 HKLM，或被其他菜单管理工具恢复。

### 删除提示 `NEEDADMIN`

以管理员身份重新运行程序。HKLM 下的系统级菜单项不能由普通用户写入。

### 误删后如何恢复

使用删除前生成的 `.reg` 文件执行 `reg import <备份文件>`，或从备份目录中选择对应配置单元的导出文件。

## 许可证

本仓库当前未声明开源许可证。使用、修改和再分发前请先获得作者授权；其中 Windows、Python、PyInstaller 及其他工具链分别受其自身许可证约束。