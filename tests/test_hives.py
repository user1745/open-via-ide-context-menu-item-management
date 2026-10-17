"""HKCR 合并视图（HKLM + HKCU 并集）的只读验证。

只读取注册表，不做任何修改。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ide_menu import core  # noqa: E402


class TestMergedView(unittest.TestCase):
    """core.get_items() 必须返回 HKCR 合并视图，而不是只看 HKCU。"""

    @classmethod
    def setUpClass(cls):
        cls.items = core.get_items(core.CONTEXT_IDS)

    def test_every_item_declares_its_hives(self):
        for it in self.items:
            with self.subTest(item=it.name, ctx=it.context):
                self.assertTrue(it.hives, f"{it.context}/{it.name} 没有记录 hives")
                for h in it.hives:
                    self.assertIn(h, core.HIVES)

    def test_contexts_are_not_lost(self):
        for ctx in core.CONTEXT_IDS:
            rows = [i for i in self.items if i.context == ctx]
            with self.subTest(ctx=ctx):
                self.assertTrue(rows, f"{ctx} 没有读到任何子菜单项")

    def test_names_unique_per_context(self):
        seen: set[tuple[str, str]] = set()
        for it in self.items:
            key = (it.context, it.name)
            with self.subTest(item=key):
                self.assertNotIn(key, seen, f"{key} 重复出现（合并时未去重）")
                seen.add(key)

    def test_merged_is_at_least_as_large_as_hkcu_only(self):
        """合并视图不得少于任何单个配置单元的条目数。"""
        for ctx in core.CONTEXT_IDS:
            merged = {i.name for i in self.items if i.context == ctx}
            for h in core.HIVES:
                per_hive = set(core._leaf_names_by_hive(ctx).get(h, []))
                with self.subTest(ctx=ctx, hive=h):
                    self.assertTrue(
                        merged >= per_hive,
                        f"{ctx} 合并视图缺少 {h} 中的 {per_hive - merged}",
                    )

    def test_both_hives_contribute_on_this_machine(self):
        """
        本机 HKLM 里有 Antigravity / ChatGPT / CLion，只读 HKCU 是看不到的。
        这条测试正是为了防止回归到「只读 HKCU」。
        """
        hklm_only = set()
        for ctx in core.CONTEXT_IDS:
            merged = {i.name for i in self.items if i.context == ctx}
            hklm = set(core._leaf_names_by_hive(ctx).get("HKLM", []))
            hkcu = set(core._leaf_names_by_hive(ctx).get("HKCU", []))
            hklm_only |= (hklm - hkcu) & merged
        self.assertTrue(
            hklm_only,
            "期望存在仅存在于 HKLM 的子菜单项；若机器上确实没有，可忽略此失败。",
        )

    def test_parent_verbs_are_wired(self):
        targets = {v.context: v.target for v in core.parent_verbs()}
        for ctx in core.CONTEXT_IDS:
            with self.subTest(ctx=ctx):
                self.assertEqual(targets.get(ctx), core.LEAF[ctx])


class TestMatchCarriesHives(unittest.TestCase):
    """匹配结果必须带 hives，删除时才知道要动哪些配置单元。"""

    @classmethod
    def setUpClass(cls):
        cls.items = core.get_items(core.CONTEXT_IDS)

    def test_every_match_has_hives(self):
        labels = [i.label for i in self.items if i.label]
        if not labels:
            self.skipTest("注册表里没有子菜单项")
        for label in labels:
            for m in core.select_matches([label]):
                with self.subTest(label=label):
                    self.assertTrue(m.hives)

    def test_match_display_prefers_label(self):
        m = core.Match("File", "Code", "\u901a\u8fc7 Code \u6253\u5f00", ("HKCU",))
        self.assertEqual(m.display, "\u901a\u8fc7 Code \u6253\u5f00")
        self.assertEqual(core.Match("File", "Code").display, "Code")


if __name__ == "__main__":
    unittest.main()