"""核心逻辑测试。

只做**只读**验证 + 纯函数单测，不会删除任何真实的菜单项。

运行:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ide_menu import core  # noqa: E402


class TestSplitNames(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(core.split_names(""), [])
        self.assertEqual(core.split_names("   "), [])

    def test_single(self):
        self.assertEqual(core.split_names("Code"), ["Code"])

    def test_separators(self):
        for text in ("Code,Cursor", "Code;Cursor", "Code|Cursor", "Code, Cursor", "Code，Cursor", "Code；Cursor", "Code、Cursor"):
            with self.subTest(text=text):
                self.assertEqual(core.split_names(text), ["Code", "Cursor"])

    def test_space_is_not_a_separator(self):
        # 子键名本身可能含空格（如 "TRAE SOLO CN"）
        self.assertEqual(core.split_names("TRAE SOLO CN"), ["TRAE SOLO CN"])

    def test_strips_quotes(self):
        self.assertEqual(core.split_names('"TRAE SOLO CN"'), ["TRAE SOLO CN"])

    def test_mixed(self):
        self.assertEqual(core.split_names(' Code , "TRAE SOLO CN" ,Cursor '), ["Code", "TRAE SOLO CN", "Cursor"])


class TestEscape(unittest.TestCase):
    def test_ascii_untouched(self):
        self.assertEqual(core.escape_non_ascii("Code"), "Code")

    def test_cjk_escaped(self):
        self.assertEqual(core.escape_non_ascii("通过"), r"\u901A\u8FC7")

    def test_empty(self):
        self.assertEqual(core.escape_non_ascii(""), "")


class TestConstants(unittest.TestCase):
    def test_three_contexts(self):
        self.assertEqual(core.CONTEXT_IDS, ("File", "Dir", "Bg"))

    def test_leaf_names(self):
        self.assertEqual(core.LEAF["File"], "OpenViaIDE_File")
        self.assertEqual(core.LEAF["Dir"], "OpenViaIDE_Dir")
        self.assertEqual(core.LEAF["Bg"], "OpenViaIDE_Bg")

    def test_placeholder_rule_documented(self):
        # %V 只在目录背景有效；文件/文件夹必须用 %1
        self.assertIn("%1", core.__doc__ or "")
        self.assertIn("%V", core.__doc__ or "")

    def test_norm_contexts_rejects_unknown(self):
        with self.assertRaises(ValueError):
            core._norm_contexts(["Nope"])

    def test_norm_contexts_keeps_canonical_order(self):
        self.assertEqual(core._norm_contexts(["Bg", "File"]), ("File", "Bg"))
        self.assertEqual(core._norm_contexts(None), core.CONTEXT_IDS)


class TestReadOnlyRegistry(unittest.TestCase):
    """读取真实注册表（只读，不做任何修改）。"""

    @classmethod
    def setUpClass(cls):
        try:
            cls.items = core.get_items()
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest(f"无法读取注册表: {exc}")

    def test_reads_some_items(self):
        self.assertGreater(len(self.items), 0, "当前注册表里没有任何子菜单项")

    def test_every_item_has_context_and_name(self):
        for it in self.items:
            self.assertIn(it.context, core.CONTEXT_IDS)
            self.assertTrue(it.name)

    def test_item_immutable(self):
        it = self.items[0]
        with self.assertRaises(Exception):
            it.name = "x"  # type: ignore[misc]

    def test_command_uses_correct_placeholder(self):
        for it in self.items:
            if not it.command:
                continue
            if it.context == "Bg":
                self.assertIn("%V", it.command, f"{it.context}/{it.name} 应使用 %V")
            else:
                self.assertIn("%1", it.command, f"{it.context}/{it.name} 应使用 %1")

    def test_label_escaped_is_ascii(self):
        for it in self.items:
            out = it.label_escaped
            self.assertTrue(all(ord(c) < 128 for c in out))

    def test_parent_verbs_wired(self):
        verbs = {v.context: v for v in core.parent_verbs()}
        for ctx in core.CONTEXT_IDS:
            if ctx in verbs:
                self.assertTrue(verbs[ctx].wired, f"{ctx} 的 ExtendedSubCommandsKey 为空")
                self.assertEqual(verbs[ctx].target, core.LEAF[ctx])

    def test_exact_match(self):
        """按全称精确匹配：只在该项所属的上下文里命中一次。"""
        if not self.items:
            self.skipTest("无项目")
        sample = self.items[0]
        hits = core.select_matches([sample.label], [sample.context])
        self.assertEqual([(h.context, h.name) for h in hits], [(sample.context, sample.name)])

    def test_match_is_case_insensitive(self):
        if not self.items:
            self.skipTest("无项目")
        sample = self.items[0]
        hits = core.select_matches([sample.label.upper()], [sample.context])
        self.assertIn(sample.name, [h.name for h in hits])
        self.assertIn(sample.label, [h.label for h in hits])

    def test_wildcard(self):
        if not self.items:
            self.skipTest("无项目")
        hits = core.select_matches(["*"], core.CONTEXT_IDS)
        self.assertEqual(len(hits), len(self.items))

    def test_full_name_pattern(self):
        """全称（MUIVerb）必须命中。"""
        if not self.items:
            self.skipTest("无项目")
        sample = self.items[0]
        hits = core.select_matches([sample.label], core.CONTEXT_IDS)
        self.assertIn(sample.name, [h.name for h in hits])

    def test_bare_app_name_does_not_match(self):
        """只写应用名（注册表子键名）不得命中。"""
        if not self.items:
            self.skipTest("无项目")
        for sample in self.items:
            with self.subTest(name=sample.name):
                hits = core.select_matches([sample.name], core.CONTEXT_IDS)
                self.assertEqual(hits, [], f"子键名 {sample.name!r} 不应命中")

    def test_non_existent_name_yields_nothing(self):
        hits = core.select_matches(["__definitely_not_here__"], core.CONTEXT_IDS)
        self.assertEqual(hits, [])

    def test_display_prefers_label(self):
        if not self.items:
            self.skipTest("无项目")
        sample = self.items[0]
        m = core.Match("Bg", sample.name, sample.label)
        self.assertEqual(m.display, sample.label)
        self.assertEqual(core.Match("Bg", sample.name).display, sample.name)

    def test_missing_context_is_skipped_not_error(self):
        # 只选一个上下文，不应因其它上下文缺失而报错
        self.assertIsInstance(core.select_matches(["*"], ["Bg"]), list)


if __name__ == "__main__":
    unittest.main(verbosity=2)