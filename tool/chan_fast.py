#!/usr/bin/env python3
"""营销通知渠道（通用版，走 fast 引擎）。
  chan_fast.py -s SERIAL scan             只读：列出开着的、名字像营销的渠道（候选，人工挑）；第四列是应用名
                                          （读应用名时在 /data/local/tmp 临时放一个 3 KB 的文件，用完删掉）
  chan_fast.py -s SERIAL verify 清单.tsv   只读：清单里还开着几个
  chan_fast.py -s SERIAL off 清单.tsv      逐个打开渠道页关掉
  chan_fast.py -s SERIAL on  清单.tsv      还原
清单.tsv：包名<TAB>渠道id<TAB>说明[<TAB>应用名]，一行一个；# 开头是注释。
"""
import re, shlex, sys, time, os
from dataclasses import dataclass
for _st in (sys.stdout, sys.stderr):
    try:
        _st.reconfigure(encoding="utf-8", errors="replace")   # Windows 控制台默认不是 UTF-8
    except Exception:
        pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fast import Phone, ScreenLocked, pause_point
from row import PATH_DEPTH, bounds, own, path
from channel_policy import protected_channel
from troubleshooting import XIAOMI_INPUT
import adb_link
import wait


class ShellPhone(adb_link.Connection):
    """扫描和复查只读 adb，不启动手机端 UiAutomation。"""
    def __init__(self, serial):
        super().__init__(serial, sticky=False)          # 一个 reader 跑一整批：一次掉线不该毒掉后面的读取
        self.d = self

    def shell(self, command, timeout=60):
        result = super().shell(command, timeout=timeout)
        if result.returncode:
            raise RuntimeError("adb 读取失败：" + (result.stderr or result.stdout).strip())
        return result

    def push(self, local, remote, timeout=30):
        result = super().push(local, remote, timeout=timeout)
        if result.returncode:
            raise RuntimeError("adb 传文件失败：" + (result.stderr or result.stdout).strip())


LABELS_DEX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "applabels.dex")   # 源码在 applabels/
LABELS_REMOTE = "/data/local/tmp/aac-labels.dex"


def app_labels(reader, packages):
    """包名 → 手机上显示的应用名（跟随系统语言）。以前清单只有包名，用户认不出是哪个软件。
    在手机上跑一次 applabels.dex（只读，打印完退出，用完删掉）；读不到的不给，界面退回显示包名。"""
    packages = sorted({pk for pk in packages if re.fullmatch(r"[\w.]+", pk)})
    if not packages or not os.path.exists(LABELS_DEX):
        return {}
    out, pushed = {}, False
    try:
        reader.push(LABELS_DEX, LABELS_REMOTE)
        pushed = True
        for start in range(0, len(packages), 40):          # 老系统 adb 命令行有长度上限
            batch = " ".join(packages[start:start + 40])
            text = reader.shell(f"CLASSPATH={LABELS_REMOTE} app_process / aac.Labels {batch}", timeout=60).output
            for line in text.splitlines():
                pk, _, label = line.partition("\t")
                if pk in packages and label.strip():
                    out[pk] = label.strip()
    except Exception:
        pass                    # 只影响显示：读不到就显示包名，不让扫描失败
    finally:
        if pushed:
            try:
                reader.shell(f"rm -f {LABELS_REMOTE}")
            except Exception:
                pass
    return out

KW = re.compile(r"营销|活动|推荐|推广|热点|热门|资讯|新闻|福利|优惠|特惠|精选|精彩|运营|促销|红包|直播|种草|内容|头条|猜你|好物|权益|会员|签到|广告|recommend|promo|market|deal|news|topstory|upsell|offer", re.I)
SKIP = re.compile(r"下载|更新|安装|上传|订单|物流|快递|交易|支付|付款|\bpayments?\b|账号|安全|验证|通话|来电|消息|聊天|私信|评论|互动|提醒|闹钟|日程|天气预警|系统|前台|后台|服务运行|播放|媒体"
                  r"|热点和网络共享|智能热点|红包助手|盗窃|驾驶状态|权限建议|运营商|警告|告警|实时活动|赛事|护眼"
                  r"|上层显示"     # 「“钱包”正在其他应用的上层显示内容」是悬浮窗提示，名字带「内容」被误选（#115）
                  r"|提取|传输|已共享|正在进行", re.I)   # 识屏「内容提取」（系统锁定）、三星「内容已传输」等功能通知（错误日志 10-27）
RETRY_MAX = 10

