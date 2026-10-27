"""2026-10-27 社区反馈回归：荣耀 / 三星渠道页、内联渠道开关、多用户解析、小米点击被拒、adb 掉线。
不用手机，模拟页面与系统回读。"""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tool"))
import adb_link
import chan_fast as chan
import fast
import run
import troubleshooting


def page(xml, focus, w=1080, h=2340):
    p = fast.Phone.__new__(fast.Phone)
    p.W, p.H, p.log = w, h, False
    p.d = Mock()
    p.locked = Mock(return_value=False)
    p.focus = Mock(return_value=focus)
    p.confirm = Mock()
    p.click = Mock()
    p.tree = Mock(return_value=ET.fromstring(xml))
    return p


CHANNEL_PAGE = '''<hierarchy><node>
  <node text="营销通知" bounds="[100,120][600,200]"/>
  <node bounds="[0,300][1080,410]">
    <node text="允许通知" bounds="[60,320][600,390]"/>
    <node class="android.widget.Switch" checkable="true" checked="true" bounds="[900,320][1040,390]"/>
  </node>
</node></hierarchy>'''

# #99 荣耀 Magic6 / MagicOS 10 / Android 16：渠道平铺在应用通知页，每行自带开关
INLINE_PAGE = '''<hierarchy><node>
  <node text="拼多多" bounds="[100,120][600,200]"/>
  <node clickable="true" bounds="[0,640][1280,720]">
    <node text="显示通知" bounds="[60,650][600,710]"/>
    <node class="android.widget.Switch" checkable="true" checked="true" bounds="[1050,650][1160,710]"/>
  </node>
  <node clickable="true" bounds="[0,890][1280,970]">
    <node text="一般通知" bounds="[60,900][600,960]"/>
    <node class="android.widget.Switch" checkable="true" checked="true" bounds="[1080,900][1190,960]"/>
  </node>
  <node clickable="true" bounds="[0,1084][1280,1164]">
    <node text="营销通知" bounds="[60,1094][600,1154]"/>
    <node class="android.widget.Switch" checkable="true" checked="true" bounds="[1080,1094][1190,1154]"/>
  </node>
</node></hierarchy>'''


class PageIdentityTests(unittest.TestCase):
    def test_honor_systemmanager_channel_page_is_trusted(self):
        # #86 PTP-AN00 实测 Activity
        p = page(CHANNEL_PAGE, "com.hihonor.systemmanager/com.hihonor.notificationmanager.ui.NotificationSettingsActivity")
        self.assertEqual(chan.channel_switch(p, "营销通知")[0], "允许通知")

    def test_huawei_and_short_activity_names(self):
        for focus in ("com.huawei.systemmanager/com.huawei.notificationmanager.ui.NotificationSettingsActivity",
                      "com.oplus.notificationmanager/.ChannelNotificationSettingsActivity"):
            p = page(CHANNEL_PAGE, focus)
            self.assertIsNotNone(chan.channel_switch(p, "营销通知"), focus)

    def test_lookalike_hosts_are_refused(self):
        for focus in ("com.hihonor.systemmanager/com.hihonor.systemmanager.MainActivity",
                      "com.example.systemmanager/com.hihonor.notificationmanager.ui.NotificationSettingsActivity",
                      "com.hihonor.systemmanager/com.hihonor.notificationmanager.ui.NotificationSettingsActivityX.Evil"):
            p = page(CHANNEL_PAGE, focus)
            self.assertIsNone(chan.channel_switch(p, "营销通知"), focus)

    def test_samsung_header_title_and_switchbar_label(self):
        # #95：标题在 entity_header_title，y≈577/2340；开关只有 content-desc「允许通知」
        p = page('''<hierarchy><node>
          <node text="通知类别" bounds="[79,150][600,230]"/>
          <node resource-id="com.android.settings:id/entity_header_title" text="营销信息" bounds="[79,577][1001,666]"/>
          <node bounds="[0,800][1080,960]">
            <node text="开" bounds="[60,840][300,920]"/>
            <node resource-id="com.android.settings:id/sesl_switchbar_switch" class="android.widget.Switch"
                  content-desc="允许通知" checkable="true" checked="true" bounds="[900,840][1040,920]"/>
          </node>
        </node></hierarchy>''', "com.android.settings/com.android.settings.SubSettings")
        sw = chan.channel_switch(p, "营销信息")
        self.assertIsNotNone(sw)
        self.assertEqual(sw[2], (970, 880))

    def test_low_title_without_header_id_is_still_refused(self):
        p = page(CHANNEL_PAGE.replace("[100,120][600,200]", "[100,700][600,780]"),
                 "com.android.settings/com.android.settings.SubSettings")
        self.assertIsNone(chan.channel_switch(p, "营销通知"))


