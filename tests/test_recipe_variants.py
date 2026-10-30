"""同一型号按系统版本选机型脚本变体（PR #338），以及变体要进安装包。不用手机。"""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tool"))
import run


class VariantTests(unittest.TestCase):
    def pick(self, model, brand, os_, build):
        path, reference = run.recipe_for(model, brand, {"os": os_, "build": build})
        self.assertFalse(reference)
        return Path(path).relative_to(ROOT / "recipes").as_posix()

    def test_xiaomi_15_hyperos_3_and_4(self):
        # #312 是 HyperOS 3，#298 是 HyperOS 4：同一型号两份，按系统版本选
        self.assertEqual(self.pick("24129PN74C", "Xiaomi", "OS3.0.307.0.WOCCNXM", "BP2A.250605.031.A3"),
                         "xiaomi-24129PN74C/recipe.py")
        self.assertEqual(self.pick("24129PN74C", "Xiaomi", "OS4.0.0.22.XOCCNXM", "CP2A.260605.016"),
                         "xiaomi-24129PN74C/recipe_os4.py")

    def test_oneplus_ace_2_android_15(self):
        self.assertEqual(self.pick("PHK110", "OnePlus", "", "PHK110_15.0.0.601(CN01)"), "oneplus-PHK110/recipe_android15.py")
        self.assertEqual(self.pick("PHK110", "OnePlus", "", "PHK110_16.0.5.701(CN01)"), "oneplus-PHK110/recipe.py")

    def test_variants_are_packaged(self):
        spec = importlib.util.spec_from_file_location("bundle_variants", ROOT / "gui/bundle_data.py")
        bundle = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bundle)
        shipped = {Path(src).relative_to(ROOT).as_posix() for src, _ in bundle.bundle_data(ROOT)}
        for variant in ROOT.glob("recipes/*/recipe_*.py"):
            self.assertIn(variant.relative_to(ROOT).as_posix(), shipped)


if __name__ == "__main__":
    unittest.main()