# ---------- 一项的结局 ----------
# 每个出口返回一个 Outcome；怎么记账（算不算失败、要不要重试、算不算拨动了、复查是否豁免）
# 由下面的 RULES 表决定，不再由返回值的字符串形状暗示。detail 只给人看。
DONE = "done"                          # 达成目标（关掉或还原）
GREYED = "greyed"                      # 系统锁定了这个渠道：开关是灰的，点了也不会变
APP_DENIED = "app_denied"              # 应用通知整体关闭（POST_NOTIFICATIONS 被拒），渠道不会弹出
PROTECTED = "protected"                # 找机位一类功能通知，不动
NO_CHANNEL = "no_channel"              # 清单里的渠道在手机上不存在
DELETED = "deleted"                    # 渠道已删除
APP_OFF = "app_off"                    # 应用通知总开关关着
ALREADY = "already"                    # 本来就是目标状态，不打印
CONFIRMED_LATER = "confirmed_later"    # 第二遍重扫才确认其实已经改好
NOT_CONFIRMED = "not_confirmed"        # 页面没认出，或重取时页面已变化
MISMATCH = "mismatch"                  # 界面状态与渠道实际状态不一致
UNCHANGED = "unchanged"                # 点了三次，渠道状态仍未改变
ERROR = "error"                        # 意外异常，原文进 detail


@dataclass(frozen=True)
class Outcome:
    kind: str
    detail: str = ""


# 怎么记账由这一张表决定，不由返回值的形状暗示。键是结局，值是它对整批的四件事：
# fail_close / fail_open —— 关 / 开的方向上算不算失败（渠道已删除在还原时才算失败）；
# retry —— 页面慢可能造成的失败，一批跑完再试一次；
# toggled —— 算不算「实际拨动了」，用于「拨了 N 个」；
# exempt —— 收尾复查时豁免（系统锁定、应总开关关着，本来就不会变）。
# 渲染在 render()，是另一个问题：同一结局在不同方向下说法不同。
RULES = {
    DONE: dict(fail_close=False, fail_open=False, retry=False, toggled=True, exempt=False),
    GREYED: dict(fail_close=False, fail_open=False, retry=False, toggled=False, exempt=True),
    APP_DENIED: dict(fail_close=False, fail_open=False, retry=False, toggled=False, exempt=True),
    PROTECTED: dict(fail_close=False, fail_open=False, retry=False, toggled=False, exempt=False),
    NO_CHANNEL: dict(fail_close=True, fail_open=True, retry=False, toggled=False, exempt=False),
    DELETED: dict(fail_close=False, fail_open=True, retry=False, toggled=False, exempt=False),
    APP_OFF: dict(fail_close=False, fail_open=True, retry=False, toggled=False, exempt=False),
    ALREADY: dict(fail_close=False, fail_open=False, retry=False, toggled=False, exempt=False),
    CONFIRMED_LATER: dict(fail_close=False, fail_open=False, retry=False, toggled=True, exempt=False),
    NOT_CONFIRMED: dict(fail_close=True, fail_open=True, retry=True, toggled=False, exempt=False),
    MISMATCH: dict(fail_close=True, fail_open=True, retry=False, toggled=False, exempt=False),
    UNCHANGED: dict(fail_close=True, fail_open=True, retry=True, toggled=False, exempt=False),
    ERROR: dict(fail_close=True, fail_open=True, retry=False, toggled=False, exempt=False),
}
KINDS = tuple(RULES)


def failed(outcome, want_on=False):
    """这一项要不要算进退出码。"""
    return RULES[outcome.kind]["fail_open" if want_on else "fail_close"]


def retryable(outcome):
    return RULES[outcome.kind]["retry"]


def toggled(outcome):
    return RULES[outcome.kind]["toggled"]


def exempt_from_recheck(outcome):
    """收尾复查时不算「仍开着」：系统锁定的渠道点不动，应用通知整体关着的渠道不会弹。"""
    return RULES[outcome.kind]["exempt"]


def kind_of_state(st):
    """state() 的读数 → 结局：清单里的渠道不存在 / 已删除 / 应用通知总开关关着。"""
    return {"--": NO_CHANNEL, "del": DELETED, "app": APP_OFF}[st]


def render(outcome, label, want_on):
    """这一项的打印行；None 表示不提（已经是目标状态，或第二遍才确认改好、第一遍的 ✗ 已说过）。"""
    kind = outcome.kind
    if kind in (ALREADY, CONFIRMED_LATER):
        return None
    if kind == PROTECTED:
        return f"  · 受保护，未改动 {label}（找机位功能通知，{outcome.detail}）"
    if kind in (NO_CHANNEL, DELETED, APP_OFF):
        return f"  · 未操作 {label}（渠道不存在、已删除或应用通知已关闭）"
    if kind == GREYED:
        return f"  · 系统锁定（开关是灰的），不能关闭，不算失败  {label}"
    if kind == APP_DENIED:
        return f"  · 应用通知已整体关闭，渠道不会弹出，不算失败  {label}"
    if kind == DONE:
        return f"  {'开' if want_on else '关'}  {label}"
    return f"  ✗ {outcome.detail}  {label}"


def show(outcome, label, want_on):
    """打印这一项的结局；不打印的项静默通过。"""
    line = render(outcome, label, want_on)
    if line:
        print(line)


def truncated(cid):
    """三星等系统会把长渠道 ID 缩略成 'com.se...'（#95）：不能当真实 ID 深链或去重。"""
    return cid.endswith(("...", "…"))


