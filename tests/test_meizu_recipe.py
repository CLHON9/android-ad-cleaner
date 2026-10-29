"""魅族脚本只操作已确认的页面和精确目标，不把失败回读当成功。"""
import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tool"))
import run

RECIPE = ROOT / "recipes/meizu-MEIZU 21 Pro/recipe.py"


class MeizuRecipeTests(unittest.TestCase):
    def phone(self):
        p = Mock()
        p.changed = []
        p.W, p.H = 1000, 2000
        p.focus.return_value = "app/Settings"
        p.locked.return_value = False
        p.tree.return_value = ET.Element("hierarchy")
        p.texts.return_value = []
        return p

    def load(self, phone, only=None):
        scope = {"p": phone, "ONLY": only or ["__none__"]}
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(RECIPE.read_text(encoding="utf-8"), str(RECIPE), "exec"), scope)
        return scope

    def test_model_selects_exact_recipe(self):
        path, reference = run.recipe_for("MEIZU 21 Pro", "meizu")
        self.assertFalse(reference)
        self.assertEqual(Path(path), RECIPE)
        meta = run.recipe_meta(path)
        self.assertEqual(meta["build"], "Flyme 12.6.0.0A")
        self.assertIn("锁屏画报", meta["steps"])

    def test_version_mismatch_aborts_before_navigation(self):
        p = self.phone()
        p.d.shell.side_effect = [Mock(output="MEIZU 21 Pro"), Mock(output="Flyme 12.6.1.0A")]
        scope = self.load(p, ["全局搜索"])
        self.assertEqual(scope["FAILED_STEPS"], ["全局搜索"])
        p.click.assert_not_called()
        self.assertEqual(p.d.shell.call_count, 2)

    def test_missing_or_duplicate_target_stops_before_click(self):
        for switches in ([('其他', True, (1, 2))],
                         [('目标', True, (1, 2)), ('目标', True, (3, 4))]):
            p = self.phone(); p.switches.return_value = switches
            scope = self.load(p)
            with self.assertRaisesRegex(RuntimeError, "未全部唯一识别"):
                scope["close_named"](["目标"], "页面", "app/Settings")
            p.click.assert_not_called()

    def test_only_confirm_matching_dialog_and_verify(self):
        p = self.phone()
        p.switches.side_effect = [[("目标", True, (900, 500)), ("提醒", True, (900, 700))],
                                  [("目标", True, (900, 500))],
                                  [("目标", False, (900, 500)), ("提醒", True, (900, 700))]]
        button = ET.Element("node", {"class": "android.widget.Button"})
        p.texts.return_value = [("确定关闭目标？", (100, 1000, 800, 1100), ET.Element("node")),
                                ("确定", (600, 1200, 800, 1300), button)]
        scope = self.load(p)
        with patch.object(scope["time"], "sleep"):
            scope["close_named"](["目标"], "页面", "app/Settings")
        self.assertEqual(p.click.call_count, 2)
        self.assertEqual(p.changed, [("页面", "目标")])

    def test_unrelated_confirmation_stops_without_confirming(self):
        p = self.phone()
        p.switches.return_value = [("目标", True, (900, 500))]
        button = ET.Element("node", {"class": "android.widget.Button"})
        p.texts.return_value = [("同意协议", (100, 1000, 800, 1100), ET.Element("node")),
                                ("确定", (600, 1200, 800, 1300), button)]
        scope = self.load(p)
        with patch.object(scope["time"], "sleep"), self.assertRaisesRegex(RuntimeError, "无法识别"):
            scope["close_named"](["目标"], "页面", "app/Settings")
        self.assertEqual(p.click.call_count, 1)
        self.assertEqual(p.changed, [])

    def test_other_switch_change_fails_verification(self):
        p = self.phone()
        p.switches.side_effect = [[("目标", True, (900, 500)), ("提醒", True, (900, 700))],
                                  [("目标", True, (900, 500))],
                                  [("目标", False, (900, 500)), ("提醒", False, (900, 700))]]
        scope = self.load(p)
        with patch.object(scope["time"], "sleep"), self.assertRaisesRegex(RuntimeError, "其他开关"):
            scope["close_named"](["目标"], "页面", "app/Settings")
        self.assertEqual(p.changed, [])


if __name__ == "__main__":
    unittest.main()
