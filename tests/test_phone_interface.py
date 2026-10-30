"""Phone 的接口面：读屏策略、探路的包名过滤、安全模式、读屏 adapter 的名字。

守的是「这些状态从哪来」：一次渠道尝试的诊断归 chan_fast（Attempt），
读屏策略与设备记忆归 Phone 构造处声明的字段。装配统一走 fixtures。
"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tool"))
import explore
import fast
from fixtures import Clock, Device, Timeline, fake_phone, install_clock, phone_stub
from reader import Reader

# 同一屏里两个 App 的文字：Settings 自己的一行，和浮在它上面的另一个窗口
TWO_WINDOWS = '''<hierarchy rotation="0">
  <node class="android.widget.TextView" package="com.android.settings" text="隐私" bounds="[60,300][400,360]"/>
  <node class="android.widget.TextView" package="com.example.overlay" text="别的窗口" bounds="[60,420][400,480]"/>
  <node class="android.widget.TextView" package="com.android.settings" text="广告" bounds="[60,540][400,600]"/>
</hierarchy>'''


# vivo OriginOS Ocean（安卓 10）的通知设置页挂在 com.android.systemui 上
SYSTEMUI_PAGE = '''<hierarchy rotation="0">
  <node package="com.android.systemui" text="状态栏" bounds="[60,60][400,120]"/>
  <node package="com.android.systemui" text="允许通知" bounds="[60,300][400,360]"/>
  <node package="com.android.systemui" class="android.widget.Switch" checkable="true" checked="true" bounds="[950,300][1060,380]"/>
</hierarchy>'''


class TextsTests(unittest.TestCase):
    def test_systemui_text_is_dropped_unless_the_page_is_systemui(self):
        p = fake_phone(stages=[(0.0, SYSTEMUI_PAGE)])
        self.assertEqual(p.texts(), [])                              # 状态栏文字默认不算
        p.systemui_text = True
        self.assertEqual([t for t, _, _ in p.texts()], ["状态栏", "允许通知"])


class EntriesTests(unittest.TestCase):
    def test_entries_drop_text_from_another_window(self):
        p = fake_phone(stages=[(0.0, TWO_WINDOWS)])
        self.assertIn("别的窗口", [t for t, _, _ in p.texts()])      # 守卫：这段文字真的读到了
        self.assertEqual(explore.entries(p, "com.android.settings"), ["隐私", "广告"])


class FakeReader:
    """一个按 Reader 接口写的假设备：只实现 Phone 真正会调到的方法。"""

    def __init__(self, page="<hierarchy/>", size=(1080, 2340)):
        self.page, self.size, self.commands = page, size, []
        self.settings = {}
        self.closed = False

    def shell(self, command, timeout=60):
        self.commands.append(command)
        return SimpleNamespace(output="", exit_code=0)

    def dump_hierarchy(self):
        return self.page

    def window_size(self):
        return self.size

    def screenshot(self):
        return None

    def app_stop(self, package):
        self.stopped = package

    def close(self):
        self.closed = True


class ReaderTests(unittest.TestCase):
    def test_fixtures_device_is_a_reader(self):
        self.assertIsInstance(Device(Timeline([(0.0, "<hierarchy/>")]), (1080, 2340), Clock()), Reader)

    def test_a_stub_reader_is_the_same_object_as_d(self):
        p = phone_stub("S", d=FakeReader())
        self.assertIs(p.d, p.reader)                                  # `d` 只是历史名字
        p.d = FakeReader()                                            # 写 `d` 也写穿到 reader
        self.assertIsInstance(p.reader, FakeReader)

    def test_phone_can_be_built_from_a_named_reader(self):
        r = FakeReader()
        p = fast.Phone("S", log=False, reader=r)
        self.assertIs(p.reader, r)
        self.assertEqual((p.W, p.H), (1080, 2340))
        self.assertEqual(p.texts(), [])                               # 没连手机也能读屏（空树）
        p.close()
        self.assertTrue(r.closed)


# 两个都不该在安全模式下被碰的普通广告开关
LIST_PAGE = '''<hierarchy rotation="0">
  <node package="com.android.settings" clickable="true" bounds="[0,300][1080,380]">
    <node text="个性化推荐" bounds="[60,310][400,370]"/>
    <node class="android.widget.Switch" checkable="true" checked="true" bounds="[950,300][1060,380]"/>
  </node>
  <node package="com.android.settings" clickable="true" bounds="[0,500][1080,580]">
    <node text="猜你喜欢" bounds="[60,510][400,570]"/>
    <node class="android.widget.Switch" checkable="true" checked="true" bounds="[950,500][1060,580]"/>
  </node>
</hierarchy>'''


CARD_PAGE = '''<hierarchy rotation="0">
  <node package="com.android.settings" clickable="true" bounds="[0,600][1080,860]">
    <node text="营销通知" bounds="[60,620][600,700]"/>
    <node class="android.widget.Switch" checkable="true" checked="true" bounds="[900,620][1000,700]"/>
    <node class="android.widget.Switch" checkable="true" checked="false" bounds="[900,750][1000,830]"/>
  </node>
  <node package="com.android.settings" bounds="[0,1000][1080,1260]">
    <node text="订单通知" bounds="[60,1020][600,1100]"/>
    <node class="android.widget.Switch" checkable="true" checked="true" bounds="[900,1020][1000,1100]"/>
  </node>
</hierarchy>'''


class AttemptTests(unittest.TestCase):
    """一次渠道尝试的诊断归 chan_fast；Phone 上不再有 why / stage / vivo_app。"""

    def test_the_reason_lands_in_the_attempt_not_on_the_phone(self):
        import chan_fast as chan
        p = fake_phone(stages=[(0.0, CARD_PAGE)],
                       focus=[(0.0, "com.android.settings/com.android.settings.Settings$AppNotificationSettingsActivity")])
        at = chan.Attempt()
        self.assertIsNone(chan.inline_switch(p, "营销通知", at))     # 行内两个开关：认不出
        self.assertIn("行内开关 2 个", at.why)                        # 守卫：真的走到了「没认出」这一支
        for gone in ("why", "stage", "vivo_app"):
            self.assertFalse(hasattr(p, gone), gone)                  # 这些状态不再挂在 Phone 上


class SafeModeTests(unittest.TestCase):
    """安全模式（参考脚本 / 录制版本不符）只关点名的开关，不做整页全关。"""

    def phone(self):
        self.lines = []
        self.clock = Clock()
        install_clock(fast, self.clock)
        return fake_phone(clock=self.clock, stages=[(0.0, LIST_PAGE)], say=self.lines.append)

    def test_safe_mode_leaves_a_page_of_unnamed_switches_alone(self):
        p = self.phone()
        p.safe_mode = True
        self.assertEqual(p.off(page="系统·广告服务"), 0)
        self.assertEqual(self.clock.clicks, 0)                        # 守卫：真的一下都没点
        self.assertTrue(any("安全模式不做整页全关" in line for line in self.lines))
        self.assertEqual(p.changed, [])

    def test_without_safe_mode_the_same_page_is_clicked(self):
        p = self.phone()
        p.safe_mode = False
        p.off(page="系统·广告服务")
        self.assertGreater(self.clock.clicks, 0)                      # 同一页在非安全模式下会点
        self.assertFalse(any("安全模式不做整页全关" in line for line in self.lines))


if __name__ == "__main__":
    unittest.main()