def parse(p, locked=None):
    """只取机主空间（user 0）。双开、分身、隐私空间、安全文件夹的同名应用 UID 不同（#95），
    以前按包名混在一起：界面已关，回读却拿到另一空间的「开」。
    locked：传入集合时，收集系统不允许关闭的渠道（系统应用固定通知权限、渠道本身不可屏蔽，#134）。"""
    txt = p.d.shell("dumpsys notification --noredact", timeout=60).output
    # 安卓 8 / 9 的段名是「per-package config:」（RankingHelper），10 起是「PackagePreferences:」（#258 海信 Android 9）
    start = next((k for k in (txt.find("PackagePreferences:"), txt.find("per-package config:")) if k >= 0), -1)
    if start < 0:
        raise RuntimeError("读不到通知渠道状态，停止操作；请检查 USB 调试连接和系统权限")
    txt = txt[start:]
    cur, fixed, app_off, d = None, False, {}, {}
    for line in txt.splitlines():
        m = re.match(r"\s*AppSettings: (\S+)(?: \((\d+)\))?", line)
        if m:
            cur = m.group(1) if not m.group(2) or int(m.group(2)) < 100000 else None
            fixed = "fixedImportance=true" in line
            if cur:
                app_off[cur] = "importance=NONE" in line
            continue
        m = re.search(r"NotificationChannel\{mId='(.*?)', mName=(.*?), mDescription=.*?mImportance=(-?\d+).*?mDeleted=(\w+)", line)
        if m and cur:
            # 同一渠道可能带尾随空格回读两次（#194 纵横读屏）：键统一去掉空格，否则清单行
            # 查不到状态。两条读数矛盾时取「开着」的那条，宁可多关一次也不漏关；
            # 已删除的记录不覆盖有效记录。只有重要性 0 是已屏蔽，其余值都按开着算（同 state()）。
            key = (cur, m.group(1).strip())
            importance, deleted = int(m.group(3)), m.group(4) == "true"
            old = d.get(key)
            if (old is None or (old[2] and not deleted)
                    or (old[2] == deleted and old[1] == 0 and importance != 0)):
                d[key] = (m.group(2).strip(), importance, deleted)
            # 两条读数对「系统锁定」说法不一时按锁定处理：跳过比误关安全，且与回读顺序无关。
            # 已删除的记录不参与判断，它的锁定信息不可信。
            if locked is not None and fixed and not deleted and "mBlockableSystem=false" in line:
                locked.add(key)
    return d, app_off


def keep_awake(reader):
    """改开关期间插电常亮：营销通知一步可能跑好几分钟，以前只有机型脚本设了常亮（#71 中途锁屏）。"""
    old = reader.shell("settings get global stay_on_while_plugged_in").output.strip()
    try:
        reader.shell("settings put global stay_on_while_plugged_in 7")
        ok = reader.shell("settings get global stay_on_while_plugged_in").output.strip() == "7"
    except RuntimeError:
        ok = False
    if not ok:
        print("  ! 插电常亮没有设上，手机息屏会打断操作；请把自动锁屏时间调长后再跑。" + XIAOMI_INPUT, flush=True)
    return old if old.isdigit() else "0"


def load(path):
    rows = {}
    with open(path, encoding="utf-8-sig") as f:
        for lineno, line in enumerate(f, 1):
            line = line.rstrip("\r\n")
            if line.strip() and not line.lstrip().startswith("#"):
                # 第四列应用名只给人看：日志里不写应用名，上报的错误日志不含应用列表
                pk, cid, label = (x.strip() for x in (line.split("\t") + ["", ""])[:3])
                if not re.fullmatch(r"[\w.]+", pk) or not cid:
                    raise ValueError(f"清单第 {lineno} 行缺少有效包名或渠道 ID")
                # 同一渠道的重复行（含只差空格的写法，#194）合成一行：收尾按渠道计数，不能重复；
                # 哪一行带应用名就用哪一行的。
                rows[(pk, cid)] = label or rows.get((pk, cid), "")
    return [(pk, cid, label or cid) for (pk, cid), label in rows.items()]


def state(d, app_off, pk, cid):
    if (pk, cid) not in d:
        return "--"
    name, imp, deleted = d[(pk, cid)]
    if imp == 0: return "off"
    if deleted: return "del"
    if app_off.get(pk): return "app"
    return "ON"


ALLOW = {"允许通知", "显示通知", "Allow notifications", "Show notifications"}

