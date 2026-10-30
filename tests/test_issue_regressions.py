"""社区反馈回归：不用手机，模拟页面与系统回读，不以 UI 状态代替执行结果。"""
import contextlib
import importlib.util
import io
import json
import ntpath
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tool"))
import adb_link
import chan_fast as chan
import fast
import run


def channel_phone():
    p = fast.Phone.__new__(fast.Phone)
    p.link = fast.adb_link.Connection("test")
    p.W, p.H, p.log = 1080, 1920, False
    p.d = Mock()
    p.locked = Mock(return_value=False)
    p.focus = Mock(return_value="com.android.settings/.Settings$ChannelNotificationSettingsActivity")
    p.confirm = Mock()
    p.click = Mock()
    p.tree = Mock(return_value=ET.fromstring('''<hierarchy><node>
      <node text="营销" bounds="[100,80][600,180]"/>
      <node bounds="[0,300][1080,410]">
        <node text="允许通知" bounds="[60,320][600,390]"/>
        <node class="android.widget.Switch" checked="true" checkable="true" bounds="[900,320][1040,390]"/>
      </node>
    </node></hierarchy>'''))
    return p


def snapshot(on=True, app_off=False):
    return {("com.example", "promo"): ("营销", 3 if on else 0, False)}, {"com.example": app_off}


class ShellPipeTests(unittest.TestCase):
    """#205：管道末端提前退出（grep -m / head -n）→ dumpsys 收到 SIGPIPE → adbutils 判
    「shell output invalid」，chan-off 整段中断。末端必须把整条流读完。"""

    # 管道末端只要提前退出就会触发 SIGPIPE：grep -m N、head（-N 或 -n N）、sed 'Nq'
    EARLY_EXIT = re.compile(r"grep\s+-m\s*\d|\|\s*head\b|\|\s*sed\s+['\"]?\d+q")

    def dumpsys_commands(self):
        calls = []
        p = fast.Phone.__new__(fast.Phone)
        p.link = fast.adb_link.Connection("test")
        p.d = Mock()
        p.d.shell.side_effect = lambda cmd, *a, **k: (calls.append(cmd), types.SimpleNamespace(output=""))[1]
        p.focus()
        chan.notifications_denied(p, "com.example")
        return calls

    def test_dumpsys_pipelines_read_to_the_end(self):
        for cmd in self.dumpsys_commands() + [adb_link.KEYGUARD_CMD]:
            with self.subTest(cmd=cmd):
                self.assertNotRegex(cmd, self.EARLY_EXIT)

    def test_focus_uses_first_match_when_the_whole_stream_is_read(self):
        # sed 把整条流读完后截断到前几行，输出仍可能有多条匹配；取第一行才是原来的语义
        p = fast.Phone.__new__(fast.Phone)
        p.link = fast.adb_link.Connection("test")
        p.d = Mock()
        p.d.shell.return_value = types.SimpleNamespace(output=(
            "  mCurrentFocus=Window{1 u0 com.a/.A}\n  mCurrentFocus=Window{2 u0 com.b/.B}\n"))
        self.assertEqual(p.focus(), "com.a/.A")


class ScreenshotTests(unittest.TestCase):
    def test_partial_bounds_do_not_read_outside_image(self):
        image = Image.new("RGB", (100, 100), "blue")
        self.assertIsNone(fast.Phone._pixel_on(image, 70, 70, 160, 120))
        self.assertIsNone(fast.Phone._pixel_on(image, -10, 0, 10, 10))
        self.assertTrue(fast.Phone._pixel_on(image, 70, 70, 100, 100))

    def test_resolution_mismatch_is_unknown_not_off(self):
        p = channel_phone()
        p.d.screenshot.return_value = Image.new("RGB", (540, 960))
        root = ET.fromstring('<hierarchy><node resource-id="app:id/switch" clickable="true" bounds="[900,300][1040,400]"/></hierarchy>')
        self.assertEqual(p.switches(root), [])


