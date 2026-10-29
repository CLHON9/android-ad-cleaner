"""2026-10-29：0.2.6 一夜的 68 份上报和 GitHub 新 Issue 归类出的问题，以及提示音、adb 镜像。不用手机。"""
import os
os.environ.setdefault("AAC_NO_SOUND", "1")     # 客户端提示音：测试里不出声
import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tool"))
import chan_fast as chan
import fast


def phone(xml, w=1080, h=2340):
    p = fast.Phone.__new__(fast.Phone)
    p.W, p.H, p.log, p.miss = w, h, False, 0
    p.d = Mock()
    p.click = Mock()
    p.tree = Mock(return_value=ET.fromstring(xml))
    return p


# #247 OPPO Find X9 Pro 软件商店：「边下边玩」的说明里有「隐私」，tap 隐私 点了这一行，把功能关了
STORE = '''<hierarchy><node bounds="[0,0][1080,2340]">
  <node clickable="true" bounds="[0,400][1080,560]">
    <node text="边下边玩" bounds="[60,410][700,470]"/>
    <node text="试玩时不涉及隐私数据" bounds="[60,480][700,540]"/>
    <node class="android.widget.Switch" checkable="true" checked="true" bounds="[900,440][1000,520]"/>
  </node>
  <node clickable="true" bounds="[0,600][1080,700]">
    <node text="隐私授权管理" bounds="[60,620][700,680]"/>
  </node>
  <node clickable="true" bounds="[0,800][1080,900]">
    <node text="隐私" bounds="[60,820][700,880]"/>
  </node>
</node></hierarchy>'''


class TapTests(unittest.TestCase):
    def test_exact_title_wins_over_partial_text(self):
        p = phone(STORE)
        self.assertEqual(p.find("隐私", nav=True), (380, 850))

    def test_partial_match_skips_switch_descriptions(self):
        xml = STORE.replace('<node text="隐私" bounds="[60,820][700,880]"/>', "")
        p = phone(xml)
        self.assertEqual(p.find("隐私", nav=True), (380, 650))       # 导航行「隐私授权管理」，不是开关的说明
        only_switch = '''<hierarchy><node bounds="[0,0][1080,2340]">''' + STORE.split('<node bounds="[0,0][1080,2340]">')[1].split("</node>\n  <node clickable")[0] + "</node></node></hierarchy>"
        self.assertIsNone(phone(only_switch).find("隐私", nav=True))
        self.assertEqual(phone(only_switch).find("隐私"), (380, 510))   # 只看在不在（go 的判断）不受影响

    def test_switch_row_helper(self):
        root = ET.fromstring(STORE)
        parents = {c: q for q in root.iter() for c in q}
        texts = {n.get("text"): n for n in root.iter("node") if n.get("text")}
        self.assertTrue(fast.switch_row(texts["试玩时不涉及隐私数据"], parents))
        self.assertFalse(fast.switch_row(texts["隐私授权管理"], parents))


class ConfirmTests(unittest.TestCase):
    def test_label_in_child_text_view(self):
        # PR #239：vivo / iQOO 弹窗的按钮文字在 Button 下级 TextView（vbutton_title）
        p = phone('''<hierarchy><node bounds="[0,0][1080,2340]">
          <node class="android.widget.Button" clickable="true" bounds="[270,2130][810,2268]">
            <node resource-id="com.vivo.magazine:id/vbutton_title" class="android.widget.TextView" text="关闭" bounds="[502,2175][578,2222]"/>
          </node></node></hierarchy>''')
        with patch.object(fast.time, "sleep"):
            self.assertEqual(p.confirm(), "关闭")
        p.click.assert_called_once_with(540, 2199)

    def test_off_screen_leftover_button_is_skipped(self):
        # PR #248：页面里留着上一层对话框的按钮，坐标在屏幕外
        p = phone('''<hierarchy><node bounds="[0,0][1080,2340]">
          <node class="android.widget.Button" text="确定" bounds="[2200,1000][2600,1100]"/>
          <node class="android.widget.Button" text="确定" bounds="[300,1500][800,1600]"/>
        </node></hierarchy>''')
        with patch.object(fast.time, "sleep"):
            self.assertEqual(p.confirm(), "确定")
        p.click.assert_called_once_with(550, 1550)

    def test_button_with_its_own_label_ignores_child_words(self):
        p = phone('''<hierarchy><node bounds="[0,0][1080,2340]">
          <node class="android.widget.Button" text="保持开启" bounds="[270,1944][810,2082]">
            <node class="android.widget.TextView" text="关闭" bounds="[300,1950][400,2000]"/>
          </node></node></hierarchy>''')
        with patch.object(fast.time, "sleep"):
            self.assertIsNone(p.confirm())


