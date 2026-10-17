"""管理员提权相关的测试（只做无副作用的探测，不真的触发 UAC）。"""

from __future__ import annotations

import unittest

from ide_menu import core


class TestIsAdmin(unittest.TestCase):
    def test_returns_bool(self):
        self.assertIsInstance(core.is_admin(), bool)

    def test_is_exported(self):
        for name in ("is_admin", "relaunch_elevated", "require_admin"):
            self.assertIn(name, core.__all__, f"{name} 未导出到 __all__")


class TestRelaunchElevated(unittest.TestCase):
    def test_noop_when_already_admin(self):
        """已经在管理员身份下时不应该重新拉起。"""
        if not core.is_admin():
            self.skipTest("当前不是管理员，跳过")
        self.assertFalse(core.relaunch_elevated([]))

    def test_accepts_explicit_argv(self):
        """签名必须接受一个 argv 序列（不真正执行提权）。"""
        import inspect

        params = inspect.signature(core.relaunch_elevated).parameters
        self.assertIn("argv", params)
        self.assertIsNone(params["argv"].default)


class TestRequireAdmin(unittest.TestCase):
    def test_true_when_admin(self):
        if not core.is_admin():
            self.skipTest("当前不是管理员，跳过")
        self.assertTrue(core.require_admin(gui=False))

    def test_no_gui_and_declined_returns_false(self):
        """gui=False 且用户在 stdin 回答 n 时，必须返回 False 而不是崩溃。"""
        if core.is_admin():
            self.skipTest("当前就是管理员，跳过")
        import builtins

        original = builtins.input
        builtins.input = lambda *_a, **_k: "n"
        try:
            self.assertFalse(core.require_admin(gui=False))
        finally:
            builtins.input = original

    def test_canceled_code_constant(self):
        self.assertEqual(core._RUNAS_CANCELED, 1223)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()