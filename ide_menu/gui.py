"""图形界面（tkinter）：通过IDE打开·右键菜单项管理。"""

from __future__ import annotations

import sys
import tkinter as tk
import traceback
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Sequence

from . import core

#: 应用名称，同时用作窗口标题。
APP_TITLE = "通过IDE打开·右键菜单项管理（阿懂）"

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
        st.configure("Title.TLabel", font=("Microsoft YaHei UI", 15, "bold"))
        st.configure("Hint.TLabel", foreground=COL_MUTED, font=("Microsoft YaHei UI", 9))
        st.configure("GroupTitle.TLabelframe.Label", font=("Microsoft YaHei UI", 10, "bold"))
        st.configure("Status.TLabel", foreground=COL_MUTED, font=("Microsoft YaHei UI", 9))
        st.configure("Danger.TButton", font=("Microsoft YaHei UI", 10, "bold"),
                     background=COL_ACCENT, foreground="#ffffff",
                     bordercolor=COL_ACCENT, focuscolor=COL_ACCENT)
        st.map("Danger.TButton",
               background=[("pressed", "#8d1b1b"), ("active", "#a51f1f"), ("disabled", "#e0b4b4")],
               foreground=[("disabled", "#f2f2f2")])

    # ---------------------------------------------------------------- 布局
    def _layout(self) -> None:
        r = self.root
        r.columnconfigure(0, weight=1)
        r.rowconfigure(7, weight=3)   # 三个列表
        r.rowconfigure(9, weight=2)   # 日志

        pad = 10
        ttk.Label(r, text=APP_TITLE, style="Title.TLabel").grid(
            row=0, column=0, sticky="w", padx=pad, pady=(pad, 2)
        )

        ttk.Label(r, text="要删除的子菜单项全称").grid(row=1, column=0, sticky="w", padx=pad, pady=(8, 2))

        entry_row = ttk.Frame(r)
        entry_row.grid(row=2, column=0, sticky="ew", padx=pad)
        entry_row.columnconfigure(0, weight=1)
        self.cmb = ttk.Combobox(entry_row, textvariable=self.var_name, font=("Microsoft YaHei UI", 10))
        self.cmb.grid(row=0, column=0, sticky="ew")
        ttk.Button(entry_row, text="填入选中项", command=self.fill_from_list).grid(
            row=0, column=1, padx=(8, 0)
        )
        ttk.Button(entry_row, text="清除输入", command=self.clear_input).grid(row=0, column=2, padx=(6, 0))

        ttk.Label(r, text=HINT_TEXT, style="Hint.TLabel", wraplength=900, justify="left").grid(
            row=3, column=0, sticky="w", padx=pad, pady=(3, 0)
        )

        opts = ttk.Frame(r)
        opts.grid(row=4, column=0, sticky="w", padx=pad, pady=(8, 0))
        for i, ctx in enumerate(core.CONTEXT_IDS):
            ttk.Checkbutton(opts, text=core.LABEL[ctx].split("（")[0], variable=self.var_ctx[ctx]).grid(
                row=0, column=i, sticky="w", padx=(0, 14)
            )
        ttk.Checkbutton(opts, text="删光后清理空菜单", variable=self.var_prune).grid(
            row=0, column=len(core.CONTEXT_IDS), sticky="w", padx=(6, 0)
        )

        acts = ttk.Frame(r)
        acts.grid(row=5, column=0, sticky="ew", padx=pad, pady=(10, 0))
        acts.columnconfigure(5, weight=1)
        ttk.Button(acts, text="预 览", command=self.preview).grid(row=0, column=0)
        ttk.Button(acts, text="删 除", style="Danger.TButton", command=self.delete).grid(row=0, column=1, padx=8)
        ttk.Button(acts, text="刷 新", command=self.refresh).grid(row=0, column=2)
        ttk.Button(acts, text="重启资源管理器", command=self.restart_explorer).grid(row=0, column=3, padx=8)
        ttk.Button(acts, text="备份目录", command=self.open_backups).grid(row=0, column=4)

        ttk.Label(r, text="当前子菜单项（各上下文实际内容，不做交集；双击可填入名称）").grid(
            row=6, column=0, sticky="w", padx=pad, pady=(12, 2)
        )

        self.ctx_frame = ttk.Frame(r)
        self.ctx_frame.grid(row=7, column=0, sticky="nsew", padx=pad)
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

        # 日志标题行：左侧标题，右侧「清空日志」按钮
        log_head = ttk.Frame(r)
        log_head.grid(row=8, column=0, sticky="ew", padx=pad, pady=(12, 2))
        log_head.columnconfigure(1, weight=1)
        ttk.Label(log_head, text="日志").grid(row=0, column=0, sticky="w")
        ttk.Button(log_head, text="清空日志", command=self.clear_log).grid(row=0, column=2, sticky="e")

        self.log_box = ScrolledText(
            r, height=9, state="disabled", wrap="word", font=("Consolas", 9), relief="solid", borderwidth=1
        )
        self.log_box.grid(row=9, column=0, sticky="nsew", padx=pad)

        status = ttk.Frame(r)
        status.grid(row=11, column=0, sticky="ew", padx=pad, pady=(6, 0))
        status.columnconfigure(0, weight=1)
        ttk.Label(status, textvariable=self.var_status, style="Status.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(status, text=core.DEFAULT_BACKUP_DIR, style="Status.TLabel").grid(row=0, column=1, sticky="e")

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

    def log(self, text: str, color: str | None = None) -> None:
        self.log_box.configure(state="normal")
        if color:
            self.log_box.tag_add("color", "end", "end")
            self.log_box.tag_config("color", foreground=color)
            self.log_box.insert("end", text, "color")
        else:
            self.log_box.insert("end", text)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _banner(self, title: str) -> None:
        self.log("")
        self.log(f"===== {title} =====", COL_INFO)

    def _patterns(self) -> list[str]:
        return core.split_names(self.var_name.get())

    def refresh(self, initial: bool = False) -> None:
        # 始终读取全部三个上下文：每个框只显示自己那一份的真实内容，
        # 不做交集，也不因为取消勾选而变空。
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
                self.log(f"  {core.LABEL[ctx]}：{len(self._labels[ctx])} 项", COL_MUTED)
            for v in core.parent_verbs():
                state = "OK" if v.wired else "!! 未接线"
                self.log(f"  {core.LABEL_ASCII[v.context]} -> {v.target or '<无>'}  [{state}]")

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
                self.log(f"  [命中] {core.LABEL_ASCII[ctx]} : {', '.join(rows)}", COL_OK)
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
            rows = [m.display for m in plan if m.context == ctx]
            if rows:
                lines.append(f"  {core.LABEL[ctx]}")
                lines.extend(f"      - {t}" for t in rows)
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

        for line in log:
            color = COL_OK if line.startswith("REMOVED") else (COL_MUTED if line.startswith("BACKUP") else COL_WARN)
            self.log(f"  {line}", color)

        self.refresh()
        if messagebox.askyesno("立即生效", "是否现在重启资源管理器（explorer.exe）使菜单更新？\n所有已打开的文件夹窗口会关闭。"):
            self.restart_explorer(ask=False)

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

    # 匹配规则自检：全称命中、应用名不命中、通配符命中
    probe = [
        (["通过 Code 打开"], 3),
        (["Code"], 0),
        (["通过 * 打开"], 3 * 4),
    ]
    for pats, expect in probe:
        try:
            n = len(core.select_matches(pats, core.CONTEXT_IDS))
        except Exception as exc:  # noqa: BLE001
            n = f"ERR {exc}"
        ok = "OK " if n == expect else "BAD"
        print(f"match {ok}  {[core.escape_non_ascii(p) for p in pats]} -> {n} (expect {expect})")

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