@patch.object(chan.time, "sleep")
class ChannelTests(unittest.TestCase):
    def test_bom_and_crlf_do_not_drop_first_channel(self, _sleep):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "channels.tsv")
            path.write_bytes("\ufeffcom.example\tpromo\t营销\r\n".encode())
            self.assertEqual(chan.load(path), [("com.example", "promo", "营销")])

    def test_malformed_channel_list_is_reported(self, _sleep):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "channels.tsv")
            path.write_text("com.example\n")
            with self.assertRaisesRegex(ValueError, "第 1 行"):
                chan.load(path)

    def test_channel_list_with_trailing_spaces_is_normalized(self, _sleep):
        # #194 纵横读屏：清单里同一渠道带尾空格出现两次，后一行被报「未确认」，收尾误报仍开着 1 个
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "channels.tsv")
            path.write_text("com.example\tpromo \ncom.example\tpromo\t营销 \n", encoding="utf-8")
            self.assertEqual(chan.load(path), [("com.example", "promo", "营销")])

    def test_dump_ids_with_trailing_spaces_are_one_channel(self, _sleep):
        # 系统回读里同一渠道可能带尾随空格；内部键必须一致，否则 load 后的 ID 查不到状态
        p = channel_phone()
        p.d.shell.return_value.output = """PackagePreferences:
      AppSettings: com.zongheng.reader importance=DEFAULT
        NotificationChannel{mId='flhd', mName=福利活动, mDescription=null, mImportance=0, mDeleted=false}
        NotificationChannel{mId='flhd ', mName=福利活动 , mDescription=null, mImportance=3, mDeleted=false}
    """
        d, _ = chan.parse(p)
        self.assertEqual(list(d), [("com.zongheng.reader", "flhd")])
        self.assertEqual(d[("com.zongheng.reader", "flhd")][:2], ("福利活动", 3))

    def test_deleted_duplicate_does_not_override_live_channel(self, _sleep):
        p = channel_phone()
        p.d.shell.return_value.output = """PackagePreferences:
      AppSettings: com.example importance=DEFAULT
        NotificationChannel{mId='promo', mName=活动优惠, mDescription=null, mImportance=0, mDeleted=false}
        NotificationChannel{mId='promo ', mName=活动优惠 , mDescription=null, mImportance=3, mDeleted=true}
    """
        d, _ = chan.parse(p)
        self.assertEqual(d[("com.example", "promo")], ("活动优惠", 0, False))

    def test_unspecified_importance_keeps_channel_on(self, _sleep):
        # 0 才是已屏蔽；-1000（未指定）名义上仍开着，合并时不能被已关的那条盖掉
        p = channel_phone()
        p.d.shell.return_value.output = """PackagePreferences:
      AppSettings: com.example importance=DEFAULT
        NotificationChannel{mId='promo', mName=营销, mDescription=null, mImportance=0, mDeleted=false}
        NotificationChannel{mId='promo ', mName=营销 , mDescription=null, mImportance=-1000, mDeleted=false}
    """
        d, _ = chan.parse(p)
        self.assertEqual(d[("com.example", "promo")][1], -1000)
        self.assertEqual(chan.state(d, {}, "com.example", "promo"), "ON")

    def test_deleted_duplicate_does_not_mark_channel_locked(self, _sleep):
        p = channel_phone()
        p.d.shell.return_value.output = """PackagePreferences:
      AppSettings: com.example (10001) importance=DEFAULT fixedImportance=true
        NotificationChannel{mId='promo', mName=活动优惠, mDescription=null, mImportance=3, mDeleted=false}
        NotificationChannel{mId='promo ', mName=活动优惠 , mDescription=null, mImportance=3, mDeleted=true, mBlockableSystem=false}
    """
        locked = set()
        chan.parse(p, locked)
        self.assertEqual(locked, set())

    def test_repeated_rows_do_not_count_as_still_on(self, _sleep):
        result = types.SimpleNamespace(returncode=0, stderr="", stdout="""PackagePreferences:
      AppSettings: com.example importance=DEFAULT
        NotificationChannel{mId='promo', mName=营销, mDescription=null, mImportance=3, mDeleted=false}
    """)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "channels.tsv")
            path.write_text("com.example\tpromo \t营销 \ncom.example\tpromo\t营销\n", encoding="utf-8")
            with patch.object(subprocess, "run", return_value=result), \
                 patch.object(sys, "argv", ["chan_fast.py", "-s", "test", "verify", str(path)]), \
                 contextlib.redirect_stdout(io.StringIO()) as out:
                chan.main()
        # 渠道仍开着：按渠道计 1 个，重复行不能算成 2 个
        self.assertIn("营销渠道仍开着: 1 个", out.getvalue())
        self.assertNotIn("营销渠道仍开着: 2 个", out.getvalue())

    def test_scan_lists_repeated_channel_once(self, _sleep):
        result = types.SimpleNamespace(returncode=0, stderr="", stdout="""PackagePreferences:
      AppSettings: com.zongheng.reader importance=DEFAULT
        NotificationChannel{mId='flhd', mName=福利活动, mDescription=null, mImportance=3, mDeleted=false}
        NotificationChannel{mId='flhd ', mName=福利活动 , mDescription=null, mImportance=3, mDeleted=false}
    """)
        with patch.object(subprocess, "run", return_value=result), \
             patch.object(chan, "app_labels", return_value={}), \
             patch.object(sys, "argv", ["chan_fast.py", "-s", "test", "scan"]), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            chan.main()
        self.assertEqual(out.getvalue(), "com.zongheng.reader\tflhd\t福利活动\n")

    def test_notification_dump_failure_is_not_empty_success(self, _sleep):
        p = channel_phone()
        p.d.shell.return_value.output = "Permission denied"
        with self.assertRaisesRegex(RuntimeError, "读不到"):
            chan.parse(p)

    def test_app_master_switch_is_not_channel_switch(self, _sleep):
        p = channel_phone()
        p.focus.return_value = "com.android.settings/.Settings$AppNotificationSettingsActivity"
        self.assertIsNone(chan.channel_switch(p, "营销"))

    def test_coloros14_separate_channel_page_is_supported(self, _sleep):
        p = channel_phone()
        p.focus.return_value = "com.oplus.notificationmanager/com.oplus.notificationmanager.ChannelNotificationSettingsActivity"
        self.assertEqual(chan.channel_switch(p, "营销")[0], "允许通知")
        self.assertIsNone(chan.channel_switch(p, "其他渠道"))

    def test_coloros14_app_master_page_remains_forbidden(self, _sleep):
        p = channel_phone()
        p.focus.return_value = "com.oplus.notificationmanager/com.oplus.notificationmanager.AppNotificationSettingsActivity"
        self.assertIsNone(chan.channel_switch(p, "营销"))

    def test_coloros14_unknown_page_or_lookalike_package_is_not_trusted(self, _sleep):
        p = channel_phone()
        for focus in (
            "com.oplus.notificationmanager/com.oplus.notificationmanager.OtherActivity",
            "com.example.notificationmanager/com.oplus.notificationmanager.ChannelNotificationSettingsActivity",
        ):
            p.focus.return_value = focus
            self.assertIsNone(chan.channel_switch(p, "营销"))

    def test_same_text_in_unrelated_page_cannot_authorize_click(self, _sleep):
        p = channel_phone()
        p.focus.return_value = "com.example/.MarketingSettings"
        with patch.object(chan, "parse", return_value=snapshot()), patch.object(chan, "via_app_page", return_value=None):
            self.assertEqual(chan.toggle(p, "com.example", "promo", False, "营销").kind, chan.NOT_CONFIRMED)
        p.click.assert_not_called()

    def test_no_fallback_to_first_switch(self, _sleep):
        p = channel_phone()
        for node in p.tree().iter():
            if node.get("text") == "允许通知":
                node.set("text", "智能静默")
        self.assertIsNone(chan.channel_switch(p, "营销"))

    def test_vivo_app_wide_notification_page_is_refused(self, _sleep):
        # vivo 应用总页与渠道页同一个 Activity；总页有多个开关，「允许通知」管整个 App，不能点
        p = channel_phone()
        p.focus.return_value = ("com.vivo.systemuiplugin/com.vivo.systemui.statusbar.notification"
                                ".settings.channels.NotificationSettingsActivity")
        root = p.tree()
        extra = ET.fromstring('''<node bounds="[0,500][1080,610]">
          <node text="静默通知" bounds="[60,520][600,590]"/>
          <node class="android.widget.Switch" checked="false" checkable="true" bounds="[900,520][1040,590]"/></node>''')
        root[0].append(extra)
        with patch.object(chan, "parse", return_value=snapshot()), patch.object(chan, "via_app_page", return_value=None):
            self.assertEqual(chan.toggle(p, "com.example", "promo", False, "营销").kind, chan.NOT_CONFIRMED)
        p.click.assert_not_called()

    def test_vivo_channel_page_needs_app_title_from_app_page(self, _sleep):
        # X300 Ultra 实测：总页与渠道页同一个 Activity，只能靠顶栏标题区分
        p = channel_phone()
        p.focus.return_value = ("com.vivo.systemuiplugin/com.vivo.systemui.statusbar.notification"
                                ".settings.channels.NotificationSettingsActivity")
        for node in p.tree().iter():
            if node.get("text") == "营销":
                node.set("resource-id", "android:id/originui_vtoolbar_normal_title_rom14_0")
        p.vivo_app = None
        self.assertIsNone(chan.channel_switch(p, "营销"))          # 没经过总页：不知道 App 名
        p.vivo_app = "示例应用"
        self.assertEqual(chan.channel_switch(p, "营销")[0], "允许通知")
        p.vivo_app = "营销"
        self.assertIsNone(chan.channel_switch(p, "营销"))          # App 与渠道同名：无法区分
        p.vivo_app = "示例应用"
        p.focus.return_value = "com.vivo.systemuiplugin/.OtherActivity"
        self.assertIsNone(chan.channel_switch(p, "营销"))

    def test_last_click_is_verified_not_reported_as_failure(self, _sleep):
        p = channel_phone()
        with patch.object(chan, "parse", side_effect=[snapshot(), snapshot(), snapshot(), snapshot(False)]):
            self.assertEqual(chan.toggle(p, "com.example", "promo", False, "营销").kind, chan.DONE)
        self.assertEqual(p.click.call_count, 3)

    def test_changed_page_does_not_reuse_coordinates(self, _sleep):
        p = channel_phone()
        p.click.side_effect = lambda *xy: p.tree.__setattr__("return_value", ET.fromstring("<hierarchy/>"))
        with patch.object(chan, "parse", return_value=snapshot()):
            self.assertIn("已变化", chan.toggle(p, "com.example", "promo", False, "营销").detail)
        self.assertEqual(p.click.call_count, 1)

    def test_app_notification_change_aborts_batch(self, _sleep):
        p = channel_phone()
        with patch.object(chan, "parse", side_effect=[snapshot(), snapshot(app_off=True)]):
            with self.assertRaisesRegex(RuntimeError, "总开关发生变化"):
                chan.toggle(p, "com.example", "promo", False, "营销")
        p.click.assert_called_once()

    def test_ui_only_success_is_not_reported(self, _sleep):
        p = channel_phone()
        for node in p.tree().iter():
            if node.get("checkable") == "true":
                node.set("checked", "false")
        with patch.object(chan, "parse", return_value=snapshot()):
            self.assertIn("不一致", chan.toggle(p, "com.example", "promo", False, "营销").detail)
        p.click.assert_not_called()

    def test_app_page_fallback_navigates_then_checks_channel(self, _sleep):
        p = channel_phone()
        p.focus.return_value = "com.android.settings/.Settings$AppNotificationSettingsActivity"
        channel_root = p.tree()
        p.tree.return_value = ET.fromstring('''<hierarchy><node>
          <node text="示例应用" bounds="[100,80][600,180]"/>
          <node clickable="true" bounds="[0,600][1080,710]">
            <node text="营销" bounds="[60,620][600,690]"/>
          </node>
        </node></hierarchy>''')
        def navigate(*_):
            p.tree.return_value = channel_root
            p.focus.return_value = "com.android.settings/.SubSettings"
        p.click.side_effect = navigate
        p.settle = Mock(return_value=True)
        self.assertEqual(chan.via_app_page(p, "com.example", "营销")[0], "允许通知")
        p.click.assert_called_once()

    def test_restore_failure_returns_nonzero(self, _sleep):
        with patch.object(chan, "Phone", return_value=channel_phone()), patch.object(chan, "keep_awake", return_value=None), \
             patch.object(chan, "load", return_value=[("com.example", "promo", "营销")]), \
             patch.object(chan, "parse", return_value=snapshot(False)), \
             patch.object(chan, "toggle", return_value=chan.Outcome(chan.NOT_CONFIRMED, "未确认渠道页")), \
             patch.object(sys, "argv", ["chan_fast.py", "-s", "test", "on", "channels.tsv"]), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                chan.main()
        self.assertEqual(raised.exception.code, 1)


class QuickappTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.backup = Path(self.directory.name, "vivo-test")
        self.backup.mkdir()
        self.value = "1"
        def shell(_serial, cmd):
            if "put secure" in cmd:
                self.value = cmd.split()[-1]
            return ""
        patches = [patch.object(run, "BACKUPS", self.directory.name),
                   patch.object(run, "latest_backup", return_value=str(self.backup)),
                   patch.object(run, "quickapp_switch", side_effect=lambda _: self.value),
                   patch.object(run, "sh", side_effect=shell)]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def test_close_repeat_backup_restore_preserves_original(self):
        run.set_quickapp_service("test-device")
        self.assertEqual(self.value, "0")
        first = self.backup / "quickapp-setting.json"
        original = first.read_text()
        new_backup = Path(self.directory.name, "vivo-later")
        new_backup.mkdir()
        with patch.object(run, "latest_backup", return_value=str(new_backup)):
            run.set_quickapp_service("test-device")
            self.assertEqual(first.read_text(), original)
            run.set_quickapp_service("test-device", restore=True)
        self.assertEqual(self.value, "1")
        self.assertFalse(first.exists())

    def test_already_disabled_never_creates_default_restore(self):
        self.value = "0"
        run.set_quickapp_service("test-device")
        with self.assertRaisesRegex(RuntimeError, "没有找到"):
            run.set_quickapp_service("test-device", restore=True)
        self.assertEqual(self.value, "0")

    def test_other_device_backup_cannot_be_restored(self):
        run.set_quickapp_service("another-device")
        with self.assertRaisesRegex(RuntimeError, "没有找到"):
            run.set_quickapp_service("test-device", restore=True)
        self.assertEqual(self.value, "0")

    def test_failed_write_keeps_original_and_reports_error(self):
        with patch.object(run, "sh", return_value="Permission denied"):
            with self.assertRaisesRegex(RuntimeError, "校验失败"):
                run.set_quickapp_service("test-device")
        self.assertEqual(json.loads((self.backup / "quickapp-setting.json").read_text())["original"], "1")

    def test_missing_service_switch_does_not_write(self):
        self.value = None
        with self.assertRaisesRegex(RuntimeError, "读不到"):
            run.set_quickapp_service("test-device")
        run.sh.assert_not_called()

    def test_service_disabled_is_closed_without_package_suspension(self):
        self.value = "0"
        with patch.object(run, "installed", side_effect=lambda _s, pkg: pkg == "com.vivo.hybrid"), \
             patch.object(run, "suspended", return_value=False):
            entries = run.quickapps("test-device")
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0]["closed"])
        self.assertFalse(entries[0]["suspended"])
        self.assertEqual(entries[0]["method"], "setting")

    def test_force_stop_follows_successful_suspend(self):
        events = []
        initial = {"pkg": "com.example.quick", "name": "测试快应用", "closed": False, "method": "suspend"}
        closed = dict(initial, closed=True)
        with patch.object(run, "quickapps", side_effect=[[initial], [closed]]), \
             patch.object(run, "suspended", return_value=True), patch.object(run, "record"), \
             patch.object(run, "sh_all", side_effect=lambda s, cmd: events.append(cmd) or "success"), \
             patch.object(run, "sh", side_effect=lambda s, cmd: events.append(cmd) or ""), \
             patch.object(sys, "argv", ["run.py", "-s", "test", "quickapp", "off"]), \
             contextlib.redirect_stdout(io.StringIO()):
            run.main()
        self.assertEqual(events, ["pm suspend --user 0 com.example.quick", "am force-stop --user 0 com.example.quick"])


