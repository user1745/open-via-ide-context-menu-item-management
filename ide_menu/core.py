"""注册表核心逻辑：管理级联右键菜单「通过 IDE 打开」的子菜单项。

菜单结构
--------
「通过 IDE 打开」是一个**级联菜单（static cascading menu）**：父菜单自身
不带 command，只有一个 ``ExtendedSubCommandsKey`` 指向存放真实子项的叶子键。

    HKCU\\Software\\Classes\\*\\shell\\OpenViaIDE                      -> OpenViaIDE_File
    HKCU\\Software\\Classes\\Directory\\shell\\OpenViaIDE              -> OpenViaIDE_Dir
    HKCU\\Software\\Classes\\Directory\\Background\\shell\\OpenViaIDE   -> OpenViaIDE_Bg

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
    "CONTEXT_IDS",
    "LEAF",
    "PARENT_KEY",
    "LABEL",
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

HKCU_CLASSES = r"Software\Classes"
VERB_NAME = "OpenViaIDE"

CONTEXT_IDS: tuple[str, ...] = ("File", "Dir", "Bg")

#: 存放真实子项的叶子键名
LEAF: dict[str, str] = {
    "File": "OpenViaIDE_File",
    "Dir": "OpenViaIDE_Dir",
    "Bg": "OpenViaIDE_Bg",
}

#: 指向各叶子键的父菜单注册表路径（相对 HKCU\Software\Classes）
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


# --------------------------------------------------------------------------
# 数据结构
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MenuItem:
    """一个子菜单项。"""

    context: str
    name: str          # 注册表子键名（传给 -Name 的就是这个）
    label: str         # 显示文本 MUIVerb
    command: str | None
    icon: str | None

    @property
    def label_escaped(self) -> str:
        """非 ASCII 转成 \\uXXXX，供控制台安全输出。"""
        if not self.label:
            return ""
        return "".join(c if ord(c) < 127 else f"\\u{ord(c):04X}" for c in self.label)


@dataclass(frozen=True)
class Match:
    """一次命中：哪个上下文下的哪一项。

    ``name`` 是注册表子键名（真正删除时用的），``label`` 是用户可见的全称。
    """

    context: str
    name: str
    label: str = ""

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


def _open(path: str, access: int = _R) -> int | None:
    try:
        return winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, access)
    except OSError:
        return None


@contextlib.contextmanager
def _root(access: int = _R) -> Iterator[int]:
    """打开 HKCU\\Software\\Classes，用完自动关闭。"""
    k = _open(HKCU_CLASSES, access)
    if k is None:
        raise RegistryError_(f"无法打开 HKCU\\{HKCU_CLASSES}")
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


def _delete_tree(hive: int, path: str) -> None:
    """递归删除注册表子树（先子后父）。"""
    k = _open(path, _RW)
    if k is None:
        return
    for sub in _subkeys(k):
        _delete_tree(hive, path + "\\" + sub)
    winreg.CloseKey(k)
    winreg.DeleteKeyEx(hive, path, _WOW64, 0)


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


def get_items(contexts: Sequence[str] | None = None) -> list[MenuItem]:
    """读取指定上下文的全部子菜单项（默认三处全读）。"""
    ctxs = _norm_contexts(contexts)
    items: list[MenuItem] = []
    with _root() as root:
        for ctx in ctxs:
            shell = _open_child(root, LEAF[ctx] + "\\shell")
            if shell is None:
                continue
            try:
                for name in _subkeys(shell):
                    k = _open_child(shell, name)
                    if k is None:
                        continue
                    try:
                        items.append(
                            MenuItem(
                                context=ctx,
                                name=name,
                                label=_label_of(k),
                                command=_command_of(k),
                                icon=_read_value(k, "Icon"),
                            )
                        )
                    finally:
                        winreg.CloseKey(k)
            finally:
                winreg.CloseKey(shell)
    return items


def parent_verbs(contexts: Sequence[str] | None = None) -> list[ParentVerb]:
    """读取三处父菜单自身的状态。"""
    ctxs = _norm_contexts(contexts)
    out: list[ParentVerb] = []
    with _root() as root:
        for ctx in ctxs:
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
                    hits.append(Match(ctx, it.name, it.label))
                    break
    return hits


# --------------------------------------------------------------------------
# 备份
# --------------------------------------------------------------------------


def backup_leaf(context: str, backup_dir: str | None = None, stamp: str | None = None) -> str | None:
    """把一个叶子键导出成 .reg 备份，返回文件路径（失败返回 None）。"""
    if context not in LEAF:
        raise ValueError(f"未知上下文: {context}")
    backup_dir = backup_dir or DEFAULT_BACKUP_DIR
    stamp = stamp or _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    os.makedirs(backup_dir, exist_ok=True)
    reg = os.path.join(backup_dir, f"{LEAF[context]}_{stamp}.reg")
    src = f"HKCU\\{HKCU_CLASSES}\\{LEAF[context]}"
    try:
        r = subprocess.run(
            ["reg.exe", "export", src, reg, "/y"],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return reg if r.returncode == 0 and os.path.exists(reg) else None


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

    日志前缀：``BACKUP`` / ``REMOVED`` / ``PRUNED`` / ``SKIP`` / ``WARN``。
    """
    ctxs = _norm_contexts(contexts)
    stamp = stamp or _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    log: list[str] = []
    if not plan:
        return log

    with _root(_RW) as root:
        # 先把所有要改动的叶子键各备份一次（删除之前）
        if backup:
            os.makedirs(backup_dir or DEFAULT_BACKUP_DIR, exist_ok=True)
            for ctx in ctxs:
                if not any(m.context == ctx for m in plan):
                    continue
                p = backup_leaf(ctx, backup_dir, stamp)
                if p:
                    log.append(f"BACKUP  {LABEL_ASCII[ctx]} -> {p}")
                else:
                    log.append(f"WARN    备份失败: {LEAF[ctx]}")

        for ctx in ctxs:
            targets = [m.name for m in plan if m.context == ctx]
            if not targets:
                continue
            leaf_shell = LEAF[ctx] + "\\shell"
            shell = _open_child(root, leaf_shell, _RW)
            if shell is None:
                log.append(f"SKIP    {LABEL_ASCII[ctx]} : 叶子键已消失")
                continue
            present = set(_subkeys(shell))
            winreg.CloseKey(shell)

            for name in targets:
                if name not in present:
                    log.append(f"SKIP    {LABEL_ASCII[ctx]} : '{name}' 已不存在")
                    continue
                try:
                    _delete_tree(winreg.HKEY_CURRENT_USER, f"{HKCU_CLASSES}\\{leaf_shell}\\{name}")
                    log.append(f"REMOVED {LABEL_ASCII[ctx]} : '{name}'")
                except OSError as exc:
                    log.append(f"SKIP    {LABEL_ASCII[ctx]} : 删除 '{name}' 失败 ({exc})")

            if prune_empty:
                shell = _open_child(root, leaf_shell)
                if shell is not None:
                    still = _subkeys(shell)
                    winreg.CloseKey(shell)
                    if not still:
                        log.append(f"PRUNED  {LABEL_ASCII[ctx]} : 叶子键已空")
                        pk = _open_child(root, PARENT_KEY[ctx], _RW)
                        if pk is not None:
                            has_verb = VERB_NAME in _subkeys(pk)
                            winreg.CloseKey(pk)
                            if has_verb:
                                try:
                                    _delete_tree(
                                        winreg.HKEY_CURRENT_USER,
                                        f"{HKCU_CLASSES}\\{PARENT_KEY[ctx]}\\{VERB_NAME}",
                                    )
                                    log.append(f"PRUNED  {LABEL_ASCII[ctx]} : 空的父菜单已删除")
                                except OSError as exc:
                                    log.append(f"SKIP    {LABEL_ASCII[ctx]} : 删除父菜单失败 ({exc})")
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