# 通知页不在 com.android.settings 里的系统：只接受这些 Activity，页面内容仍由 channel_switch() 复核。
NOTIFY_HOSTS = {
    # ColorOS 14 一加 Ace 2 Pro 实测；ColorOS 17 Find X9 Ultra 社区实测（#165）
    "com.oplus.notificationmanager": re.compile(r"^com\.oplus\.notificationmanager\.(?:Channel|App)NotificationSettingsActivity$"),
    # 荣耀 MagicOS 10 PTP-AN00 社区实测（#86）。华为 EMUI / HarmonyOS 4 和旧版荣耀按同一结构识别，未经实测
    "com.hihonor.systemmanager": re.compile(r"^com\.hihonor\.notificationmanager\.ui\.\w*Notification\w*Activity$"),
    "com.huawei.systemmanager": re.compile(r"^com\.huawei\.notificationmanager\.ui\.\w*Notification\w*Activity$"),
}
HEADER_IDS = ("entity_header_title", "header_title")   # 三星 One UI 渠道名在页眉控件里，位置低于 0.22H（#95）


# vivo 通知设置页：OriginOS 4 起在 com.vivo.systemuiplugin；OriginOS Ocean（安卓 10）还在 com.android.systemui（错误日志 10-28）
VIVO_HOSTS = ("com.vivo.systemuiplugin", "com.android.systemui")
VIVO_ACTIVITY = ".notification.settings.channels.NotificationSettingsActivity"


def vivo_page(focus):
    return bool(focus) and focus.partition("/")[0] in VIVO_HOSTS and focus.endswith(VIVO_ACTIVITY)


def notification_focus(p):
    """vivo 的应用通知总页和单个渠道页是同一个 Activity（X300 Ultra / OriginOS 6 实测）：
    总页标题是 App 名，「允许通知」管整个 App；渠道页标题是渠道名，开关数随渠道开关状态变化。
    这里只认页面身份，区分交给 channel_switch()。"""
    focus = p.focus()
    package, _, activity = focus.partition("/")
    if activity.startswith("."):
        activity = package + activity
    p.sysui = False
    if package in NOTIFY_HOSTS:
        return focus if NOTIFY_HOSTS[package].match(activity) else ""
    if package in VIVO_HOSTS:
        if not activity.endswith(VIVO_ACTIVITY):
            return ""
        p.vivo_seen = True
        p.sysui = package == "com.android.systemui"   # texts() 默认不读 systemui 的文字（那是状态栏）
        return focus
    return focus if "settings" in package.lower() and ("notification" in activity.lower() or "SubSettings" in activity) else ""


def titled(p, root, name):
    """页面顶部的标题就是这个渠道名：还停在渠道页。"""
    return any(t == name and b[1] < p.H * 0.22 for t, b, _ in p.texts(root))


def top_title(p, root):
    """顶栏标题控件的文字（vivo：originui_vtoolbar_normal_title）。"""
    for t, b, n in p.texts(root):
        rid = (n.get("resource-id") or "").lower()
        if "toolbar" in rid and "title" in rid and b[1] < p.H * 0.22:
            return t
    return None