class FocusTests(unittest.TestCase):
    def test_null_focus_falls_back_to_focused_app(self):
        # 华为 LIO-AN00 HarmonyOS 4.2、vivo V2111A：页面在，却报「停在 未知页面」
        p = fast.Phone.__new__(fast.Phone)
        p.d = Mock()
        p.d.shell.return_value = types.SimpleNamespace(output=(
            "  mCurrentFocus=null\n  mFocusedApp=ActivityRecord{5e1 u0 com.android.settings/.Settings$AppNotificationSettingsActivity t88}\n"))
        self.assertEqual(p.focus(), "com.android.settings/.Settings$AppNotificationSettingsActivity")

    def test_resumed_activity_line_variants(self):
        p = fast.Phone.__new__(fast.Phone)
        p.d = Mock()
        p.d.shell.side_effect = [types.SimpleNamespace(output="  mCurrentFocus=null\n"),
                                 types.SimpleNamespace(output="    mResumedActivity: ActivityRecord{9a u0 com.vivo.x/.MainActivity t3}\n")]
        self.assertEqual(p.focus(), "com.vivo.x/.MainActivity")


ANDROID9 = """Ranking Config:
  per-package config:
Records:
    AppSettings: com.hisense.promo (10091)
        NotificationChannel{mId='deals', mName=优惠活动, mDescription=null, mImportance=3, mBypassDnd=false, mDeleted=false}
    AppSettings: com.blocked (10092) importance=NONE
        NotificationChannel{mId='news', mName=新闻推送, mDescription=null, mImportance=3, mBypassDnd=false, mDeleted=false}
Restored without uid:
"""