class InlineChannelTests(unittest.TestCase):
    focus = "com.android.settings/com.android.settings.Settings$AppNotificationSettingsActivity"

    def test_inline_row_switch_is_picked_by_exact_title(self):
        p = page(INLINE_PAGE, self.focus, w=1280, h=2800)
        self.assertEqual(chan.page_switch(p, "营销通知"), ("营销通知", True, (1135, 1124)))

    def test_app_master_and_partial_titles_are_never_targets(self):
        p = page(INLINE_PAGE, self.focus, w=1280, h=2800)
        self.assertIsNone(chan.inline_switch(p, "显示通知"))
        self.assertIsNone(chan.inline_switch(p, "营销"))

    def test_duplicate_titles_are_ambiguous(self):
        xml = INLINE_PAGE.replace("一般通知", "营销通知")
        p = page(xml, self.focus, w=1280, h=2800)
        self.assertIsNone(chan.inline_switch(p, "营销通知"))

    def test_app_page_fallback_uses_inline_row_without_navigation_click(self):
        p = page(INLINE_PAGE, self.focus, w=1280, h=2800)
        with patch.object(chan.time, "sleep"):
            self.assertEqual(chan.via_app_page(p, "com.xunmeng.pinduoduo", "营销通知")[2], (1135, 1124))
        p.click.assert_not_called()


def snap(target_on=True, other_on=True, app_off=False):
    return ({("com.example", "promo"): ("营销通知", 3 if target_on else 0, False),
             ("com.example", "order"): ("订单通知", 3 if other_on else 0, False)}, {"com.example": app_off})


@patch.object(chan.time, "sleep")
class SideEffectTests(unittest.TestCase):
    def phone(self):
        return page(CHANNEL_PAGE, "com.android.settings/.Settings$ChannelNotificationSettingsActivity")

    def test_other_channel_change_is_undone_and_stops_batch(self, _sleep):
        p = self.phone()
        def flip(*_):
            for n in p.tree().iter():
                if n.get("checkable") == "true":
                    n.set("checked", "false" if n.get("checked") == "true" else "true")
        p.click.side_effect = flip
        with patch.object(chan, "parse", side_effect=[snap(), snap(target_on=False, other_on=False)]):
            with self.assertRaisesRegex(chan.StopBatch, "订单通知.*已点回"):
                chan.toggle(p, "com.example", "promo", False, "营销通知")
        self.assertEqual(p.click.call_count, 2)

    def test_app_master_change_still_stops_batch(self, _sleep):
        p = self.phone()
        with patch.object(chan, "parse", side_effect=[snap(), snap(app_off=True)]):
            with self.assertRaisesRegex(RuntimeError, "应用通知总开关"):
                chan.toggle(p, "com.example", "promo", False, "营销通知")

    def test_listed_channels_merged_into_one_switch_are_allowed(self, _sleep):
        p = self.phone()
        allowed = {("com.example", "promo"), ("com.example", "order")}
        with patch.object(chan, "parse", side_effect=[snap(), snap(target_on=False, other_on=False)]):
            self.assertIsNone(chan.toggle(p, "com.example", "promo", False, "营销通知", allowed))

    def test_unconfirmed_page_reports_where_it_stopped(self, _sleep):
        p = self.phone()
        p.focus.return_value = "com.vendor.notify/.UnknownPage"
        with patch.object(chan, "parse", return_value=snap()), patch.object(chan, "via_app_page", return_value=None):
            self.assertIn("停在 com.vendor.notify/.UnknownPage", chan.toggle(p, "com.example", "promo", False, "营销通知"))

    def test_batch_stops_after_stopbatch(self, _sleep):
        items = [("com.example", "promo", "营销通知"), ("com.example", "news", "资讯")]
        data = {("com.example", "promo"): ("营销通知", 3, False), ("com.example", "news"): ("资讯", 3, False)}
        with patch.object(chan, "load", return_value=items), patch.object(chan, "parse", return_value=(data, {})), \
             patch.object(chan, "Phone"), patch.object(chan, "keep_awake", return_value=None), \
             patch.object(chan, "toggle", side_effect=chan.StopBatch("点错了")) as toggle, \
             patch.object(sys, "argv", ["chan_fast.py", "-s", "test", "off", "x.tsv"]), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            with self.assertRaises(SystemExit):
                chan.main()
        toggle.assert_called_once()
        self.assertIn("点错了", out.getvalue())


