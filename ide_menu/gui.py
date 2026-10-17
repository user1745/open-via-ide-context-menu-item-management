"""图形界面（tkinter）：通过IDE打开·右键菜单项管理 (阿董)。"""

from __future__ import annotations

import os
import sys
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Sequence

from . import core

#: 应用名称，同时用作窗口标题栏文字。
APP_TITLE = "通过IDE打开·右键菜单项管理 (阿董)"

HINT_TEXT = (
    "请输入子菜单项的完整名称，例如「通过 Code 打开」「通过 OpenCode 打开」；"
    "只写应用名（Code）不会命中。"
    "多个名称用 逗号 / 分号 / 竖线 分隔（名称中的空格不会被拆开）；"
    "支持 * ? 通配符；双击下方任意一项可自动填入。"
)

COL_ACCENT = "#c62828"
COL_MUTED = "#666666"
COL_OK = "#2e7d32"
COL_WARN = "#b26a00"
COL_INFO = "#1565c0"


class App:
    """主窗口。所有状态都在实例上，回调通过 self 访问。"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.resizable(True, True)

        self.var_name = tk.StringVar()
        self.var_prune = tk.BooleanVar(value=False)
        # 「添加应用」页的状态
        self.var_exe = tk.StringVar()
        self.var_app = tk.StringVar()
        self.var_hive = tk.StringVar(value="HKCU")
        self.var_ctx = {c: tk.BooleanVar(value=True) for c in core.CONTEXT_IDS}
        self.var_status = tk.StringVar(value="就绪")
        self.listboxes: dict[str, tk.Listbox] = {}
        self._history: list[str] = []
        self._labels: dict[str, list[str]] = {c: [] for c in core.CONTEXT_IDS}

        self._style()
        self._layout()
        self._bind()
        self.refresh(initial=True)

    # ---------------------------------------------------------------- 样式
    def _style(self) -> None:
        st = ttk.Style()
        # NOTE: the 'vista' ttk theme IGNORES a style's `background`, so on
        # Windows a ttk.Button can never be filled red. 'clam' is the only
        # built-in theme that honours it -- using it app-wide also guarantees
        # the 删除 button looks exactly like 刷新 / 重启资源管理器, just red.
        for name in ("clam", "vista"):
            try:
                st.theme_use(name)
                break
            except tk.TclError:
                continue
        base = ("Microsoft YaHei UI", 10)
        self.root.option_add("*Font", base)
        st.configure(".", font=base)
        st.configure("Hint.TLabel", foreground=COL_MUTED, font=("Microsoft YaHei UI", 9))
        st.configure("GroupTitle.TLabelframe.Label", font=("Microsoft YaHei UI", 10, "bold"))
        st.configure("Status.TLabel", foreground=COL_MUTED, font=("Microsoft YaHei UI", 9))
        st.configure("Danger.TButton", font=("Microsoft YaHei UI", 10, "bold"),
                     background=COL_ACCENT, foreground="#ffffff",
                     bordercolor=COL_ACCENT, focuscolor=COL_ACCENT)
        st.map("Danger.TButton",
               background=[("pressed", "#8d1b1b"), ("active", "#a51f1f"), ("disabled", "#e0b4b4")],
               foreground=[("disabled", "#f2f2f2")])
        st.configure("Primary.TButton", font=("Microsoft YaHei UI", 10, "bold"),
                     background=COL_INFO, foreground="#ffffff",
                     bordercolor=COL_INFO, focuscolor=COL_INFO)
        st.map("Primary.TButton",
               background=[("pressed", "#0d47a1"), ("active", "#1257a8"), ("disabled", "#b9cfe8")],
               foreground=[("disabled", "#f2f2f2")])

    # ---------------------------------------------------------------- 布局
    def _layout(self) -> None:
        r = self.root
        r.columnconfigure(0, weight=1)
        r.rowconfigure(0, weight=3)   # 功能区（两个分页）
        r.rowconfigure(2, weight=2)   # 日志

        pad = 10
        # NOTE: 窗口顶部不再放应用大标题，标题只保留在标题栏（APP_TITLE）。

        # ---- 分页：删除 / 添加 ------------------------------------------
        self.nb = ttk.Notebook(r)
        self.nb.grid(row=0, column=0, sticky="nsew", padx=pad, pady=(pad, 0))
        del_tab = ttk.Frame(self.nb, padding=2)
        add_tab = ttk.Frame(self.nb, padding=10)
        self.nb.add(del_tab, text="删除子菜单项")
        self.nb.add(add_tab, text="添加应用")
        self._layout_delete_tab(del_tab, pad)
        self._layout_add_tab(add_tab, pad)

        # 日志标题行：左侧标题，右侧「清空日志」按钮
        log_head = ttk.Frame(r)
        log_head.grid(row=1, column=0, sticky="ew", padx=pad, pady=(12, 2))
        log_head.columnconfigure(1, weight=1)
        ttk.Label(log_head, text="日志").grid(row=0, column=0, sticky="w")
        ttk.Button(log_head, text="清空日志", command=self.clear_log).grid(row=0, column=2, sticky="e")

        self.log_box = ScrolledText(
            r, height=10, state="disabled", wrap="word",
            font=("Microsoft YaHei UI", 9), relief="solid", borderwidth=1
        )
        self.log_box.grid(row=2, column=0, sticky="nsew", padx=pad)

        status = ttk.Frame(r)
        status.grid(row=3, column=0, sticky="ew", padx=pad, pady=(6, 0))
        status.columnconfigure(0, weight=1)
        ttk.Label(status, textvariable=self.var_status, style="Status.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(status, text=core.DEFAULT_BACKUP_DIR, style="Status.TLabel").grid(row=0, column=1, sticky="e")

    # ---------------------------------------------------------------- 删除页
    def _layout_delete_tab(self, d: ttk.Frame, pad: int) -> None:
        d.columnconfigure(0, weight=1)
        d.rowconfigure(6, weight=3)   # 三个列表

        ttk.Label(d, text="要删除的子菜单项全称").grid(
            row=0, column=0, sticky="w", padx=pad, pady=(pad, 2)
        )

        entry_row = ttk.Frame(d)
        entry_row.grid(row=1, column=0, sticky="ew", padx=pad)
        entry_row.columnconfigure(0, weight=1)
        self.cmb = ttk.Combobox(entry_row, textvariable=self.var_name, font=("Microsoft YaHei UI", 10))
        self.cmb.grid(row=0, column=0, sticky="ew")
        ttk.Button(entry_row, text="填入选中项", command=self.fill_from_list).grid(
            row=0, column=1, padx=(8, 0)
        )
        ttk.Button(entry_row, text="清除输入", command=self.clear_input).grid(row=0, column=2, padx=(6, 0))

        ttk.Label(d, text=HINT_TEXT, style="Hint.TLabel", wraplength=900, justify="left").grid(
            row=2, column=0, sticky="w", padx=pad, pady=(3, 0)
        )

        opts = ttk.Frame(d)
        opts.grid(row=3, column=0, sticky="w", padx=pad, pady=(8, 0))
        for i, ctx in enumerate(core.CONTEXT_IDS):
            ttk.Checkbutton(opts, text=core.LABEL[ctx].split("（")[0], variable=self.var_ctx[ctx]).grid(
                row=0, column=i, sticky="w", padx=(0, 14)
            )
        ttk.Checkbutton(opts, text="删光后清理空菜单", variable=self.var_prune).grid(
            row=0, column=len(core.CONTEXT_IDS), sticky="w", padx=(6, 0)
        )

        acts = ttk.Frame(d)
        acts.grid(row=4, column=0, sticky="ew", padx=pad, pady=(10, 0))
        acts.columnconfigure(5, weight=1)
        ttk.Button(acts, text="预 览", command=self.preview).grid(row=0, column=0)
        ttk.Button(acts, text="删 除", style="Danger.TButton", command=self.delete).grid(row=0, column=1, padx=8)
        ttk.Button(acts, text="刷 新", command=self.refresh).grid(row=0, column=2)
        ttk.Button(acts, text="重启资源管理器", command=self.restart_explorer).grid(row=0, column=3, padx=8)
        ttk.Button(acts, text="备份目录", command=self.open_backups).grid(row=0, column=4)

        ttk.Label(d, text="当前子菜单项：双击可填入名称)").grid(
            row=5, column=0, sticky="w", padx=pad, pady=(12, 2)
        )

        self.ctx_frame = ttk.Frame(d)
        self.ctx_frame.grid(row=6, column=0, sticky="nsew", padx=pad)
        for i in range(len(core.CONTEXT_IDS)):
            # tkinter 等宽三列的正确写法：每列都要 weight + 相同的 uniform
            self.ctx_frame.columnconfigure(i, weight=1, uniform="ctx")
        self.ctx_frame.rowconfigure(0, weight=1)

        for i, ctx in enumerate(core.CONTEXT_IDS):
            lf = ttk.LabelFrame(self.ctx_frame, text=core.LABEL[ctx], style="GroupTitle.TLabelframe")
            lf.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 4, 0))
            lb = tk.Listbox(lf, borderwidth=0, highlightthickness=0, activestyle="none",
                            selectmode=tk.BROWSE, exportselection=False, font=("Microsoft YaHei UI", 10))
            lb.pack(fill="both", expand=True, padx=4, pady=4)
            self.listboxes[ctx] = lb

    # ---------------------------------------------------------------- 添加页
    def _layout_add_tab(self, a: ttk.Frame, pad: int) -> None:
        a.columnconfigure(1, weight=1)

        ttk.Label(
            a,
            text="把一个新的可执行程序加入「通过IDE打开」的三个位置。\n"
                 "菜单文本自动生成为「通过 （应用名） 打开」，图标取该 exe 自身的图标。",
            style="Hint.TLabel", justify="left", wraplength=880,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        ttk.Label(a, text="程序路径").grid(row=1, column=0, sticky="w", pady=4)
        self.ent_exe = ttk.Entry(a, textvariable=self.var_exe, font=("Microsoft YaHei UI", 10))
        self.ent_exe.grid(row=1, column=1, sticky="ew", padx=8, pady=4)
        ttk.Button(a, text="浏览…", command=self.browse_exe).grid(row=1, column=2, sticky="e", pady=4)

        ttk.Label(a, text="应用名称").grid(row=2, column=0, sticky="w", pady=4)
        self.ent_app = ttk.Entry(a, textvariable=self.var_app, font=("Microsoft YaHei UI", 10))
        self.ent_app.grid(row=2, column=1, sticky="ew", padx=8, pady=4)
        ttk.Button(a, text="从版本信息读取", command=self.use_version_name).grid(
            row=2, column=2, sticky="e", pady=4
        )

        hive_box = ttk.LabelFrame(a, text="写入位置", style="GroupTitle.TLabelframe")
        hive_box.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(10, 4))
        ttk.Radiobutton(hive_box, text="当前用户（HKCU，无需管理员权限）",
                        value="HKCU", variable=self.var_hive).grid(row=0, column=0, sticky="w", padx=10, pady=4)
        ttk.Radiobutton(hive_box, text="所有用户（HKLM，需管理员权限）",
                        value="HKLM", variable=self.var_hive).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 4))

        acts = ttk.Frame(a)
        acts.grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 0))
        ttk.Button(acts, text="添加到三个菜单", style="Primary.TButton", command=self.add_app).grid(row=0, column=0)
        ttk.Button(acts, text="预 览", command=self.preview_add).grid(row=0, column=1, padx=8)
        ttk.Button(acts, text="清 空", command=self.clear_add).grid(row=0, column=2)

        ttk.Label(
            a,
            text="提示：应用名称默认取 exe 的文件名（去掉 .exe）。\n"
                 "若 exe 的版本信息里有更合适的名称，点「从版本信息读取」即可替换。",
            style="Hint.TLabel", justify="left",
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(12, 0))

    # ---------------------------------------------------------------- 事件
    def _bind(self) -> None:
        self.cmb.bind("<Return>", lambda _e: self.delete())
        self.cmb.bind("<KP_Enter>", lambda _e: self.delete())
        for lb in self.listboxes.values():
            lb.bind("<Double-Button-1>", self._on_list_double_click)
            lb.bind("<ButtonRelease-1>", lambda _e: None)

    def _on_list_double_click(self, event: tk.Event) -> str:
        lb = event.widget
        idx = lb.nearest(event.y)
        value = lb.get(idx)
        if value:
            self.var_name.set(value)
            self.log(f"已填入: {value}", COL_OK)
        return "break"

    def fill_from_list(self) -> None:
        # 三个框都允许取值，与「影响哪些上下文」的勾选无关
        for ctx in core.CONTEXT_IDS:
            lb = self.listboxes[ctx]
            sel = lb.curselection()
            if sel:
                value = lb.get(sel[0])
                self.var_name.set(value)
                self.log(f"已填入: {value}", COL_OK)
                return
        messagebox.showinfo("提示", "请先在下方任意列表中选中一项。")

    def clear_input(self) -> None:
        self.var_name.set("")
        self.cmb.focus_set()

    def clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.var_status.set("日志已清空")

    # ---------------------------------------------------------------- 逻辑
    def _contexts(self) -> list[str]:
        """勾选的上下文 —— 只影响删除范围，不影响下方列表显示。"""
        return [c for c in core.CONTEXT_IDS if self.var_ctx[c].get()]

    def log(self, text: str = "", color: str | None = None) -> None:
        """
        追加一条日志：一次调用独占自己的若干行，行尾统一补换行。

        这样多条日志不会挤在同一行，缩进和空行也能稳定对齐。
        """
        box = self.log_box
        box.configure(state="normal")
        tag = "plain"
        if color:
            tag = "c" + color.lstrip("#")
            box.tag_config(tag, foreground=color)
        body = "" if text is None else str(text)
        for line in body.split("\n"):
            box.insert("end", line.rstrip() + "\n", tag)
        box.see("end")
        box.configure(state="disabled")

    def _banner(self, title: str) -> None:
        self.log("")
        self.log(f"===== {title} =====", COL_INFO)

    def _patterns(self) -> list[str]:
        return core.split_names(self.var_name.get())

    def refresh(self, initial: bool = False) -> None:
        # 始终读取全部三个上下文：每个框只显示自己那一份的真实内容
        # （HKCR 合并视图 = HKLM 与 HKCU 的并集），不做交集，
        # 也不因为取消勾选而变空。
        try:
            items = core.get_items(core.CONTEXT_IDS)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("错误", f"读取注册表失败:\n{exc}")
            return

        total = 0
        self._labels = {c: [] for c in core.CONTEXT_IDS}
        for ctx in core.CONTEXT_IDS:
            lb = self.listboxes[ctx]
            lb.delete(0, tk.END)
            rows = [i for i in items if i.context == ctx]
            for i in rows:
                text = i.label or i.name
                lb.insert(tk.END, text)
                self._labels[ctx].append(text)
            total += len(rows)

        # 下拉历史用全称，和输入框的匹配规则保持一致
        for text in sorted({i.label or i.name for i in items}):
            if text not in self._history:
                self._history.append(text)
        self.cmb.configure(values=self._history)

        self.var_status.set(f"已加载 {total} 个子菜单项（{len(core.CONTEXT_IDS)} 个上下文）")
        if initial:
            self._banner("就绪")
            self.log(HINT_TEXT, COL_MUTED)
            for ctx in core.CONTEXT_IDS:
                n = len(self._labels[ctx])
                self.log(f"  {core.LABEL[ctx]} : {n} 项", COL_MUTED)
            for v in core.parent_verbs():
                state = "OK" if v.wired else "!! 未接线"
                self.log(f"  {core.LABEL_ASCII[v.context]} -> {v.target or '<无>'}  [{state}]")
            self.log("  列表内容为 HKCR 合并视图：HKLM 与 HKCU 的子项并集。", COL_MUTED)

    def _suggest(self) -> str:
        """没命中时，提示可用的完整名称（去重）。"""
        seen: list[str] = []
        for ctx in core.CONTEXT_IDS:
            for t in self._labels[ctx]:
                if t not in seen:
                    seen.append(t)
        return "\n".join(f"  · {t}" for t in seen) if seen else "（当前没有任何子菜单项）"

    def _plan(self, ctxs: Sequence[str]):
        return core.select_matches(self._patterns(), ctxs)

    def preview(self) -> None:
        self._banner("预演")
        if not self._patterns():
            self.log("请输入要预览的名称。", COL_WARN)
            return
        ctxs = self._contexts() or list(core.CONTEXT_IDS)
        try:
            plan = self._plan(ctxs)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("错误", str(exc))
            return
        for ctx in ctxs:
            rows = [m.display for m in plan if m.context == ctx]
            if rows:
                self.log(f"  [命中] {core.LABEL_ASCII[ctx]}", COL_OK)
                for t in rows:
                    self.log(f"      - {t}", COL_OK)
            else:
                self.log(f"  [跳过] {core.LABEL_ASCII[ctx]} : 无此项", COL_WARN)
        if not plan:
            self.log("可用名称：", COL_WARN)
            self.log(self._suggest(), COL_WARN)
        self.log(f"合计 {len(plan)} 处（尚未做任何修改）", COL_INFO)

    def delete(self) -> None:
        patterns = self._patterns()
        if not patterns:
            messagebox.showwarning(
                "缺少输入",
                "请先在上方输入框填写要删除的子菜单项全称，\n例如「通过 Code 打开」。",
            )
            return

        ctxs = self._contexts() or list(core.CONTEXT_IDS)
        try:
            plan = self._plan(ctxs)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("错误", str(exc))
            return

        self._banner("删除")
        if not plan:
            self.log("任何上下文都没有匹配项，未做任何修改。", COL_WARN)
            messagebox.showinfo(
                "没有匹配项",
                "没有找到匹配的子菜单项。\n\n必须输入完整名称，当前可用：\n" + self._suggest(),
            )
            return

        lines = ["即将删除以下子菜单项：", ""]
        for ctx in ctxs:
            rows = [m for m in plan if m.context == ctx]
            if rows:
                lines.append(f"  {core.LABEL[ctx]}")
                for m in rows:
                    where = "+".join(m.hives) or "HKCU"
                    lines.append(f"      - {m.display}    [{where}]")
        if self.var_prune.get():
            lines += ["", "并会删除因此变空的父菜单项。"]
        lines += ["", "删除前会自动导出 .reg 备份。", "确定继续吗？"]
        if not messagebox.askyesno("确认删除", "\n".join(lines), default="no"):
            self.log("已取消。", COL_MUTED)
            return

        try:
            log = core.remove_items(plan, ctxs, prune_empty=self.var_prune.get(), backup=True)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("删除失败", str(exc))
            return

        denied = 0
        for line in log:
            if line.startswith("REMOVED"):
                color = COL_OK
            elif line.startswith("BACKUP"):
                color = COL_MUTED
            elif line.startswith("NEEDADMIN"):
                color = COL_WARN
                denied += 1
            else:
                color = COL_WARN
            self.log(f"  {line}", color)

        self.refresh()
        # NOTE: 删除后不再自动重启资源管理器；需要时点「重启资源管理器」按钮。
        self.log("完成。菜单将在重启资源管理器后更新。", COL_INFO)
        if denied:
            messagebox.showwarning(
                "部分项目需要管理员权限",
                f"有 {denied} 处位于 HKLM，普通权限无法删除。\n\n"
                "请以管理员身份运行本程序后再试，\n"
                "或手动删除 HKLM\\Software\\Classes 下的对应子项。",
            )

    def restart_explorer(self, ask: bool = True) -> None:
        if ask and not messagebox.askyesno("重启资源管理器", "所有已打开的文件夹窗口会被关闭，确定继续？"):
            return
        try:
            core.restart_explorer()
            self.log("已重启资源管理器。", COL_OK)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("失败", str(exc))

    def open_backups(self) -> None:
        try:
            p = core.open_backup_dir()
            self.log(f"已打开备份目录: {p}", COL_MUTED)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("失败", str(exc))

    # ---------------------------------------------------------------- 添加页
    def _app_name(self) -> str:
        """当前填写（或可自动推断）的应用名。"""
        name = self.var_app.get().strip()
        if name:
            return name
        path = self.var_exe.get().strip()
        return core.app_name_from_path(path) if path else ""

    def _resolved_exe(self) -> str:
        path = self.var_exe.get().strip().strip('"')
        return os.path.abspath(os.path.expandvars(path)) if path else ""

    def browse_exe(self) -> None:
        path = filedialog.askopenfilename(
            title="选择要加入「通过IDE打开」的程序",
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")],
        )
        if not path:
            return
        self.var_exe.set(path)
        self.var_app.set(core.app_name_from_path(path))
        self.log(f"已选择: {path}", COL_MUTED)
        self.log(f"应用名称: {core.make_label(self._app_name())}", COL_MUTED)

    def use_version_name(self) -> None:
        path = self._resolved_exe()
        if not path:
            messagebox.showwarning("缺少路径", "请先浏览或填写 exe 的完整路径。")
            return
        name = core.app_name_from_version_info(path)
        if not name:
            messagebox.showinfo("没有版本信息", "该文件没有可用的版本信息（ProductName/FileDescription）。")
            return
        self.var_app.set(name)
        self.log(f"已从版本信息读取应用名: {name}", COL_MUTED)
        self.log(f"菜单文本将变为: {core.make_label(name)}", COL_MUTED)

    def clear_add(self) -> None:
        self.var_exe.set("")
        self.var_app.set("")
        self.ent_exe.focus_set()

    def preview_add(self) -> None:
        self._banner("添加 · 预演")
        path = self._resolved_exe()
        if not path:
            self.log("请先浏览或填写 exe 的完整路径。", COL_WARN)
            return
        name = self._app_name()
        label = core.make_label(name)
        self.log(f"程序路径 : {path}", COL_MUTED)
        self.log(f"应用名称 : {name}", COL_MUTED)
        self.log(f"菜单文本 : {label}", COL_OK)
        self.log(f"图标来源 : {core.exe_icon_path(path)}", COL_MUTED)
        for ctx in core.CONTEXT_IDS:
            self.log(f"  → {core.LABEL[ctx]}：{path} {core.PLACEHOLDER[ctx]}", COL_INFO)
        self.log(f"写入位置 : {self.var_hive.get()}   （尚未做任何修改）", COL_INFO)

    def add_app(self) -> None:
        path = self._resolved_exe()
        if not path:
            messagebox.showwarning("缺少路径", "请先浏览或填写 exe 的完整路径。")
            return
        name = self._app_name()
        if not name:
            messagebox.showwarning("缺少应用名称", "无法从该文件名推断应用名称，请手动填写。")
            return

        label = core.make_label(name)
        hive = self.var_hive.get()
        lines = [
            "即将把下面的程序加入「通过IDE打开」的三个位置：",
            "",
            f"  程序路径 : {path}",
            f"  菜单文本 : {label}",
            f"  图标     : {core.exe_icon_path(path)}",
            f"  写入位置 : {hive}",
            "",
        ]
        for ctx in core.CONTEXT_IDS:
            lines.append(f"  · {core.LABEL[ctx]}  →  {path} {core.PLACEHOLDER[ctx]}")
        lines += ["", "写入前会自动导出 .reg 备份。", "确定继续吗？"]
        if not messagebox.askyesno("确认添加", "\n".join(lines), default="no"):
            self._banner("添加")
            self.log("已取消。", COL_MUTED)
            return

        self._banner("添加")
        try:
            log = core.add_items(path, name, core.CONTEXT_IDS, hive, backup=True)
        except ValueError as exc:
            messagebox.showerror("无法添加", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("添加失败", str(exc))
            return

        for line in log:
            color = COL_OK if line.startswith("ADDED") else (
                COL_MUTED if line.startswith("BACKUP") else COL_WARN)
            self.log(f"  {line}", color)

        need_admin = [x for x in log if x.startswith("NEEDADMIN")]
        if need_admin:
            messagebox.showwarning(
                "需要管理员权限",
                "以下位置写入失败，因为 HKLM 需要管理员权限：\n\n"
                + "\n".join(need_admin)
                + "\n\n请以管理员身份重新运行本程序后重试。",
            )

        self.refresh()
        self.log("完成。菜单将在重启资源管理器后更新。", COL_INFO)


def _center(root: tk.Tk, width: int, height: int) -> None:
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w = min(width, sw - 40)
    h = min(height, sh - 80)
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 2)}")
    root.minsize(760, 540)


def main(argv: Sequence[str] | None = None) -> int:
    root = tk.Tk()
    _center(root, 960, 760)
    app = App(root)

    def handler(exc_type, exc, tb) -> None:  # noqa: ANN001
        messagebox.showerror("未处理的异常", f"{exc_type.__name__}: {exc}")
        traceback.print_exception(exc_type, exc, tb, file=sys.stderr)

    root.report_callback_exception = handler

    if argv and "--self-test" in argv:
        return self_test(root, app)
    root.mainloop()
    return 0


def self_test(root: tk.Tk, app: App) -> int:
    """不进入消息循环，构建界面并把几何/状态信息打印到 stdout。"""
    for _ in range(3):
        root.update_idletasks()
        root.update()

    print(f"title      : {root.title()}")
    print(f"theme      : {ttk.Style().theme_use()}")
    print(f"form       : {root.winfo_width()} x {root.winfo_height()} "
          f"at ({root.winfo_x()},{root.winfo_y()})")
    print(f"requested  : {root.winfo_reqwidth()} x {root.winfo_reqheight()}")
    print(f"screen     : {root.winfo_screenwidth()} x {root.winfo_screenheight()}")

    items = core.get_items(core.CONTEXT_IDS)
    total = len(items)
    ox = root.winfo_rootx()
    for ctx in core.CONTEXT_IDS:
        lb = app.listboxes[ctx]
        print(f"  {core.LABEL_ASCII[ctx]:<34} x={lb.winfo_rootx() - ox:<4} "
              f"w={lb.winfo_width():<4} h={lb.winfo_height():<4} items={lb.size():<3} "
              f"[{core.LABEL[ctx]}]")
        for i in range(lb.size()):
            print(f"        {core.escape_non_ascii(lb.get(i))}")

    print(f"combobox   : {app.cmb.winfo_width()} x {app.cmb.winfo_height()} "
          f"values={[core.escape_non_ascii(v) for v in app.cmb.cget('values')]}")

    # 匹配规则自检：全称命中、应用名不命中、通配符命中（期望值由注册表实况推导）
    all_labels = [i.label for i in items if i.label]
    first = all_labels[0] if all_labels else ""
    subkey_names = {i.name for i in items}
    probes = [(first or "?", None), (sorted(subkey_names)[0] if subkey_names else "?", 0),
              ("\u901a\u8fc7 * \u6253\u5f00", total)]
    for pats, expect in probes:
        try:
            n = len(core.select_matches([pats], core.CONTEXT_IDS))
        except Exception as exc:  # noqa: BLE001
            n = f"ERR {exc}"
        if expect is None:      # 该全称出现在几个上下文里
            expect = len({i.context for i in items if i.label == pats})
        ok = "OK " if n == expect else "BAD"
        print(f"match {ok}  {[core.escape_non_ascii(pats)]} -> {n} (expect {expect})")

    tabs = [app.nb.tab(i, "text") for i in range(app.nb.index("end"))]
    print(f"tabs       : {tabs}  (current={app.nb.tab(app.nb.select(), 'text')})")
    print(f"add exe's  : {app.ent_exe.winfo_width()} x {app.ent_exe.winfo_height()}")
    print(f"add app's  : {app.ent_app.winfo_width()} x {app.ent_app.winfo_height()}")
    print(f"add hive   : {app.var_hive.get()}")

    print(f"status     : {app.var_status.get()}")
    print("checkboxes : "
          + " ".join(f"{c}={app.var_ctx[c].get()}" for c in core.CONTEXT_IDS)
          + f" Prune={app.var_prune.get()}")
    log_text = app.log_box.get("1.0", "end-1c")
    print(f"log length : {len(log_text)}")
    for line in log_text.splitlines():
        print(f"        {core.escape_non_ascii(line)}")
    print("SELF-TEST-OK")
    root.destroy()
    return 0