class NotificationTests(unittest.TestCase):
    def test_android9_dump_is_read(self):
        # #258 海信 HLTE217T / Android 9：以前「读不到通知渠道状态」
        p = types.SimpleNamespace(d=types.SimpleNamespace(shell=lambda *a, **k: types.SimpleNamespace(output=ANDROID9)))
        d, app_off = chan.parse(p)
        self.assertEqual(d[("com.hisense.promo", "deals")], ("优惠活动", 3, False))
        self.assertTrue(app_off["com.blocked"])

    def test_channel_name_with_trailing_space(self):
        # 一加 13：渠道名「福利活动 」带空格，页面文字去掉了空格，以前「应用通知页里没找到这一行」
        p = Mock()
        p.locked.return_value = False
        seen = []
        with patch.object(chan, "parse", return_value=({("com.x", "w"): ("福利活动 ", 3, False)}, {})), \
             patch.object(chan, "wait_page", side_effect=lambda p, name, rounds=12: seen.append(name)), \
             patch.object(chan, "via_app_page", return_value=None), patch.object(chan, "page_hint", return_value=""):
            chan.toggle(p, "com.x", "w", False, "福利活动 ")
        self.assertEqual(seen, ["福利活动"])

    def test_app_level_permission_off_is_not_a_failure(self):
        # 三星 SM-S9080：9 个渠道页上开关显示关、渠道记录仍开（应用通知整体关了）
        p = Mock()
        p.d.shell.return_value = types.SimpleNamespace(output="      android.permission.POST_NOTIFICATIONS: granted=false, flags=[ USER_SET ]\n")
        self.assertTrue(chan.notifications_denied(p, "com.samsung.x"))
        p.d.shell.return_value = types.SimpleNamespace(output="      android.permission.POST_NOTIFICATIONS: granted=true, flags=[ ]\n")
        self.assertFalse(chan.notifications_denied(p, "com.samsung.x"))

    def test_denied_channels_are_left_out_of_the_failure_count(self):
        items = [("com.a", "promo", "营销通知"), ("com.b", "news", "新闻")]
        on = {(pk, cid): (label, 3, False) for pk, cid, label in items}
        after = {("com.a", "promo"): ("营销通知", 0, False), ("com.b", "news"): ("新闻", 3, False)}
        phone_ = Mock(wait_unlocked=Mock(return_value=True), lost=False)
        with patch.object(chan, "load", return_value=items), patch.object(chan, "parse", side_effect=[(on, {}), (after, {})]), \
             patch.object(chan, "Phone", return_value=phone_), patch.object(chan, "keep_awake", return_value=None), \
             patch.object(chan, "toggle", side_effect=[None, chan.APP_DENIED]), patch.object(chan, "pause_point"), \
             patch.object(sys, "argv", ["chan_fast.py", "-s", "t", "off", "x.tsv"]), contextlib.redirect_stdout(io.StringIO()) as out:
            chan.main()                 # 不 sys.exit(1)
        self.assertIn("应用通知已整体关闭", out.getvalue())
        self.assertIn("营销渠道仍开着: 0 个", out.getvalue())


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("aac_gui_1029", ROOT / "gui/app.py")
        cls.app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.app)

    def test_adb_falls_back_to_mirror_and_checks_the_file(self):
        # #273：从 Google 下载 adb 失败
        body = b"PK-fake-zip"
        digest = hashlib.sha256(body).hexdigest()

        class Reply(io.BytesIO):
            headers = {"Content-Length": str(len(body))}
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with tempfile.TemporaryDirectory() as d, patch.object(self.app, "DATA", d):
            api = self.app.Api()
            sources = [("Google 官网", "https://g/x.zip", digest), ("腾讯云镜像", "https://t/x.zip", digest)]
            urls = []

            def opener(request, timeout):
                urls.append(request.full_url)
                if "//g/" in request.full_url:
                    raise OSError("timed out")
                return Reply(body)
            with patch.object(api, "adb_sources", return_value=sources), \
                 patch.object(self.app.urllib.request, "urlopen", side_effect=opener), \
                 patch.object(self.app.zipfile, "ZipFile", side_effect=self.app.zipfile.BadZipFile("not a zip")):
                api._download()
            self.assertEqual(urls, ["https://g/x.zip", "https://t/x.zip"])
            self.assertIn("not a zip", api.dl["msg"])           # 校验过了，走到解压
            self.assertFalse(Path(d, "platform-tools.zip").exists())
            with patch.object(api, "adb_sources", return_value=[("腾讯云镜像", "https://t/x.zip", "0" * 64)]), \
                 patch.object(self.app.urllib.request, "urlopen", return_value=Reply(body)):
                api._download()
            self.assertIn("校验不对", api.dl["msg"])

    def test_pinned_adb_covers_every_platform(self):
        for system in ("Windows", "Darwin", "Linux"):
            name, digest = self.app.ADB_PINNED[system]
            self.assertIn(self.app.ADB_VERSION, name)
            self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_chime_moments(self):
        with tempfile.TemporaryDirectory() as d, patch.object(self.app, "DATA", d), \
             patch.object(self.app, "chime") as chime:
            api = self.app.Api()
            api.job = {"running": True, "cancel": False, "lines": [], "results": [], "serial": "t", "t0": 0}
            api._log("  ! 手机锁屏了：请解锁手机并保持亮屏，解锁后自动继续（最多等 90 秒）")
            api._log("⏸ 已暂停：现在可以操作手机。")
            api._log("  关  营销通知")
            self.assertEqual(chime.call_count, 2)
            done = Mock(stdout=io.StringIO("")); done.wait.return_value = 0
            with patch.object(self.app.subprocess, "Popen", return_value=done):
                api._work([("收尾", "run.py", ["-s", "t", "finish"])])
            self.assertEqual(chime.call_count, 3)

    def test_chime_plays_once_for_close_events_and_never_in_tests(self):
        with patch.dict(os.environ, {"AAC_NO_SOUND": ""}), patch.object(self.app, "IS_WIN", False), \
             patch.object(self.app.platform, "system", return_value="Darwin"), \
             patch.object(self.app.subprocess, "Popen") as popen:
            self.app._last_chime[0] = 0
            self.app.chime(); self.app.chime()
        self.assertEqual(popen.call_count, 1)
        self.assertEqual(popen.call_args.args[0][0], "afplay")
        self.assertTrue(popen.call_args.args[0][1].endswith("chime.wav"))
        with patch.object(self.app.subprocess, "Popen") as popen:
            self.app._last_chime[0] = 0
            self.app.chime()
        popen.assert_not_called()

    def test_chime_file_is_short_soft_and_shipped(self):
        import wave
        with wave.open(str(ROOT / "gui/web/chime.wav")) as w:
            frames = w.readframes(w.getnframes())
            seconds = w.getnframes() / w.getframerate()
        peak = max(abs(int.from_bytes(frames[i:i + 2], "little", signed=True)) for i in range(0, len(frames), 2)) / 32767
        self.assertLess(seconds, 1.0)
        self.assertTrue(0.15 < peak < 0.4)                    # 不刺耳，也不至于听不见
        spec = importlib.util.spec_from_file_location("bundle_1029", ROOT / "gui/bundle_data.py")
        bundle = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bundle)
        self.assertIn(str(ROOT / "gui/web/chime.wav"), [src for src, _ in bundle.bundle_data(ROOT)])


if __name__ == "__main__":
    unittest.main()