DUMP = """PackagePreferences:
  AppSettings: com.ss.android (10234) importance=UNSPECIFIED userLockedFields=0
    NotificationChannel{mId='promo', mName=营销推广, mDescription=, mImportance=0, mBypassDnd=false, mDeleted=false}
  AppSettings: com.ss.android (1010234) importance=UNSPECIFIED userLockedFields=0
    NotificationChannel{mId='promo', mName=营销推广, mDescription=, mImportance=3, mBypassDnd=false, mDeleted=false}
  AppSettings: com.samsung.app (10111) importance=UNSPECIFIED
    NotificationChannel{mId='com.se...', mName=优惠, mDescription=, mImportance=3, mBypassDnd=false, mDeleted=false}
  AppSettings: com.dual.only (99910099) importance=NONE
    NotificationChannel{mId='x', mName=活动, mDescription=, mImportance=3, mBypassDnd=false, mDeleted=false}
"""


class ParseTests(unittest.TestCase):
    def test_other_user_spaces_do_not_override_owner(self):
        # #95 / 小米双开：另一空间同包名同渠道仍开着，不能当成机主空间没关
        d, app_off = chan.parse(types.SimpleNamespace(d=types.SimpleNamespace(
            shell=lambda *a, **k: types.SimpleNamespace(output=DUMP))))
        self.assertEqual(d[("com.ss.android", "promo")][1], 0)
        self.assertNotIn(("com.dual.only", "x"), d)
        self.assertNotIn("com.dual.only", app_off)

    def test_truncated_ids_are_left_out_of_scan(self):
        reader = types.SimpleNamespace(shell=lambda *a, **k: types.SimpleNamespace(output=DUMP))
        reader.d = reader
        err = io.StringIO()
        with patch.object(chan, "ShellPhone", return_value=reader), \
             patch.object(sys, "argv", ["chan_fast.py", "-s", "test", "scan"]), \
             contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(err):
            chan.main()
        self.assertNotIn("com.se...", out.getvalue())
        self.assertIn("缩略", err.getvalue())


class LockedChannelTests(unittest.TestCase):
    DUMP = """PackagePreferences:
  AppSettings: com.motorola.sim (1001) importance=DEFAULT userSet=false fixedImportance=true
    NotificationChannel{mId='sim_promo', mName=智能 SIM 推荐通知, mDescription=, mImportance=3, mBlockableSystem=false, mDeleted=false}
  AppSettings: com.example (10200) importance=DEFAULT
    NotificationChannel{mId='promo', mName=活动优惠, mDescription=, mImportance=3, mBlockableSystem=false, mDeleted=false}
"""

    def test_scan_leaves_out_system_locked_channels(self):
        # #134：系统锁定的渠道开关是灰的，列进清单只会报「状态未改变」
        reader = types.SimpleNamespace(shell=lambda *a, **k: types.SimpleNamespace(output=self.DUMP))
        reader.d = reader
        with patch.object(chan, "ShellPhone", return_value=reader), \
             patch.object(sys, "argv", ["chan_fast.py", "-s", "test", "scan"]), \
             contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            chan.main()
        self.assertEqual(out.getvalue(), "com.example\tpromo\t活动优惠\n")
        self.assertIn("系统锁定", err.getvalue())

    def test_greyed_switch_is_reported_without_clicking(self):
        p = page(CHANNEL_PAGE.replace('checked="true"', 'checked="true" enabled="false"'),
                 "com.android.settings/.Settings$ChannelNotificationSettingsActivity")
        with patch.object(chan, "parse", return_value=snap()), patch.object(chan.time, "sleep"):
            self.assertIn("系统锁定", chan.toggle(p, "com.example", "promo", False, "营销通知"))
        p.click.assert_not_called()


