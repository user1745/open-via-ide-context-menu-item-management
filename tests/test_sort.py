"""排序（按应用名首字母）的测试。

全部为纯函数测试 + 只读的实时注册表断言，不会写入注册表。
"""

from __future__ import annotations

import unittest

from ide_menu import core


def _item(context: str, name: str, label: str | None = None) -> core.MenuItem:
    return core.MenuItem(
        context=context,
        name=name,
        label=label if label is not None else core.make_label(name),
        command=None,
        icon=None,
    )


class TestAppNameOf(unittest.TestCase):
    """从菜单项文本里还原应用名。"""

    def test_strips_prefix_and_suffix(self):
        self.assertEqual(core.app_name_of("通过 Code 打开"), "Code")

    def test_name_with_spaces(self):
        self.assertEqual(core.app_name_of("通过 TRAE CN 打开"), "TRAE CN")

    def test_collapses_whitespace(self):
        self.assertEqual(core.app_name_of("通过  微信  编辑器 打开"), "微信 编辑器")

    def test_empty_uses_fallback(self):
        self.assertEqual(core.app_name_of("", "Code"), "Code")
        self.assertEqual(core.app_name_of("随便什么文本"), "随便什么文本")

    def test_round_trip_with_make_label(self):
        # make_label 会顺手清掉多余空格，所以往返比较要拿清理后的名字
        for raw, expected in (("Code", "Code"), ("TRAE CN", "TRAE CN"),
                              ("GitHub Copilot", "GitHub Copilot"),
                              ("  VS  Code  ", "VS Code")):
            self.assertEqual(core.app_name_of(core.make_label(raw)), expected)


class TestCompareNames(unittest.TestCase):
    def test_equal(self):
        self.assertEqual(core.compare_names("Code", "Code"), 0)

    def test_case_insensitive_first_letter(self):
        # 无论最终落到 NLS 还是 casefold 兜底，都必须是「小写在前」
        self.assertLess(core.compare_names("Code", "cursor"), 0)

    def test_ordering_is_consistent(self):
        a, b = "apple", "Bad"
        self.assertLess(core.compare_names(a, b), 0)
        self.assertGreater(core.compare_names(b, a), 0)


class TestSortItems(unittest.TestCase):
    """排序后每个上下文各自独立有序。"""

    def test_sorts_by_app_name_not_subkey(self):
        # 子键名与菜单项名称故意错位（真实注册表里 HKLM 就有这种脏数据）
        items = [
            _item("File", "zzz", "通过 apple 打开"),
            _item("File", "aaa", "通过 Bad 打开"),
            _item("File", "mmm", "通过 Code 打开"),
            _item("File", "bbb", "通过 ANT 打开"),
        ]
        got = [i.app_name for i in core.sort_items(items)]
        self.assertEqual(got, ["ANT", "apple", "Bad", "Code"])

    def test_each_context_sorted_independently(self):
        items = [
            _item("File", "b", "通过 Zulu 打开"),
            _item("File", "a", "通过 Alpha 打开"),
            _item("Bg", "c", "通过 Yankee 打开"),
            _item("Bg", "d", "通过 Bravo 打开"),
        ]
        out = core.sort_items(items)
        by_ctx: dict[str, list[str]] = {}
        for i in out:
            by_ctx.setdefault(i.context, []).append(i.app_name)
        self.assertEqual(by_ctx["File"], ["Alpha", "Zulu"])
        self.assertEqual(by_ctx["Bg"], ["Bravo", "Yankee"])

    def test_is_stable_and_non_destructive(self):
        items = [_item("File", "x", "通过 B 打开"), _item("File", "y", "通过 A 打开")]
        out = core.sort_items(items)
        self.assertEqual(len(out), len(items))
        self.assertEqual({id(i) for i in out}, {id(i) for i in items})

    def test_empty_and_single(self):
        self.assertEqual(core.sort_items([]), [])
        one = [_item("File", "a", "通过 A 打开")]
        self.assertEqual([i.app_name for i in core.sort_items(one)], ["A"])

    def test_falls_back_to_subkey_when_no_label(self):
        items = [_item("File", "zebra"), _item("File", "alpha")]
        self.assertEqual([i.app_name for i in core.sort_items(items)], ["alpha", "zebra"])


class TestLiveSorted(unittest.TestCase):
    """只读断言：真实注册表里每个上下文都是排好序的。"""

    @classmethod
    def setUpClass(cls):
        cls.items = core.get_items(core.CONTEXT_IDS)

    def test_returns_something_or_empty_but_never_raises(self):
        self.assertIsInstance(self.items, list)

    def test_every_context_is_monotonic(self):
        by_ctx: dict[str, list[core.MenuItem]] = {}
        for i in self.items:
            by_ctx.setdefault(i.context, []).append(i)
        for ctx, rows in by_ctx.items():
            names = [i.app_name for i in rows]
            with self.subTest(context=ctx):
                self.assertEqual(len(names), len(set(names)), "同一上下文内不应有重名")
                for a, b in zip(names, names[1:]):
                    self.assertLessEqual(core.compare_names(a, b), 0, f"{a!r} 应排在 {b!r} 之前")

    def test_app_name_matches_label_shape(self):
        for i in self.items:
            with self.subTest(name=i.name):
                self.assertEqual(i.app_name, core.app_name_of(i.label, i.name))


if __name__ == "__main__":
    unittest.main()
