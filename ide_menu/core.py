"""注册表核心逻辑：管理级联右键菜单「通过 IDE 打开」的子菜单项。

菜单结构
--------
「通过 IDE 打开」是一个**级联菜单（static cascading menu）**：父菜单自身
不带 command，只有一个 ``ExtendedSubCommandsKey`` 指向存放真实子项的叶子键。

    HKCU\\Software\\Classes\\*\\shell\\OpenViaIDE                      -> OpenViaIDE_File
    HKCU\\Software\\Classes\\Directory\\shell\\OpenViaIDE              -> OpenViaIDE_Dir
    HKCU\\Software\\Classes\\Directory\\Background\\shell\\OpenViaIDE   -> OpenViaIDE_Bg

HKCR 合并视图（关键）
--------------------
``ExtendedSubCommandsKey`` 里的名字是相对 **HKCR** 解析的。HKCR 是
``HKLM\\Software\\Classes`` 与 ``HKCU\\Software\\Classes`` 的**合并视图**，
而且子键是**并集**关系：同一个叶子键可能一半在 HKLM、一半在 HKCU。

因此：

* 读取时必须**同时**看两个配置单元，否则会漏掉一半子菜单项
  （只读 HKCU 时会看不到 HKLM 里的 CLion / ChatGPT / Antigravity）。
* 值冲突时以 **HKLM 优先**（与 HKCR 的覆盖顺序一致）。
* 删除时必须对**该项实际存在的每个配置单元**都删一遍。
* 写 HKLM 需要管理员权限，权限不足会抛 PermissionError。

命令行占位符
------------
``%1``  选中的文件 / 文件夹  → File、Dir 上下文
``%V``  当前文件夹            → **仅** Bg（目录背景）上下文
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import fnmatch
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Iterator, Sequence

import winreg

__all__ = [
    "MenuItem",
    "Match",
    "ParentVerb",
    "RegistryError_",
    "AccessDenied_",
    "CONTEXT_IDS",
    "LEAF",
    "PARENT_KEY",
    "LABEL",
    "HIVES",
    "get_items",
    "select_matches",
    "split_names",
    "backup_leaf",
    "remove_items",
    "parent_verbs",
    "restart_explorer",
    "default_backup_dir",
]

# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------

CLASSES_PATH = r"Software\Classes"

#: 兼容旧名字（HKCU 只是其中之一）
HKCU_CLASSES = CLASSES_PATH

VERB_NAME = "OpenViaIDE"

#: 所有相关的配置单元。顺序即 HKCR 合并时的**覆盖优先级**（HKLM 在前）。
HIVES: dict[str, int] = {
    "HKLM": winreg.HKEY_LOCAL_MACHINE,
    "HKCU": winreg.HKEY_CURRENT_USER,
}

#: 需要写权限的配置单元（HKLM 需要管理员）
WRITABLE_HIVES: tuple[str, ...] = ("HKCU", "HKLM")

CONTEXT_IDS: tuple[str, ...] = ("File", "Dir", "Bg")

#: 存放真实子项的叶子键名
LEAF: dict[str, str] = {
    "File": "OpenViaIDE_File",
    "Dir": "OpenViaIDE_Dir",
    "Bg": "OpenViaIDE_Bg",
}

#: 指向各叶子键的父菜单注册表路径（相对 <hive>\Software\Classes）
PARENT_KEY: dict[str, str] = {
    "File": r"*\shell",
    "Dir": r"Directory\shell",
    "Bg": r"Directory\Background\shell",
}

#: 图形界面用中文名
LABEL: dict[str, str] = {
    "File": "文件（选中文件后右键）",
    "Dir": "文件夹（右键文件夹本身）",
    "Bg": "目录背景（文件夹空白处右键）",
}

#: 命令行用 ASCII 名（避免控制台代码页把中文显示成乱码）
LABEL_ASCII: dict[str, str] = {
    "File": r"FILE     (*\shell)",
    "Dir": r"FOLDER   (Directory\shell)",
    "Bg": r"BG       (Directory\Background\shell)",
}

# 显式指定 64 位视图，避免 32 位进程被 WOW64 重定向
_WOW64 = getattr(winreg, "KEY_WOW64_64KEY", 0)
_R = winreg.KEY_READ | _WOW64
_RW = winreg.KEY_ALL_ACCESS | _WOW64

DEFAULT_BACKUP_DIR = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "OpenViaIDE-backup")


class RegistryError_(RuntimeError):
    """无法打开/操作目标注册表键。"""


class AccessDenied_(PermissionError):
    """需要管理员权限才能操作（典型情况：写 HKLM）。"""


# --------------------------------------------------------------------------
# 数据结构
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MenuItem:
    """一个子菜单项（HKCR 合并视图下的一个逻辑项）。

    ``hives`` 记录该子键**实际存在于哪些配置单元**，删除时必须逐个处理。
    """

    context: str
    name: str          # 注册表子键名
    label: str         # 显示文本 MUIVerb
    command: str | None
    icon: str | None
    hives: tuple[str, ...] = ()

    @property
    def label_escaped(self) -> str:
        """非 ASCII 转成 \\uXXXX，供控制台安全输出。"""
        if not self.label:
            return ""
        return "".join(c if ord(c) < 127 else f"\\u{ord(c):04X}" for c in self.label)


@dataclass(frozen=True)
class Match:
    """一次命中：哪个上下文下的哪一项。

    ``name`` 是注册表子键名（真正删除时用的），``label`` 是用户可见的全称，
    ``hives`` 是该项实际所在的配置单元。
    """

    context: str
    name: str
    label: str = ""
    hives: tuple[str, ...] = ()

    @property
    def display(self) -> str:
        """日志/界面展示用：优先全称，没有则退回子键名。"""
        return self.label or self.name


@dataclass(frozen=True)
class ParentVerb:
    """父菜单项本身的状态。"""

    context: str
    menu_text: str
    target: str        # ExtendedSubCommandsKey 的值

    @property
    def wired(self) -> bool:
        return bool(self.target)


# --------------------------------------------------------------------------
# 底层工具
# --------------------------------------------------------------------------


def default_backup_dir() -> str:
    return DEFAULT_BACKUP_DIR


def _norm_contexts(contexts: Sequence[str] | None) -> tuple[str, ...]:
    if not contexts:
        return CONTEXT_IDS
    bad = [c for c in contexts if c not in LEAF]
    if bad:
        raise ValueError(f"未知上下文: {bad}；可选 {list(CONTEXT_IDS)}")
    # 保持固定顺序，输出稳定
    return tuple(c for c in CONTEXT_IDS if c in contexts)


def _hive_handle(hive: str | int) -> int:
    """``'HKCU'`` / ``'HKLM'`` 或原始 HKEY 常量 -> HKEY 句柄。"""
    if isinstance(hive, str):
        try:
            return HIVES[hive]
        except KeyError:
            raise ValueError(f"未知配置单元: {hive}；可选 {list(HIVES)}") from None
    return hive


def _hive_name(hive: str | int) -> str:
    if isinstance(hive, str):
        return hive
    for name, handle in HIVES.items():
        if handle == hive:
            return name
    return "HKCU"


def _open(path: str, access: int = _R, hive: str | int = "HKCU") -> int | None:
    try:
        return winreg.OpenKey(_hive_handle(hive), path, 0, access)
    except PermissionError:
        raise AccessDenied_(f"无权访问 {_hive_name(hive)}\\{path}（需要管理员权限）") from None
    except OSError:
        return None


@contextlib.contextmanager
def _root(access: int = _R, hive: str | int = "HKCU") -> Iterator[int]:
    """打开 ``<hive>\\Software\\Classes``，用完自动关闭。"""
    k = _open(CLASSES_PATH, access, hive)
    if k is None:
        raise RegistryError_(f"无法打开 {_hive_name(hive)}\\{CLASSES_PATH}")
    try:
        yield k
    finally:
        winreg.CloseKey(k)


def _open_child(parent: int, name: str, access: int = _R) -> int | None:
    try:
        return winreg.OpenKey(parent, name, 0, access)
    except OSError:
        return None


def _read_value(key: int, name: str) -> str | None:
    try:
        value, _kind = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    return value if isinstance(value, str) else str(value)


def _label_of(key: int) -> str:
    v = _read_value(key, "MUIVerb")
    if v is None:
        v = _read_value(key, "")
    return v or ""


def _command_of(key: int) -> str | None:
    ck = _open_child(key, "command")
    if ck is None:
        return None
    try:
        return _read_value(ck, "")
    finally:
        winreg.CloseKey(ck)


def _subkeys(key: int) -> list[str]:
    """列出直接子键名，按名称排序。"""
    names: list[str] = []
    idx = 0
    while True:
        try:
            names.append(winreg.EnumKey(key, idx))
        except OSError:
            break
        idx += 1
    return sorted(names)


def _delete_tree(hive: str | int, path: str) -> None:
    """递归删除注册表子树（先子后父）。"""
    k = _open(path, _RW, hive)
    if k is None:
        return
    for sub in _subkeys(k):
        _delete_tree(hive, path + "\\" + sub)
    winreg.CloseKey(k)
    try:
        winreg.DeleteKeyEx(_hive_handle(hive), path, _WOW64, 0)
    except PermissionError:
        raise AccessDenied_(f"无权删除 {_hive_name(hive)}\\{path}（需要管理员权限）") from None


#: 名称之间的分隔符：半角/全角逗号、分号、顿号、竖线、换行。
#: **空格不是分隔符** —— 因为子键名本身可能含空格（如 ``TRAE SOLO CN``）。
_SEP_RE = re.compile(r"[,;|，；、\r\n]+")


def split_names(text: str) -> list[str]:
    """
    把用户输入拆成多个名称模式。

    分隔符为 ``,`` ``;`` ``|`` ``，`` ``；`` ``、`` 和换行；
    **空格不分隔**，因此 ``TRAE SOLO CN`` 这类含空格的名称可以直接输入。
    每个片段会去掉首尾的双引号。
    """
    if not text or not text.strip():
        return []
    out: list[str] = []
    for part in _SEP_RE.split(text):
        t = part.strip().strip('"').strip("'").strip()
        if t:
            out.append(t)
    return out


def escape_non_ascii(text: str) -> str:
    """非 ASCII 转成 \\uXXXX，便于在任意代码页的控制台输出。"""
    if not text:
        return ""
    return "".join(c if ord(c) < 127 else f"\\u{ord(c):04X}" for c in text)


# --------------------------------------------------------------------------
# 读取
# --------------------------------------------------------------------------


def _leaf_names_by_hive(ctx: str) -> dict[str, list[str]]:
    """每个配置单元下，该上下文叶子键 ``shell`` 的直接子键名。"""
    out: dict[str, list[str]] = {}
    for hname in HIVES:
        with _root(hive=hname) as root:
            shell = _open_child(root, LEAF[ctx] + "\\shell")
            if shell is None:
                out[hname] = []
                continue
            try:
                out[hname] = _subkeys(shell)
            finally:
                winreg.CloseKey(shell)
    return out


def get_items(contexts: Sequence[str] | None = None) -> list[MenuItem]:
    """
    读取指定上下文的全部子菜单项（默认三处全读）。

    返回的是 **HKCR 合并视图**：``HKLM`` 与 ``HKCU`` 的子键并集，
    值冲突时以 HKLM 为准（与系统解析顺序一致）。
    """
    ctxs = _norm_contexts(contexts)
    items: list[MenuItem] = []
    for ctx in ctxs:
        per_hive = _leaf_names_by_hive(ctx)
        names: list[str] = []
        for hname in HIVES:                      # 保持 HKLM 在前的稳定顺序
            for n in per_hive.get(hname, []):
                if n not in names:
                    names.append(n)
        for name in names:
            present = tuple(h for h in HIVES if name in per_hive.get(h, []))
            label = ""
            command: str | None = None
            icon: str | None = None
            for h in HIVES:                      # HKLM 优先覆盖
                if h not in present:
                    continue
                with _root(hive=h) as root:
                    shell = _open_child(root, LEAF[ctx] + "\\shell")
                    if shell is None:
                        continue
                    k = _open_child(shell, name)
                    if k is None:
                        winreg.CloseKey(shell)
                        continue
                    try:
                        label = _label_of(k) or label
                        command = _command_of(k) or command
                        icon = _read_value(k, "Icon") or icon
                    finally:
                        winreg.CloseKey(k)
                        winreg.CloseKey(shell)
                break
            items.append(
                MenuItem(context=ctx, name=name, label=label,
                         command=command, icon=icon, hives=present)
            )
    return items


def parent_verbs(contexts: Sequence[str] | None = None) -> list[ParentVerb]:
    """读取三处父菜单自身的状态（HKCU 优先，HKLM 兜底）。"""
    ctxs = _norm_contexts(contexts)
    out: list[ParentVerb] = []
    done: set[str] = set()
    for hname in ("HKCU", "HKLM"):
        with _root(hive=hname) as root:
            for ctx in ctxs:
                if ctx in done:
                    continue
                pk = _open_child(root, PARENT_KEY[ctx])
                if pk is None:
                    continue
                try:
                    vk = _open_child(pk, VERB_NAME)
                    if vk is None:
                        continue
                    try:
                        out.append(
                            ParentVerb(
                                context=ctx,
                                menu_text=_label_of(vk),
                                target=_read_value(vk, "ExtendedSubCommandsKey") or "",
                            )
                        )
                        done.add(ctx)
                    finally:
                        winreg.CloseKey(vk)
                finally:
                    winreg.CloseKey(pk)
    return out


# --------------------------------------------------------------------------
# 匹配
# --------------------------------------------------------------------------


def select_matches(
    patterns: Sequence[str],
    contexts: Sequence[str] | None = None,
) -> list[Match]:
    """
    按子菜单项的**完整显示名**（MUIVerb，如「通过 Code 打开」）匹配。

    * 模式针对显示名做 fnmatch，不区分大小写，支持 ``*`` / ``?`` 通配符。
    * **必须输入全称**：只写应用名（如 ``Code``）不会命中，
      因为那是注册表子键名，不是用户在右键菜单里看到的文字。
    * 某个模式下在一个上下文内命中一次即算命中。
    """
    ctxs = _norm_contexts(contexts)
    items = get_items(ctxs)
    hits: list[Match] = []
    for ctx in ctxs:
        for it in (i for i in items if i.context == ctx):
            for p in patterns:
                if fnmatch.fnmatchcase(it.label.lower(), p.lower()):
                    hits.append(Match(ctx, it.name, it.label, it.hives))
                    break
    return hits


# --------------------------------------------------------------------------
# 备份
# --------------------------------------------------------------------------


def backup_leaf(context: str, backup_dir: str | None = None, stamp: str | None = None,
                hives: Sequence[str] | None = None) -> list[str]:
    """
    把一个叶子键逐配置单元导出成 .reg 备份，返回成功生成的文件路径列表。

    ``hives`` 缺省为 ``('HKCU',)``；删除涉及 HKLM 时请显式传入。
    """
    if context not in LEAF:
        raise ValueError(f"未知上下文: {context}")
    backup_dir = backup_dir or DEFAULT_BACKUP_DIR
    stamp = stamp or _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    os.makedirs(backup_dir, exist_ok=True)
    made: list[str] = []
    for hname in (hives or ("HKCU",)):
        if hname not in HIVES:
            continue
        reg = os.path.join(backup_dir, f"{LEAF[context]}_{hname}_{stamp}.reg")
        src = f"{hname}\\{CLASSES_PATH}\\{LEAF[context]}"
        try:
            r = subprocess.run(
                ["reg.exe", "export", src, reg, "/y"],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if r.returncode == 0 and os.path.exists(reg):
            made.append(reg)
    return made


# --------------------------------------------------------------------------
# 删除
# --------------------------------------------------------------------------


def remove_items(
    plan: Sequence[Match],
    contexts: Sequence[str] | None = None,
    *,
    prune_empty: bool = False,
    backup: bool = True,
    backup_dir: str | None = None,
    stamp: str | None = None,
) -> list[str]:
    """
    删除计划中的子菜单项，返回操作日志行。

    对每个命中项，会在它**实际存在的每个配置单元**下删除
    （HKCR 是合并视图，只删一边会残留另一半）。

    日志前缀：``BACKUP`` / ``REMOVED`` / ``PRUNED`` / ``SKIP`` / ``WARN`` /
    ``NEEDADMIN``。
    """
    ctxs = _norm_contexts(contexts)
    stamp = stamp or _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    log: list[str] = []
    if not plan:
        return log

    def item_path(ctx: str, name: str) -> str:
        return f"{CLASSES_PATH}\\{LEAF[ctx]}\\shell\\{name}"

    def exists(hive: str, ctx: str, name: str) -> bool:
        with _root(hive=hive) as root:
            shell = _open_child(root, LEAF[ctx] + "\\shell")
            if shell is None:
                return False
            try:
                return name in _subkeys(shell)
            finally:
                winreg.CloseKey(shell)

    for ctx in ctxs:
        targets = [m for m in plan if m.context == ctx]
        if not targets:
            continue
        hives_here: list[str] = []
        for m in targets:
            for h in (m.hives or ("HKCU",)):
                if h not in hives_here:
                    hives_here.append(h)

        # 先把所有要改动的叶子键各备份一次（删除之前）
        if backup:
            os.makedirs(backup_dir or DEFAULT_BACKUP_DIR, exist_ok=True)
            for p in backup_leaf(ctx, backup_dir, stamp, hives_here):
                log.append(f"BACKUP  {LABEL_ASCII[ctx]} -> {p}")

        for m in targets:
            for hive in (m.hives or ("HKCU",)):
                path = item_path(ctx, m.name)
                try:
                    if not exists(hive, ctx, m.name):
                        log.append(f"SKIP    {LABEL_ASCII[ctx]} : '{m.display}' 在 {hive} 不存在")
                        continue
                    _delete_tree(hive, path)
                    log.append(f"REMOVED {LABEL_ASCII[ctx]} : '{m.display}' [{hive}]")
                except AccessDenied_ as exc:
                    log.append(f"NEEDADMIN {LABEL_ASCII[ctx]} : '{m.display}' [{hive}] -> {exc}")
                except OSError as exc:
                    log.append(f"SKIP    {LABEL_ASCII[ctx]} : 删除 '{m.display}' [{hive}] 失败 ({exc})")

        if prune_empty:
            remaining = [i for i in get_items([ctx]) if any(m.name == i.name for m in targets)]
            if not remaining:
                log.append(f"PRUNED  {LABEL_ASCII[ctx]} : 叶子键已空")
                for hive in hives_here:
                    pk_path = f"{CLASSES_PATH}\\{PARENT_KEY[ctx]}\\{VERB_NAME}"
                    try:
                        with _root(hive=hive) as root:
                            pk = _open_child(root, PARENT_KEY[ctx], _RW)
                        if pk is None:
                            continue
                        try:
                            has_verb = VERB_NAME in _subkeys(pk)
                        finally:
                            winreg.CloseKey(pk)
                        if not has_verb:
                            continue
                        _delete_tree(hive, pk_path)
                        log.append(f"PRUNED  {LABEL_ASCII[ctx]} : 空的父菜单已删除 [{hive}]")
                    except AccessDenied_ as exc:
                        log.append(f"NEEDADMIN {LABEL_ASCII[ctx]} : 删除父菜单失败 [{hive}] ({exc})")
                    except OSError as exc:
                        log.append(f"SKIP    {LABEL_ASCII[ctx]} : 删除父菜单失败 [{hive}] ({exc})")
    return log


# --------------------------------------------------------------------------
# 其它
# --------------------------------------------------------------------------


def restart_explorer() -> None:
    """重启 explorer.exe，让右键菜单改动生效。"""
    subprocess.run(
        ["taskkill.exe", "/F", "/IM", "explorer.exe"],
        capture_output=True,
        timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    time.sleep(0.7)
    os.startfile("explorer.exe")  # noqa: S606


def open_backup_dir(backup_dir: str | None = None) -> str:
    """确保备份目录存在并用系统文件管理器打开。"""
    d = backup_dir or DEFAULT_BACKUP_DIR
    os.makedirs(d, exist_ok=True)
    os.startfile(d)  # noqa: S606
    return d


def export_backup_dir() -> str:
    return DEFAULT_BACKUP_DIR


def which(name: str) -> str | None:
    return shutil.which(name)