class LockScreenTests(unittest.TestCase):
    def test_other_true_fields_on_the_line_are_not_a_lock(self):
        # #115 跟帖：HyperOS 3 全程解锁，30 个渠道都被判成「手机锁屏了」
        p = fast.Phone.__new__(fast.Phone)
        p.d = Mock()
        p.d.shell.return_value = types.SimpleNamespace(output="    isKeyguardShowing=false mKeyguardOccluded=true\n")
        self.assertFalse(p.locked())
        p.d.shell.return_value = types.SimpleNamespace(output="    isKeyguardShowing=true\n")
        self.assertTrue(p.locked())


class XiaomiInputTests(unittest.TestCase):
    MIUI = ("java.lang.SecurityException: Injecting to another application requires INJECT_EVENTS permission\n"
            "\tat android.os.Parcel.createExceptionOrNull")

    def test_blocked_click_names_the_security_setting(self):
        p = page("<hierarchy/>", "x/y")
        del p.click
        p.d.window_size.return_value = (1080, 2340)
        p.d.shell.return_value = types.SimpleNamespace(output=self.MIUI, exit_code=1)
        with self.assertRaisesRegex(RuntimeError, "USB 调试（安全设置）"):
            p.click(500, 500)

    def test_status_probe_only_runs_for_xiaomi_family(self):
        with patch.object(run, "sh_all", return_value=self.MIUI) as sh_all:
            self.assertTrue(run.input_blocked("s", "Redmi"))
            self.assertFalse(run.input_blocked("s", "OPPO"))
        sh_all.assert_called_once_with("s", "input keyevent 0")
        self.assertFalse(troubleshooting.input_blocked(None))


class AdbLinkTests(unittest.TestCase):
    def test_client_errors_are_recognised_but_remote_stderr_is_not(self):
        self.assertTrue(adb_link.client_gone("adb.exe: device 'ABC' not found"))
        self.assertTrue(adb_link.client_gone("error: device offline"))
        self.assertFalse(adb_link.client_gone("/system/bin/sh: pidof: not found"))
        self.assertTrue(adb_link.lib_gone("AdbError: device '<序列号>' not found"))

    def test_sh_retries_once_after_device_returns(self):
        gone = subprocess.CompletedProcess([], 1, "", "adb: device 'S' not found")
        ok = subprocess.CompletedProcess([], 0, "M2211\n", "")
        with patch.object(run.subprocess, "run", side_effect=[gone, ok]), \
             patch.object(adb_link, "wait_for", return_value=True) as wait:
            self.assertEqual(run.sh("S", "getprop ro.product.model"), "M2211")
        wait.assert_called_once()

    def test_sh_stops_with_hint_instead_of_returning_empty(self):
        # #147：以前读到空型号，备份目录成了「-时间」，后面几步还显示成功
        gone = subprocess.CompletedProcess([], 1, "", "adb: device 'S' not found")
        with patch.object(run.subprocess, "run", return_value=gone), patch.object(adb_link, "wait_for", return_value=False):
            with self.assertRaises(SystemExit) as raised:
                run.sh("S", "getprop ro.product.model")
        self.assertIn("手机助手", str(raised.exception.code))

    def test_engine_shell_waits_then_marks_lost(self):
        p = fast.Phone.__new__(fast.Phone)
        p.serial, p.lost = "S", False
        p._shell = Mock(side_effect=Exception("device 'S' not found"))
        with patch.object(adb_link, "wait_for", return_value=False):
            with self.assertRaises(adb_link.DeviceLost):
                p._resilient_shell("dumpsys window")
            with self.assertRaises(adb_link.DeviceLost):
                p._resilient_shell("dumpsys window")
        self.assertEqual(p._shell.call_count, 1)          # 已确认断开后不再每条命令等 15 秒

    def test_engine_shell_recovers_from_short_drop(self):
        p = fast.Phone.__new__(fast.Phone)
        p.serial, p.lost = "S", False
        p._shell = Mock(side_effect=[Exception("device 'S' not found"), types.SimpleNamespace(output="ok")])
        with patch.object(adb_link, "wait_for", return_value=True):
            self.assertEqual(p._resilient_shell("echo").output, "ok")


