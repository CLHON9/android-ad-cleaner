"""OPPO Find X8s（PKT110 / ColorOS 17）：入口回读和目标开关不完整时停止，避免把尝试写成成功。"""
import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tool"))
import run


class OppoPkt110RecipeTests(unittest.TestCase):
    def load(self, phone):
        path = ROOT / "recipes/oppo-PKT110/recipe.py"
        scope = {"p": phone, "ONLY": ["__no_steps__"]}
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), scope)
        return scope

    def test_actual_model_selects_own_recipe_and_pins_recorded_build(self):
        path, reference = run.recipe_for("PKT110", "OPPO")
        self.assertFalse(reference)
        self.assertEqual(Path(path).parent.name, "oppo-PKT110")
        self.assertEqual(run.recipe_meta(path)["build"], "PKT110_17.0.0.102(CN01)")

    def test_other_oppo_model_falls_back_to_reference_recipe(self):
        path, reference = run.recipe_for("PMX110", "OPPO")
        self.assertTrue(reference)
        self.assertEqual(Path(path).parent.name, "oppo-PLP120")

    def test_missing_target_aborts_without_clicking_any_switch(self):
        p = Mock(); p.switches.return_value = [("WLAN 自动更新应用", True, (1, 2))]
        scope = self.load(p)
        with self.assertRaisesRegex(RuntimeError, "未识别全部目标开关"):
            scope["close_named"](["个性化推荐"], "商店")
        p.off.assert_not_called()

    def test_reverted_switch_is_failure_not_verified(self):
        p = Mock(); p.switches.return_value = [("个性化推荐", True, (1, 2))]
        scope = self.load(p)
        with self.assertRaisesRegex(RuntimeError, "回读未确认关闭"):
            scope["close_named"](["个性化推荐"], "商店")
        self.assertEqual(scope["VERIFIED_SWITCHES"], 0)

    def test_target_below_fold_is_verified_and_other_switch_is_preserved(self):
        p = Mock()
        p.scroll_more.return_value = True
        p.switches.side_effect = [
            [("活动弹窗", True, (1, 2)), ("应用安全", True, (1, 3))],
            [("软件福利", True, (1, 2))],
            [("活动弹窗", False, (1, 2)), ("应用安全", True, (1, 3))],
            [("软件福利", False, (1, 2))],
        ]
        scope = self.load(p)
        scope["close_named"](["活动弹窗", "软件福利"], "商店", max_screens=2)
        self.assertEqual(scope["VERIFIED_SWITCHES"], 2)

    def test_unrelated_switch_changed_is_not_reported_as_verified(self):
        p = Mock()
        p.switches.side_effect = [
            [("活动弹窗", True, (1, 2)), ("应用安全", True, (1, 3))],
            [("活动弹窗", False, (1, 2)), ("应用安全", False, (1, 3))],
        ]
        scope = self.load(p)
        with self.assertRaisesRegex(RuntimeError, "其他开关状态变化"):
            scope["close_named"](["活动弹窗"], "商店")
        self.assertEqual(scope["VERIFIED_SWITCHES"], 0)

    def test_page_that_asks_for_confirmation_is_reopened_before_readback(self):
        """主题商店「个性化推荐设置」：点下去弹确认框，确认后页面退回「设置」，
        回读前要重新进一次，否则会把关成功的开关算成没关。"""
        p = Mock()
        p.switches.side_effect = [
            [("个性化推荐设置", True, (1, 2))],
            [("个性化推荐设置", False, (1, 2))],
        ]
        scope = self.load(p)
        reopened = []
        scope["close_named"](["个性化推荐设置"], "主题", reopen=lambda: reopened.append(1))
        self.assertEqual(len(reopened), 1)
        self.assertEqual(scope["VERIFIED_SWITCHES"], 1)

    def test_close_all_needs_a_switch_to_be_present(self):
        p = Mock(); p.switches.return_value = []
        scope = self.load(p)
        with self.assertRaisesRegex(RuntimeError, "没读到开关"):
            scope["close_all"]("广告跟踪", max_screens=1)
        p.off.assert_not_called()

    def test_close_all_reports_switches_still_on_after_readback(self):
        p = Mock()
        p.switches.side_effect = [
            [("广告跟踪", True, (1, 2))],
            [("广告跟踪", True, (1, 2))],
        ]
        scope = self.load(p)
        with self.assertRaisesRegex(RuntimeError, "回读未确认关闭"):
            scope["close_all"]("广告跟踪", max_screens=1)
        self.assertEqual(scope["VERIFIED_SWITCHES"], 0)

    def test_close_all_verifies_every_switch_is_off(self):
        p = Mock()
        p.switches.side_effect = [
            [("广告跟踪", True, (1, 2)), ("示例应用", True, (1, 3))],
            [("广告跟踪", False, (1, 2)), ("示例应用", False, (1, 3))],
        ]
        scope = self.load(p)
        scope["close_all"]("广告跟踪", max_screens=1)
        self.assertEqual(scope["VERIFIED_SWITCHES"], 2)

    def test_recipe_never_suspends_disables_or_uninstalls_packages(self):
        """挂起、停用、卸载和整包关通知都不该出现在机型脚本里（CHANGELOG 0.2.6 记录过问题写法）。"""
        source = (ROOT / "recipes/oppo-PKT110/recipe.py").read_text(encoding="utf-8")
        for forbidden in ("pm suspend", "pm uninstall", "pm disable-user", "pm revoke", "notif-off"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
