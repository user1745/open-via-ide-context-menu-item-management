"""命令行界面：``ide-menu``。"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from . import __version__
from . import core

EXIT_OK = 0
EXIT_NO_MATCH = 1
EXIT_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ide-menu",
        description=(
            "管理级联右键菜单「通过 IDE 打开」的子菜单项。"
            "一次操作同时作用于文件 / 文件夹 / 目录背景三处；"
            "某处没有该项时自动跳过。"
        ),
        epilog=(
            "示例:\n"
            "  ide-menu --list\n"
            "  ide-menu -n Code --dry-run\n"
            "  ide-menu -n Code Cursor TRAE* -y\n"
            "  ide-menu -n 'TRAE CN' -m          # 按显示文本匹配\n"
            "  ide-menu -n OpenCode -p --restart # 删除后顺便清空菜单并重启资源管理器\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"ide-menu {__version__}")
    p.add_argument("-l", "--list", action="store_true", dest="do_list", help="列出三处当前的子菜单项")
    p.add_argument(
        "-n",
        "--name",
        nargs="+",
        metavar="NAME",
        help="要删除的子菜单项名称，支持 * ? 通配符，可给多个",
    )
    p.add_argument(
        "-c",
        "--context",
        choices=["All", *core.CONTEXT_IDS],
        default="All",
        help="限定操作的上下文，默认 All",
    )
    p.add_argument("-m", "--match-verb-text", action="store_true", help="同时按显示文本(MUIVerb)匹配")
    p.add_argument("-p", "--prune-empty", action="store_true", help="某处删空后一并删除空的父菜单")
    p.add_argument("-b", "--no-backup", action="store_true", help="删除前不导出 .reg 备份（不推荐）")
    p.add_argument("-B", "--backup-dir", metavar="DIR", help="备份输出目录")
    p.add_argument("--dry-run", action="store_true", help="只预览，不做任何修改")
    p.add_argument("-y", "--yes", action="store_true", help="不再询问确认")
    p.add_argument("--restart", action="store_true", help="删除后重启资源管理器使菜单生效")
    p.add_argument("--open-backups", action="store_true", help="用文件管理器打开备份目录")
    p.add_argument("--json", action="store_true", help="以 JSON 输出，便于脚本处理")
    return p


def _contexts(arg: str) -> Sequence[str]:
    return core.CONTEXT_IDS if arg == "All" else (arg,)


def _print_state(ctxs: Sequence[str], as_json: bool) -> None:
    items = core.get_items(ctxs)
    verbs = {v.context: v for v in core.parent_verbs(ctxs)}

    if as_json:
        print(
            json.dumps(
                {
                    "parents": [
                        {
                            "context": v.context,
                            "label": core.LABEL[v.context],
                            "menu_text": v.menu_text,
                            "extended_sub_commands_key": v.target,
                            "wired": v.wired,
                        }
                        for v in verbs.values()
                    ],
                    "items": [
                        {
                            "context": i.context,
                            "name": i.name,
                            "label": i.label,
                            "command": i.command,
                        }
                        for i in items
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    for ctx in ctxs:
        v = verbs.get(ctx)
        head = core.LABEL_ASCII[ctx]
        if v is None:
            print(f"{head} : <父菜单不存在>")
        else:
            flag = "" if v.wired else "  [!! ExtendedSubCommandsKey 为空]"
            print(f"{head} -> {v.target or '<无>'}{flag}")
        rows = [i for i in items if i.context == ctx]
        if not rows:
            print("    <无子菜单项>")
            continue
        for i in rows:
            print(f"    {i.name:<20} {i.label_escaped}")
        print()


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ctxs = _contexts(args.context)
    backup_dir = args.backup_dir or core.default_backup_dir()

    if args.open_backups:
        print(f"备份目录: {core.open_backup_dir(backup_dir)}")
        return EXIT_OK

    try:
        if args.do_list or not args.name:
            if args.do_list:
                _print_state(ctxs, args.json)
                return EXIT_OK
            build_parser().print_help()
            return EXIT_OK

        patterns = core.split_names(" ".join(args.name))
        if not patterns:
            print("没有解析出有效的名称。", file=sys.stderr)
            return EXIT_NO_MATCH

        plan = core.select_matches(patterns, ctxs, match_verb_text=args.match_verb_text)

        if not args.json:
            print(f"目标: {', '.join(patterns)}")
            print(f"上下文: {', '.join(ctxs)}\n")
            print("匹配结果")
            print("-" * 46)
            for ctx in ctxs:
                names = [m.name for m in plan if m.context == ctx]
                if names:
                    print(f"  {core.LABEL_ASCII[ctx]} : 将删除 {len(names)} -> {', '.join(names)}")
                else:
                    print(f"  {core.LABEL_ASCII[ctx]} : 不存在，跳过")
            print()

        if not plan:
            if args.json:
                print(json.dumps({"removed": [], "planned": []}, ensure_ascii=False))
            else:
                print("任何上下文都没有匹配项，未做任何修改。")
            return EXIT_NO_MATCH

        if args.json:
            print(
                json.dumps(
                    {
                        "planned": [{"context": m.context, "name": m.name} for m in plan],
                        "removed": [],
                    },
                    ensure_ascii=False,
                )
            )
            return EXIT_OK

        if args.dry_run:
            print("预演模式（--dry-run）：未做任何修改。")
            return EXIT_OK

        if not args.yes:
            total = len(plan)
            ans = input(f"确认删除 {total} 个子菜单项？输入 y 继续: ").strip().lower()
            if ans not in ("y", "yes"):
                print("已取消。")
                return EXIT_OK

        log = core.remove_items(
            plan,
            ctxs,
            prune_empty=args.prune_empty,
            backup=not args.no_backup,
            backup_dir=backup_dir,
        )
        print("执行结果")
        print("-" * 46)
        for line in log:
            print(f"  {line}")

        if args.restart:
            print("\n正在重启资源管理器 ...")
            core.restart_explorer()

        print("\n完成。重启 explorer.exe（或注销重登）后菜单才会更新。")
        return EXIT_OK

    except Exception as exc:  # noqa: BLE001 - CLI 顶层兜底
        print(f"错误: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())