class KeepAwakeTests(unittest.TestCase):
    def test_failed_write_warns_and_returns_original(self):
        calls = []
        def shell(cmd, timeout=60):
            calls.append(cmd)
            if "put" in cmd:
                raise RuntimeError("adb 读取失败：SecurityException")
            return types.SimpleNamespace(output="0\n")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(chan.keep_awake(types.SimpleNamespace(shell=shell)), "0")
        self.assertIn("插电常亮没有设上", out.getvalue())


class GuiTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("aac_gui_1027", ROOT / "gui/app.py")
        self.app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.app)

    def test_usb_hint_explains_missing_debug_interface_and_driver(self):
        self.assertIn("还没打开", self.app.usb_hint([("三星", "Galaxy S25", "OK", False)]))
        self.assertIn("三星", self.app.usb_hint([("三星", "Galaxy S25", "OK", False)]))
        hint = self.app.usb_hint([("荣耀", "ADB Interface", "Error", True)])
        self.assertIn("驱动没有装好", hint)
        self.assertIn("仅充电模式下允许 ADB 调试", hint)
        self.assertEqual(self.app.usb_hint([]), "")

    def test_diagnostics_include_device_count_and_other_adb(self):
        api = self.app.Api()
        api.adb = "/opt/tools/adb"
        api.last_devices = "List of devices attached\nABC123\tunauthorized usb:1-1\n"
        with patch.object(self.app, "other_adb", return_value=["/opt/tools/adb", "C:/Phone/Helper/adb.exe"]), \
             patch.object(self.app, "usb_phones", return_value=[]), patch.object(api, "_adb", return_value="Android Debug Bridge"):
            report = api.diagnostics()
        self.assertIn("adb 设备：1 台（unauthorized）", report)
        self.assertIn("C:/Phone/Helper/adb.exe", report)
        self.assertNotIn("ABC123", report)

    def test_old_adb_on_path_is_not_used(self):
        # #25 #75：PATH 里的 1.0.32（手机助手自带）被客户端拿来用，挂起、快应用全部失败
        old = subprocess.CompletedProcess([], 0, "Android Debug Bridge version 1.0.32\nRevision 09a0d98bebce-android\n", "")
        new = subprocess.CompletedProcess([], 0, "Android Debug Bridge version 1.0.41\nVersion 36.0.0-13206524\n", "")
        with patch.object(self.app.subprocess, "run", return_value=old):
            self.assertFalse(self.app.adb_ok("adb"))
        with patch.object(self.app.subprocess, "run", return_value=new):
            self.assertTrue(self.app.adb_ok("adb"))

    @unittest.skipUnless(sys.platform == "win32", "Windows 剪贴板")
    def test_windows_clipboard_round_trips_chinese(self):
        import ctypes
        text = "## 描述\n关闭营销通知失败 ✗"
        try:
            self.app.win_clipboard(text)
        except OSError as e:
            self.skipTest(f"剪贴板不可用：{e}")
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        user32.GetClipboardData.restype = ctypes.c_void_p
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        self.assertTrue(user32.OpenClipboard(None))
        try:
            handle = user32.GetClipboardData(13)
            pointer = kernel32.GlobalLock(handle)
            value = ctypes.wstring_at(pointer)
            kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
        self.assertEqual(value, text)


if __name__ == "__main__":
    unittest.main()
