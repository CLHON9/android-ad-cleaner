"""Xiaomi 15（24129PN74C）：本机实测入口、回读保护、与同底包脚本的差异。

2026-10-29 无线调试实测：底包 BP2A.250605.031.A3 与 recipes/redmi-25060RK16C 一致，
但浏览器入口是「菜单 → 设置」（不是底栏「我的」），商店没有隐私设置入口，
系统广告走设置搜索 / 深链（隐私与安全页里没有「更多安全设置」）。
"""
import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tool"))
import run


class Xiaomi24129PN74CRecipeTests(unittest.TestCase):
    def load(self, phone):
        path = ROOT / "recipes/xiaomi-24129PN74C/recipe.py"
        scope = {"p": phone, "ONLY": ["__no_steps__"]}
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), scope)
        return scope

    def test_actual_model_selects_own_recipe_and_pins_recorded_build(self):
        path, reference = run.recipe_for("24129PN74C", "Xiaomi")
        self.assertFalse(reference)
        self.assertEqual(Path(path).parent.name, "xiaomi-24129PN74C")
        self.assertEqual(run.recipe_meta(path)["build"], "BP2A.250605.031")
        self.assertEqual(run.recipe_meta(path)["models"], ["24129PN74C"])
        self.assertEqual(run.recipe_meta(path)["steps"],
                         ["系统广告", "应用商店", "手机管家", "下载管理", "主题",
                          "浏览器", "全局搜索", "负一屏", "天气和日历"])

    def test_build_matches_this_phone_and_not_other_base_packages(self):
        this_phone = {"build": "BP2A.250605.031.A3", "os": "OS3.0.307.0.WOCCNXM"}
        self.assertTrue(run.build_ok(this_phone, "BP2A.250605.031"))
        # OS4.0（小米 18 系列）不是这台机的底包。
        self.assertFalse(run.build_ok(this_phone, "OS4.0"))
        # build_ok 同时比对 HyperOS 版本号，这台的 OS3.0.307.0 与 K70 同号。
        self.assertTrue(run.build_ok(this_phone, "OS3.0.307.0"))

    def test_same_base_package_as_k80_script_but_own_entry_points(self):
        # 底包相同不等于入口相同：浏览器走「菜单」而不是底栏「我的」，商店没有隐私设置。
        k80 = run.recipe_meta(ROOT / "recipes/redmi-25060RK16C/recipe.py")["build"]
        self.assertEqual(k80, "BP2A")
        source = (ROOT / "recipes/xiaomi-24129PN74C/recipe.py").read_text(encoding="utf-8")
        self.assertIn('p.tap("菜单", exact=True, scrolls=0)', source)
        self.assertNotIn('p.tap("我的", exact=True, scrolls=0), "未找到浏览器', source)

    def test_system_ads_uses_search_or_deep_link_not_more_security_settings(self):
        source = (ROOT / "recipes/xiaomi-24129PN74C/recipe.py").read_text(encoding="utf-8")
        # 本机「隐私与安全」是权限中心，没有「更多安全设置」这一项。
        self.assertIn('p.setting("广告服务")', source)
        self.assertIn("com.android.settings/.ad.AdServiceSettings", source)
        # 菜单路径里不能出现「更多安全设置」这个点击动作（注释里的说明不算）。
        code = "\n".join(line for line in source.splitlines()
                         if not line.lstrip().startswith("#"))
        self.assertNotIn("更多安全设置", code)

    def test_browser_keeps_function_switches_and_turns_off_ads_only(self):
        source = (ROOT / "recipes/xiaomi-24129PN74C/recipe.py").read_text(encoding="utf-8")
        # 运营任务 = 做任务得金币挣红包，纯营销，要关。
        self.assertIn('p.off(only=["运营任务", "小说"], keep=["我的网盘"]', source)
        # 扫一扫 / 搜索历史 / 书签 / 最常访问是功能项，不能进 only 名单。
        for functional in ("显示扫一扫模块", "显示搜索历史模块", "显示书签模块", "显示最常访问模块"):
            self.assertNotIn(functional, source)

    def test_missing_target_aborts_without_touching_switches(self):
        p = Mock()
        p.switches.return_value = [("其他开关", True, (1, 2))]
        p.scroll_more.return_value = False
        scope = self.load(p)
        with self.assertRaisesRegex(RuntimeError, "未识别全部目标"):
            scope["close_named"](["个性化广告推荐"], "系统·广告服务")
        p.off.assert_not_called()

    def test_reverted_switch_is_failure_not_verified(self):
        p = Mock()
        p.switches.return_value = [("个性化广告推荐", True, (1, 2))]
        p.scroll_more.return_value = False
        scope = self.load(p)
        with self.assertRaisesRegex(RuntimeError, "回读未确认关闭"):
            scope["close_named"](["个性化广告推荐"], "系统·广告服务")
        self.assertEqual(scope["VERIFIED_SWITCHES"], 0)

    def test_already_off_target_is_verified(self):
        p = Mock()
        p.switches.return_value = [("个性化广告推荐 个性化广告服务会根据您的喜好进行精准匹配。", False, (1, 2))]
        p.scroll_more.return_value = False
        scope = self.load(p)
        scope["close_named"](["个性化广告推荐"], "系统·广告服务")
        self.assertEqual(scope["VERIFIED_SWITCHES"], 1)
        p.off.assert_called_once()

    def test_unrelated_switch_changed_is_not_reported_as_verified(self):
        p = Mock()
        p.switches.side_effect = [
            [("个性化广告推荐", True, (1, 2)), ("其他开关", True, (1, 3))],
            [("个性化广告推荐", False, (1, 2)), ("其他开关", False, (1, 3))],
        ]
        p.scroll_more.return_value = False
        scope = self.load(p)
        with self.assertRaisesRegex(RuntimeError, "其他开关状态变化"):
            scope["close_named"](["个性化广告推荐"], "系统·广告服务")
        self.assertEqual(scope["VERIFIED_SWITCHES"], 0)

    def test_protection_switch_is_not_in_any_only_list(self):
        """「限制广告跟踪」「防止广告追踪」这类开关是保护类，打开才对，不能进 only 名单。"""
        source = (ROOT / "recipes/xiaomi-24129PN74C/recipe.py").read_text(encoding="utf-8")
        for protective in ("限制广告跟踪", "防止广告追踪", "阻止广告跟踪"):
            self.assertNotIn(protective, source)


if __name__ == "__main__":
    unittest.main()