class BackupTests(unittest.TestCase):
    def test_backup_path_on_another_windows_drive(self):
        with patch.object(run, "ROOT", r"D:\app"), \
             patch.object(run.os.path, "relpath", side_effect=ntpath.relpath), \
             patch.dict(os.environ, {"AAC_BACKUPS": ""}):
            self.assertEqual(run.display_backup_path(r"C:\backup\channels.tsv"), r"C:\backup\channels.tsv")

    def test_scan_failure_preserves_existing_channel_list(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "channels.tsv")
            path.write_text("original-list")
            with patch.object(run, "latest_backup", return_value=directory), \
                 patch.object(run.subprocess, "run", return_value=types.SimpleNamespace(returncode=1, stdout="", stderr="读取失败")), \
                 patch.object(sys, "argv", ["run.py", "-s", "test", "chan-scan"]), \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    run.main()
            self.assertEqual(raised.exception.code, 1)
            self.assertEqual(path.read_text(), "original-list")

    def test_package_backup_is_limited_to_owner(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(run, "latest_backup", return_value=directory), \
             patch.object(run, "info", return_value={"model": "test"}), \
             patch.object(run, "sh", side_effect=lambda _s, c: "package:com.example" if "list packages" in c else "") as shell, \
             patch.object(sys, "argv", ["run.py", "-s", "test", "backup"]), \
             contextlib.redirect_stdout(io.StringIO()):
            run.main()
        calls = [c.args[1] for c in shell.call_args_list if "pm list packages" in c.args[1]]
        self.assertEqual(calls[0], "pm list packages")          # 探活用完整清单，只有它不可能合法为空
        self.assertEqual(calls[1:], ["pm list packages --user 0 -s", "pm list packages --user 0 -3",
                                     "pm list packages --user 0 -d"])


class ExternalAdbServerTests(unittest.TestCase):
    """#293：复用了外部 adb server（Iriun 等），对方退出后整轮中断，
    而且 pm path 同样没输出，断连被报成「本机没有安装」，三段连报。"""

    def phone(self):
        p = fast.Phone.__new__(fast.Phone)
        p.link = fast.adb_link.Connection("test")
        p.serial, p.lost, p.W, p.H = "S", False, 1080, 1920
        p.log, p.miss, p.changed = False, 0, []
        p.d = Mock()
        p.d.app_stop = Mock()
        return p

    def test_disconnected_device_is_not_reported_as_missing_app(self):
        p = self.phone()
        p.d.shell.side_effect = [types.SimpleNamespace(exit_code=1, output=""),
                                 types.SimpleNamespace(exit_code=0, output="")]
        with patch.object(adb_link, "detached", return_value=True):
            with self.assertRaises(adb_link.DeviceLost) as raised:
                p.start("com.heytap.yoli")
        self.assertNotIn("没有安装", str(raised.exception))
        self.assertIn("手机助手", str(raised.exception))        # 完整排查说明只在这一处出现
        self.assertTrue(p.lost)

    def test_client_error_text_alone_identifies_the_disconnect(self):
        p = self.phone()
        p.d.shell.side_effect = [types.SimpleNamespace(exit_code=0, output="error: device 'S' not found"),
                                 types.SimpleNamespace(exit_code=0, output="")]
        with patch.object(adb_link, "detached") as detached:
            with self.assertRaises(adb_link.DeviceLost):
                p.start("com.heytap.yoli")
        detached.assert_not_called()                           # 输出已经说明是断连，不再多查一次

    def test_missing_app_is_still_named_when_phone_is_there(self):
        p = self.phone()
        p.d.shell.side_effect = [types.SimpleNamespace(exit_code=0, output="No activities found to run, monkey aborted."),
                                 types.SimpleNamespace(exit_code=0, output="")]
        with patch.object(adb_link, "detached", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "本机没有安装 com.heytap.yoli"):
                p.start("com.heytap.yoli")
        self.assertFalse(p.lost)

    def test_unknown_connection_state_is_not_reported_as_disconnect(self):
        # 找不到 adb、get-state 超时：只能算状态未知，不能把参考脚本里的「没装」报成断连。
        with patch.object(adb_link, "adb_path", return_value=None):
            self.assertFalse(adb_link.detached("S"))
        with patch.object(adb_link, "adb_path", return_value="/usr/bin/adb"), \
             patch.object(adb_link.subprocess, "run", side_effect=subprocess.TimeoutExpired("adb", 8)):
            self.assertFalse(adb_link.detached("S"))

    def test_client_answer_names_the_disconnect(self):
        with patch.object(adb_link, "adb_path", return_value="/usr/bin/adb"), \
             patch.object(adb_link.subprocess, "run", return_value=types.SimpleNamespace(
                 returncode=1, stdout="", stderr="adb: device 'S' not found")):
            self.assertTrue(adb_link.detached("S"))
        with patch.object(adb_link, "adb_path", return_value="/usr/bin/adb"), \
             patch.object(adb_link.subprocess, "run", return_value=types.SimpleNamespace(
                 returncode=0, stdout="device\n", stderr="")):
            self.assertFalse(adb_link.detached("S"))

    def test_lost_screen_library_error_marks_the_run_lost(self):
        p = self.phone()
        p.d.dump_hierarchy.side_effect = Exception("HTTPConnectionPool(host='127.0.0.1', port=5037): Max retries exceeded")
        with self.assertRaises(Exception):
            p.tree()
        self.assertTrue(p.lost)                                # 后面的段据此快速跳过

    def test_confirmed_loss_skips_remaining_steps_without_touching_adb(self):
        p = self.phone()
        p.lost = True
        for step in (lambda: p.start("com.heytap.yoli"), p.tree, p.focus, lambda: p.click(10, 10),
                     lambda: p._resilient_shell("dumpsys window")):
            with self.assertRaises(adb_link.DeviceLost) as raised:
                step()
            self.assertEqual(str(raised.exception), adb_link.REPEAT)   # 后面的段只报一句
        p.d.shell.assert_not_called()
        p.d.dump_hierarchy.assert_not_called()
        p.d.window_size.assert_not_called()
        p.d.app_stop.assert_not_called()





class PackageListTests(unittest.TestCase):
    """#192：HyperOS 4 上 `pm list packages` 任何参数都无输出且 exit 0；要回退 `cmd package list`。"""

    def test_pm_list_without_output_falls_back_to_cmd_package(self):
        with patch.object(run, "sh", side_effect=lambda _s, c: "package:com.example" if c.startswith("cmd package") else ""):
            self.assertEqual(run.pkg_list("test", "--user 0 -s"), "package:com.example")

    def test_pm_list_output_skips_the_fallback(self):
        with patch.object(run, "sh", return_value="package:com.example") as shell:
            self.assertEqual(run.pkg_list("test", "--user 0 -s"), "package:com.example")
        self.assertEqual([c.args[1] for c in shell.call_args_list], ["pm list packages --user 0 -s"])

    def test_backup_writes_package_lists_when_pm_list_is_silent(self):
        def shell(_s, cmd):
            if cmd.startswith("pm list packages"):
                return ""
            if cmd.endswith(" -d"):
                return "package:com.disabled"
            if "list packages" in cmd:
                return "package:com.system\npackage:com.user"
            return ""
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(run, "latest_backup", return_value=directory), \
             patch.object(run, "info", return_value={"model": "test"}), \
             patch.object(run, "sh", side_effect=shell), \
             patch.object(sys, "argv", ["run.py", "-s", "test", "backup"]), \
             contextlib.redirect_stdout(io.StringIO()):
            run.main()
            for name in ("sys.txt", "user.txt", "disabled.txt"):
                self.assertTrue(Path(directory, name).read_text(encoding="utf-8"), name)

    def test_backup_fails_when_both_paths_are_silent(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(run, "latest_backup", return_value=directory), \
             patch.object(run, "info", return_value={"model": "test"}), \
             patch.object(run, "sh", return_value=""), \
             patch.object(sys, "argv", ["run.py", "-s", "test", "backup"]), \
             contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                run.main()
            self.assertIn("读不到包列表", str(raised.exception.code))
            # 失败时不留半成品快照：后续步骤会把最新目录当成「改动前的快照」。
            self.assertEqual(os.listdir(directory), [])

    def test_backup_keeps_legitimately_empty_filtered_lists(self):
        def shell(_s, cmd):
            return "package:com.system" if cmd.endswith(" -s") or cmd == "pm list packages" else ""
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(run, "latest_backup", return_value=directory), \
             patch.object(run, "info", return_value={"model": "test"}), \
             patch.object(run, "sh", side_effect=shell), \
             patch.object(sys, "argv", ["run.py", "-s", "test", "backup"]), \
             contextlib.redirect_stdout(io.StringIO()):
            run.main()
            self.assertEqual(Path(directory, "sys.txt").read_text(encoding="utf-8"), "package:com.system")
            self.assertEqual(Path(directory, "user.txt").read_text(encoding="utf-8"), "")

    def test_package_list_error_text_is_kept_for_troubleshooting(self):
        def shell(_s, cmd):
            return "Error: Shell does not have permission to access user 666" if cmd.startswith("pm list") else ""
        with patch.object(run, "sh", side_effect=shell):
            self.assertIn("does not have permission", run.pkg_list("test", "--user 0 -d"))

    def test_manually_disabled_quickapp_is_closed_via_cmd_package(self):
        with patch.object(run, "installed", side_effect=lambda _s, pkg: pkg == "com.miui.hybrid"), \
             patch.object(run, "quickapp_switch", return_value=None), \
             patch.object(run, "suspended", return_value=False), \
             patch.object(run, "sh", side_effect=lambda _s, c: "package:com.miui.hybrid" if c.startswith("cmd package") else ""):
            entries = run.quickapps("test-device")
        self.assertTrue(entries[0]["closed"])

    def test_not_disabled_quickapp_stays_open(self):
        with patch.object(run, "installed", side_effect=lambda _s, pkg: pkg == "com.miui.hybrid"), \
             patch.object(run, "quickapp_switch", return_value=None), \
             patch.object(run, "suspended", return_value=False), \
             patch.object(run, "sh", return_value=""):
            entries = run.quickapps("test-device")
        self.assertFalse(entries[0]["closed"])


class DesktopTests(unittest.TestCase):
    def test_gui_smoke_output_works_with_non_utf8_console(self):
        spec = importlib.util.spec_from_file_location("aac_gui_test", ROOT / "gui/app.py")
        app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(app)
        buffer = io.BytesIO()
        stream = io.TextIOWrapper(buffer, encoding="ascii", newline="\n")
        with patch.object(sys, "stdout", stream), patch.object(sys, "stderr", stream):
            app._fix_stdio()
            print("GUI smoke: 页面通过")
            stream.flush()
        self.assertEqual(buffer.getvalue().decode("utf-8"), "GUI smoke: 页面通过\n")

    def test_failed_scan_reaches_gui_as_error(self):
        spec = importlib.util.spec_from_file_location("aac_gui_test", ROOT / "gui/app.py")
        app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(app)
        api = app.Api()
        api._run = Mock(return_value=("", "读取失败", 1))
        with tempfile.TemporaryDirectory() as directory, patch.object(app, "DATA", directory):
            self.assertEqual(api.chan_scan("test"), {"error": "读取失败", "detail": "读取失败"})

    def test_gui_loads_file_uri_without_http_server(self):
        spec = importlib.util.spec_from_file_location("aac_gui_test", ROOT / "gui/app.py")
        app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(app)
        fake = types.SimpleNamespace(create_window=Mock(), start=Mock())
        with patch.dict(sys.modules, {"webview": fake}), patch.object(app, "IS_WIN", True), \
             patch.object(sys, "argv", ["app.py"]):
            app.main()
        url = fake.create_window.call_args.args[1]
        self.assertTrue(url.startswith("file:///"))
        self.assertIn("index.html", url)
        self.assertFalse(fake.start.call_args.kwargs["http_server"])
        self.assertEqual(fake.start.call_args.kwargs["gui"], "edgechromium")


class RepeatedChannelNameTests(unittest.TestCase):
    """#287：华为 HarmonyOS 4 的应用通知页把分组名写在列表里，和渠道名同名。
    inline_switch 以前看到两处同名就放弃，其实只有一处带开关。"""

    APP = "com.android.settings/.Settings$AppNotificationSettingsActivity"

    PAGE = '''<hierarchy><node class="android.widget.FrameLayout" bounds="[0,0][1080,2340]">
      <node text="淘宝" bounds="[60,100][600,200]"/>
      <node class="androidx.recyclerview.widget.RecyclerView" scrollable="true" bounds="[0,300][1080,2200]">
        <node class="android.widget.LinearLayout" bounds="[40,700][1040,840]">
          <node text="营销通知" bounds="[80,720][500,800]"/>
          <node text="3 个渠道" bounds="[80,810][500,840]"/>
        </node>
        <node class="android.widget.LinearLayout" bounds="[40,880][1040,1080]">
          <node class="android.widget.LinearLayout" bounds="[80,900][800,1060]">
            <node text="营销通知" bounds="[80,920][500,980]"/>
          </node>
          <node class="com.huawei.uikit.hwswitch.widget.HwSwitch" checkable="true" checked="true" bounds="[900,940][1000,1020]"/>
        </node>
      </node>
    </node></hierarchy>'''

    def phone(self, page):
        p = fast.Phone.__new__(fast.Phone)
        p.link = fast.adb_link.Connection("test")
        p.W, p.H, p.log, p.sysui = 1080, 2340, False, False
        p.d = Mock()
        p.focus = Mock(return_value=self.APP)
        p.tree = Mock(return_value=ET.fromstring(page))
        return p

    def test_group_row_without_switch_does_not_block_the_channel_row(self):
        self.assertEqual(chan.inline_switch(self.phone(self.PAGE), "营销通知"), ("营销通知", True, (950, 980)))

    def test_two_rows_that_both_have_switches_are_still_refused(self):
        # 两个都合格时无从判断哪个是渠道行，只能放弃，不能猜
        page = self.PAGE.replace('<node text="3 个渠道" bounds="[80,810][500,840]"/>',
                                 '<node class="android.widget.Switch" checkable="true" checked="true"'
                                 ' bounds="[900,730][1000,810]"/>')
        p = self.phone(page)
        self.assertIsNone(chan.inline_switch(p, "营销通知"))
        self.assertIn("同名 2 行", p.why)


if __name__ == "__main__":
    unittest.main()
