"""确认框按钮的文字位置：vivo 阅图锁屏把按钮文字放在 content-desc 上（Issue #246）。

设备无关：用 dump 到的真实层级树片段构造 XML，不连接手机。
运行：python -m unittest discover -s tests -v
"""
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tool"))
import fast


def phone():
    p = fast.Phone.__new__(fast.Phone)
    p.link = fast.adb_link.Connection("test")
    p.W, p.H = 1080, 2400
    p.log, p.miss, p.changed = False, 0, []
    p.d = Mock()
    return p


class ConfirmButtonTests(unittest.TestCase):
    @patch.object(fast.time, "sleep")
    def test_button_label_from_content_desc(self, _sleep):
        """vivo V2452A / 阅图锁屏：Button 的 text 为空，文字在 content-desc。

        页面同时有一个 text="关闭" 的 TextView（说明行里的一部分），
        点和读都必须落在 Button 上。
        """
        p = phone()
        root = ET.fromstring('''<hierarchy>
          <node class="android.widget.TextView" text="关闭" clickable="false" bounds="[502,2175][578,2222]"/>
          <node class="android.widget.Button" content-desc="保持开启" clickable="true" bounds="[270,1944][810,2082]"/>
          <node class="android.widget.Button" content-desc="关闭" clickable="true" bounds="[270,2130][810,2268]"/>
        </hierarchy>''')
        p.tree, p.click = Mock(return_value=root), Mock()
        self.assertEqual(p.confirm(), "关闭")
        p.click.assert_called_once_with(540, 2199)

    @patch.object(fast.time, "sleep")
    def test_state_text_without_button_class_is_ignored(self, _sleep):
        """ColorOS 开关旁边的「关闭」是状态文字，不是按钮：点了会把开关拨回去。"""
        p = phone()
        root = ET.fromstring('''<hierarchy>
          <node class="android.widget.TextView" text="关闭" clickable="false" bounds="[900,400][1000,450]"/>
          <node class="android.view.View" text="关闭" clickable="true" bounds="[900,500][1000,550]"/>
        </hierarchy>''')
        p.tree, p.click = Mock(return_value=root), Mock()
        self.assertIsNone(p.confirm())
        p.click.assert_not_called()

    @patch.object(fast.time, "sleep")
    def test_sentence_in_content_desc_is_not_a_confirm_label(self, _sleep):
        """content-desc 是整段说明时不算确认词，不能点。"""
        p = phone()
        root = ET.fromstring('''<hierarchy>
          <node class="android.widget.Button" content-desc="关闭后将无法自动切换锁屏壁纸及滑动浏览图集，建议保持开启。"
                clickable="true" bounds="[60,2200][1020,2320]"/>
        </hierarchy>''')
        p.tree, p.click = Mock(return_value=root), Mock()
        self.assertIsNone(p.confirm())
        p.click.assert_not_called()


if __name__ == "__main__":
    unittest.main()