def allow_switches(p, root):
    """页面上的「允许通知」开关。标题可能来自所在行，也可能只在开关自己的 content-desc 上（三星）。"""
    found = [s for s in p.switches(root) if s[0] in ALLOW]
    for n in root.iter("node"):
        label = (n.get("text") or n.get("content-desc") or "").strip()
        if n.get("checkable") != "true" or label not in ALLOW or not p.on_screen(n) or "RadioButton" in n.get("class", ""):
            continue
        l, t, r, b = bounds(n)
        xy = ((l + r) // 2, (t + b) // 2)
        if not any(abs(s[2][1] - xy[1]) < 30 for s in found):
            found.append((label, n.get("checked") == "true", xy))
    return found


def channel_switch(p, name):
    """同时确认渠道标题、设置页身份和明确的通知开关；绝不取页面第一个开关。"""
    focus = notification_focus(p)
    if not focus or "AppNotification" in focus or not name:
        return None
    root = p.tree()
    if not any(t == name and (b[1] < p.H * 0.22 or (
            b[1] < p.H * 0.4 and (n.get("resource-id") or "").endswith(HEADER_IDS)))
            for t, b, n in p.texts(root)):
        return None
    if vivo_page(focus):
        # vivo 应用总页的「允许通知」会关掉整个 App，订单、聊天提醒也没了。只认从总页点进来的渠道页：
        # 顶栏是渠道名，且不同于刚才总页的 App 名；两者同名就无法区分，跳过。
        app = getattr(p, "vivo_app", None)
        if not app or top_title(p, root) != name or name == app:
            return None
    switches = allow_switches(p, root)
    return switches[0] if len(switches) == 1 else None


def chain(node, parents, depth=PATH_DEPTH):
    """从渠道名往上的控件链：类名、可点 c / 可滚动 s、子树里的开关数。不含页面文字，适配新系统靠它。"""
    return "结构 " + " < ".join(
        f"{(cls or 'node').rsplit('.', 1)[-1]}{':' + flags if flags else ''}#{count}"
        for cls, flags, count in path(node, parents, depth))


def inline_switch(p, name):
    """应用通知页里渠道行自带开关（荣耀 MagicOS 10 / Android 16，#99）。
    只认标题与渠道名完全相同、全页唯一合格的一行：行里恰有一个开关、行高合理、行内没有应用总开关。
    同名文字可能不止一处（华为 HarmonyOS 4 的应用通知页把分组名写在列表里，和渠道名相同，#287）：
    没有开关或开关对不上的那些行不算，只有剩下一行时才用。"""
    focus = notification_focus(p)
    if not name or name in ALLOW or not focus or vivo_page(focus):
        return None
    root = p.tree()
    parents = {c: n for n in root.iter() for c in n}
    # 开关自己的无障碍标签、整行的标签可能也是渠道名：开关本身不算，同一行只算一次
    rows, missing, reasons = set(), False, []
    good = []
    for t, b, n in p.texts(root):
        if t != name or b[1] < p.H * 0.22 or n.get("checkable") == "true":
            continue
        row, boxes = own(n, parents, p.on_screen)
        if row is None:
            missing = True
            reasons.append("没找到所在行；" + chain(n, parents))
            continue
        if id(row) in rows:
            continue
        rows.add(id(row))
        l, tp, r, btm = bounds(row)
        labels = {(x.get("text") or x.get("content-desc") or "").strip() for x in row.iter()}
        if len(boxes) == 1 and btm - tp <= p.H * 0.2 and not labels & ALLOW:
            good.append(boxes)
        else:
            reasons.append(f"行内开关 {len(boxes)} 个，行高 {round((btm - tp) * 100 / p.H)}%"
                           + ("，行内有应用总开关" if labels & ALLOW else "") + "；" + chain(n, parents))
    if len(good) != 1:
        count = len(rows) + (1 if missing else 0)
        p.why = (reasons[0] if count == 1 and reasons
                 else f"同名 {count} 行" + (f"：{reasons[0]}" if reasons else ""))
        return None
    boxes = good[0]
    bl, bt, br, bb = bounds(boxes[0])
    return name, boxes[0].get("checked") == "true", ((bl + br) // 2, (bt + bb) // 2)


def page_switch(p, name):
    return channel_switch(p, name) or inline_switch(p, name)


POLL = 0.2                                  # 认渠道页的采样间隔


def wait_page(p, name, rounds=12):
    def sample():
        sw = page_switch(p, name)
        # vivo 直达的渠道页按规则不直接用（见 channel_switch），不空等（错误日志 10-28：每个渠道 29 秒）
        if sw is None and getattr(p, "vivo_seen", False) is True and not getattr(p, "vivo_app", None):
            raise wait.GiveUp()
        return sw

    def locked():
        return ScreenLocked("手机锁屏了") if p.locked() else None

    # 预算按次数算：慢机型一轮读屏更久，但「最多试 rounds 次」就是要试满
    return wait.until(sample, tries=rounds, poll=POLL, same=3,
                      blocked=locked, now=time.monotonic, sleep=time.sleep)


def via_app_page(p, pk, name):
    """渠道深链被拦截时，从应用通知页进入：渠道行是导航行就点进去（HyperOS），自带开关就直接用这一行（内联布局）。"""
    p.why = ""
    p.d.shell("am start -f 0x10008000 -a android.settings.APP_NOTIFICATION_SETTINGS"
              f" --es android.provider.extra.APP_PACKAGE {shlex.quote(pk)}")
    root = None

    def app_page_shown():
        nonlocal root
        # 直达的渠道页可能还没换下去：vivo 两页是同一个 Activity，ColorOS 的渠道页也认得。
        # 以前读到旧页，点标题没反应，报「点这一行后页面没变」（错误日志 10-28）
        if not notification_focus(p):
            return None
        root = p.tree()
        return True if not titled(p, root, name) else None

    if not wait.until(app_page_shown, tries=15, poll=POLL,
                      now=time.monotonic, sleep=time.sleep):
        if not notification_focus(p):
            p.stage = "应用通知页没有打开"
            return None
    p.stage = "应用通知页里没找到这一行"
    for _ in range(9):
        if p.locked():
            raise ScreenLocked("手机锁屏了")
        if not notification_focus(p):
            p.stage = "应用通知页翻页时离开了"
            return None
        root = root if root is not None else p.tree()
        vivo = vivo_page(notification_focus(p))
        parents = {c: n for n in root.iter() for c in n}
        for text, b, n in p.texts(root):
            if text != name or b[1] < p.H * 0.22 or n.get("checkable") == "true":
                continue
            row, boxes = own(n, parents, p.on_screen)
            if row is None:
                continue
            if not vivo and boxes:
                p.stage = "应用通知页这一行的开关没认出"
                return wait_page(p, name)        # 内联开关：不当作导航行点；vivo 的渠道行也带 checked，要点进去
            if vivo:
                # 同一次读屏里列表有这一行渠道，说明是总页：这时的顶栏才是 App 名（直达页可能还没退掉）
                p.vivo_app = top_title(p, root)
            before = p.sig()
            l, t, r, btm = bounds(n)
            p.click((l + r) // 2, (t + btm) // 2)
            if not p.settle(before):
                p.stage = "点这一行后页面没变"
                # vivo 进渠道页的转场慢，settle 等不到变化不代表没进去：照常认页，认不出才算没变。
                # 错误日志 10-30：0.2.7 的 vivo 报告里 212 次「点这一行后页面没变；标题顶部」——跳过时渠道页已经打开。
                # 只放宽 vivo：它的认页要求顶栏是渠道名、且不同于刚记下的 App 名，不会把总页的「允许通知」当成渠道开关
                return wait_page(p, name) if vivo else None
            p.stage = "点进去后没认出渠道页"
            return wait_page(p, name)
        if not p.scroll_more():
            break
        root = None
    return None


class StopBatch(RuntimeError):
    """点错了开关：已尝试还原，整批停止。"""


def side_effects(before, apps_before, after, apps_after, pk, cid, allowed):
    """点击后除目标渠道外还有什么变了：应用总开关，或不在本批清单里的同应用渠道。"""
    out = []
    if apps_after.get(pk, False) != apps_before.get(pk, False):
        out.append("应用通知总开关")
    for key, (name, imp, _) in after.items():
        if key[0] != pk or key == (pk, cid) or key not in before:
            continue
        if (before[key][1] == 0) != (imp == 0) and key not in allowed:
            out.append(f"渠道「{name}」")
    return out


def page_hint(p, name):
    """跳过时附上页面结构（不含页面文字）：标题在不在、有几个开关。适配新系统靠它。"""
    try:
        root = p.tree()
        at = [b[1] < p.H * 0.22 for t, b, _ in p.texts(root) if t == name]
        title = "顶部" if any(at) else ("列表" if at else "无")
        return f"标题{title}，允许通知开关 {len(allow_switches(p, root))} 个，开关 {len(p.switches(root))} 个"
    except Exception:
        return ""


def notifications_denied(p, pk):
    """安卓 13 起应用通知总开关是 POST_NOTIFICATIONS 权限。有的系统 dumpsys notification 看不出来：
    渠道页的开关显示「关」，渠道记录仍是「开」（三星 9 个、vivo 2 个，错误日志 10-29；华为 #241 同样现象）。"""
    try:
        # 不加 grep -m：提前退出会让 dumpsys 收到 SIGPIPE，u2 判「shell output invalid」（#205）
        out = p.d.shell(f"dumpsys package {shlex.quote(pk)} | grep 'POST_NOTIFICATIONS: granted='"
                        " | sed -n '1,3p'").output
    except Exception:
        return False
    return isinstance(out, str) and "POST_NOTIFICATIONS: granted=false" in out and "POST_NOTIFICATIONS: granted=true" not in out


def disabled_at(p, xy):
    """开关是灰的（系统锁定的渠道）：点了也不会变，不再连点三次再报「状态未改变」。"""
    for n in p.tree().iter("node"):
        if n.get("checkable") == "true" and n.get("enabled") == "false":
            l, t, r, b = bounds(n)
            if l <= xy[0] <= r and t <= xy[1] <= b:
                return True
    return False


def undo(p, name, xy, want_on):
    """只在同一位置仍是刚拨过去的那个开关时再点一次，不沿用已消失的坐标。"""
    sw = wait_page(p, name, rounds=6)
    if sw and abs(sw[2][1] - xy[1]) < 30 and sw[1] == want_on:
        p.click(*sw[2]); time.sleep(0.4); p.confirm()
        return True
    return False


def toggle(p, pk, cid, want_on, name="", allowed=()):
    name = (name or "").strip()     # 渠道名可能带空格（一加 13「福利活动 」），页面文字是去掉空格的（错误日志 10-29）
    try:
        if p.locked():
            raise ScreenLocked("手机锁屏了")
        before, apps_before = parse(p)
        actual_name = before.get((pk, cid), ("", 0, False))[0]
        st = state(before, apps_before, pk, cid)
        if not want_on and protected_channel(actual_name, cid, name):
            return Outcome(PROTECTED, f"当前状态 {st}")
        if st in ("--", "del", "app"):
            return Outcome(kind_of_state(st))
        p.vivo_app, p.why = None, ""
        p.stage = "渠道深链没打开渠道页"
        sw = None
        if not truncated(cid) and getattr(p, "vivo_seen", False) is not True:   # vivo 只从应用通知页进渠道页
            # NEW_TASK|CLEAR_TASK 避免复用旧渠道；仍需核对真实页面。
            p.d.shell("am start -f 0x10008000 -a android.settings.CHANNEL_NOTIFICATION_SETTINGS"
                      f" --es android.provider.extra.APP_PACKAGE {shlex.quote(pk)}"
                      f" --es android.provider.extra.CHANNEL_ID {shlex.quote(cid)}")
            sw = wait_page(p, name)
        if not sw:
            sw = via_app_page(p, pk, name)
        if not sw:
            # 只记 Activity、卡在哪一环和开关数量，不记页面内容；适配新系统靠它。
            hint = "；".join(x for x in (getattr(p, "stage", ""), page_hint(p, name), getattr(p, "why", "")) if x)
            return Outcome(NOT_CONFIRMED,
                           f"未确认「{name}」渠道页及通知开关，跳过（停在 {p.focus() or '未知页面'}；{hint}）")
        if disabled_at(p, sw[2]):
            return Outcome(GREYED)
        desired = "ON" if want_on else "off"
        for attempt in range(3):
            # 每次重取页面，开关消失时不能复用旧坐标。
            if p.locked():
                raise ScreenLocked("手机锁屏了")
            sw = wait_page(p, name, rounds=6)
            if not sw:
                return Outcome(NOT_CONFIRMED, "渠道页或开关已变化，停止操作")
            clicked = sw[1] != want_on
            if clicked:
                p.click(*sw[2]); time.sleep(0.4); p.confirm()
            current, apps = parse(p)
            extra = side_effects(before, apps_before, current, apps, pk, cid, allowed)
            if extra:
                restored = clicked and undo(p, name, sw[2], want_on)
                raise StopBatch(f"点击后{'、'.join(extra)}发生变化，{'已点回原状态' if restored else '没能自动点回'}，"
                                "停止整批；请在手机上核对该 App 的通知设置")
            if state(current, apps, pk, cid) == desired:
                return Outcome(DONE)
            if sw[1] == want_on:
                if not want_on and notifications_denied(p, pk):
                    return Outcome(APP_DENIED)
                return Outcome(MISMATCH, "界面状态与渠道实际状态不一致，未继续点击")
            time.sleep(0.25 + 0.3 * attempt)
        return Outcome(UNCHANGED, "点击后渠道状态未改变")
    except (StopBatch, adb_link.DeviceLost, ScreenLocked):
        raise                                    # 点错开关、手机断开、锁屏：由整批处理
    except Exception as e:
        gone = adb_link.lost_from(e, getattr(p, "serial", None))   # 读屏库的断线异常不是 RuntimeError，以前带着堆栈退出（错误日志 10-28）
        if gone is not None:
            raise gone from e
        if isinstance(e, RuntimeError):
            return Outcome(ERROR, str(e))
        raise



def main():
    try:
        run(sys.argv[1:])
    except adb_link.DeviceLost as e:
        sys.exit(f"✗ {e}")
    except RuntimeError as e:
        # 读屏服务被占用、启动失败等：给出原因，不打印 Python 报错堆栈（错误日志 10-27）
        sys.exit(f"✗ {e}")
    except Exception as e:
        gone = adb_link.lost_from(e, sys.argv[2] if len(sys.argv) > 2 else None)
        if gone is None:
            raise
        sys.exit(f"✗ {gone}")


def run(a):
    if a in ([], ["--help"], ["-h"]):
        print(__doc__); return
    if len(a) < 3 or a[0] != "-s" or a[2] not in {"scan", "verify", "off", "on"}:
        sys.exit("用法：chan_fast.py -s <序列号> scan|verify|off|on [清单.tsv]")
    serial, cmd = a[1], a[2]
    if cmd != "scan" and len(a) < 4:
        sys.exit("请提供通知清单路径")
    # 先校验文件；错误清单不应启动手机读屏服务。
    items = load(a[3]) if cmd != "scan" else []
    reader = ShellPhone(serial)
    if cmd == "scan":
        locked = set()
        d, app_off = parse(reader, locked)
        short = fixed = 0
        rows = []
        for (pk, cid), (name, imp, deleted) in sorted(d.items()):
            if (imp != 0 and not deleted and not app_off.get(pk) and KW.search(name + " " + cid)
                    and not SKIP.search(name) and not protected_channel(name, cid)):
                if truncated(cid):
                    short += 1
                elif (pk, cid) in locked:
                    fixed += 1
                else:
                    rows.append((pk, cid, name))
        labels = app_labels(reader, [pk for pk, _, _ in rows])
        for pk, cid, name in rows:
            print("\t".join((pk, cid, name, labels[pk]) if pk in labels else (pk, cid, name)))
        if short:
            print(f"另有 {short} 个渠道的 ID 被系统缩略，无法可靠定位，未列入清单", file=sys.stderr)
        if fixed:
            print(f"另有 {fixed} 个渠道属于系统锁定、不允许关闭的系统应用，未列入清单", file=sys.stderr)
        return
    if cmd in ("off", "on"):
        want = cmd == "on"
        d, app_off = parse(reader)
        allowed = {(pk, cid) for pk, cid, _ in items}
        p = None
        t0 = time.time(); changed = 0; failures = 0
        stay_on, awake = None, False
        exemptions, gone, halted = set(), False, False
        todo = []
        for pk, cid, label in items:
            st = state(d, app_off, pk, cid)
            if not want and protected_channel(d.get((pk, cid), ("", 0, False))[0], cid, label):
                outcome = Outcome(PROTECTED, f"当前状态 {st}")
            elif st in ("--", "del", "app"):
                outcome = Outcome(kind_of_state(st))
            elif (st == "off") != (not want):
                todo.append((pk, cid, label))       # 要打开手机去拨
                continue
            else:
                outcome = Outcome(ALREADY)          # 已经是目标状态，不打印
            show(outcome, label, want)
            if failed(outcome, want):
                failures += 1
        retry, reached = [], 0
        try:
            for second in (False, True):
                queue = todo
                if second:
                    # 页面加载慢时一次没认出（错误日志 10-28：关了 93 个剩 1 个，整步算失败）。
                    # 这台已经关成功过才重试；华为那种一个都认不出的不重试，免得白等。
                    if halted or p is None or not retry or len(retry) > RETRY_MAX or not (reached or len(retry) <= 2):
                        break
                    d, app_off = parse(reader)
                    queue = []
                    for pk, cid, label in retry:
                        st = state(d, app_off, pk, cid)
                        if (st == "off") == (not want):
                            outcome = Outcome(CONFIRMED_LATER)
                            failures -= 1       # 其实已经改过来了
                            reached += 1
                            changed += toggled(outcome)
                            show(outcome, label, want)
                        else:
                            queue.append((pk, cid, label))
                    if not queue:
                        break
                    print(f"再试一次刚才没确认的 {len(queue)} 个渠道", flush=True)
                for index, (pk, cid, label) in enumerate(queue):
                    if not awake:
                        stay_on, awake = keep_awake(reader), True
                    if p is None:
                        print("正在连接手机读屏服务……", flush=True)
                        p = Phone(serial, log=False)
                        p.vivo_seen = False
                        p.pause_at_lock_check = False   # 渠道里面查锁屏的地方不是安全位置：只在两个渠道之间暂停
                        if not p.wait_unlocked():
                            failures += 1
                            print("  ✗ 手机一直锁屏，本步骤没有执行。请解锁手机、保持亮屏后重试")
                            halted = True
                            break
                        print(f"要处理 {len(todo)} 个渠道，每个几秒到半分钟，处理完一个显示一行", flush=True)
                    pause_point()
                    try:
                        try:
                            outcome = toggle(p, pk, cid, want, d[(pk, cid)][0], allowed)
                        except ScreenLocked:
                            if not p.wait_unlocked(60):
                                raise
                            outcome = toggle(p, pk, cid, want, d[(pk, cid)][0], allowed)
                    except ScreenLocked:
                        failures += 1
                        print(f"  ✗ 手机锁屏了，停在「{label}」，剩下 {len(queue) - index} 项没有处理。请解锁手机、保持亮屏后重试")
                        halted = True
                        break
                    except (StopBatch, adb_link.DeviceLost) as e:
                        failures += 1
                        gone, halted = isinstance(e, adb_link.DeviceLost), True
                        print(f"  ✗ {e}  {label}")
                        break
                    if failed(outcome, want):
                        if not second:
                            failures += 1
                        if not second and retryable(outcome):
                            retry.append((pk, cid, label))
                    else:
                        failures -= second      # 重试成功：第一遍记下的失败撤销
                        reached += 1
                        changed += toggled(outcome)
                    if exempt_from_recheck(outcome):
                        exemptions.add((pk, cid))
                    show(outcome, label, want)
                if halted:
                    break                       # 锁屏、点错开关、断开：整批停下，不再重试
            if p is not None and not gone:
                p.d.shell("input keyevent HOME")   # 只读 / 无需改动时不操作手机页面
        finally:
            if p is not None:
                p.close()
            if stay_on is not None:
                try:
                    reader.shell(f"settings put global stay_on_while_plugged_in {stay_on}")
                except RuntimeError:
                    pass                        # 手机已断开：收尾一步会再改回
        print(f"拨了 {changed} 个，{time.time()-t0:.0f} 秒")
        if gone:
            sys.exit(1)                 # 手机已断开：上面已说明原因，不再回读
    else:
        exemptions = set()
    d, app_off = parse(reader)
    bad = 0
    for pk, cid, label in items:
        st = state(d, app_off, pk, cid)
        protected = protected_channel(d.get((pk, cid), ("", 0, False))[0], cid, label)
        if st == "ON" and not protected and (pk, cid) not in exemptions:
            bad += 1
            if cmd == "off":
                print(f"  仍开着：{label}")       # 以前只给数量，看不出是哪一个（#115）
        if cmd == "verify":
            print(f"{st:4} {label}" + ("（受保护，不参与营销关闭）" if protected else ""))
    print(f"营销渠道仍开着: {bad} 个")
    if cmd == "on":
        pending = sum(state(d, app_off, pk, cid) != "ON" for pk, cid, _ in items)
        print(f"未恢复的渠道: {pending} 个")
        if pending or failures:
            sys.exit(1)
    if cmd == "off" and (bad or failures):
        sys.exit(1)                  # 让客户端把这一步标成失败（Issue #7：以前失败了也显示成功）


if __name__ == "__main__":
    main()
