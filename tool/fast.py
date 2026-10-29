#!/usr/bin/env python3
"""去广告快速引擎（uiautomator2，读屏 ~0.03 秒）。

命令行：
  fast.py -s SERIAL ls                 列当前屏：文字 + 开关状态
  fast.py -s SERIAL check              检查读屏服务，不点击、不输出页面内容
  fast.py -s SERIAL tap 文字 [文字…]    依次点（找不到会往下翻着找）
  fast.py -s SERIAL off [保留词,…]      当前列表里开着的开关全关（保留词命中的不动），一路翻到底
  fast.py -s SERIAL scan                 只读：翻到底列出所有开关
  fast.py -s SERIAL only 词,词…         只关标题含这些词的开关
  fast.py -s SERIAL run 机型脚本.py         跑一个品牌机型脚本
在脚本里：from fast import Phone
"""
import os, re, sys, time, xml.etree.ElementTree as ET
for _st in (sys.stdout, sys.stderr):
    try:
        _st.reconfigure(encoding="utf-8", errors="replace")   # Windows 控制台默认不是 UTF-8
    except Exception:
        pass
import adbutils
import uiautomator2 as u2
from ui_session import connect
from troubleshooting import UI_RECOVERY, XIAOMI_INPUT, accessibility_summary, input_blocked
import adb_link

BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
DISMISS = ("以后再说", "暂不更新", "暂不", "取消", "我知道了", "跳过", "禁止", "不再提示", "不同意")
CONFIRM = ("确定", "关闭", "仍要关闭", "确认关闭", "确认", "继续关闭", "关闭推荐", "仍然关闭")
PERMISSION_CONTROLLERS = {"com.android.permissioncontroller", "com.google.android.permissioncontroller"}
# 输入框：荣耀 MagicOS 10（PNM-AN10 10.0.0.102）设置搜索框是 AutoCompleteTextView，类名里没有 EditText
EDIT = re.compile(r"EditText|AutoCompleteTextView")


class ScreenLocked(RuntimeError):
    """手机锁屏了：调用方等机主解锁，或停下整批，不逐项报同一个原因。"""


def pause_point():
    """客户端点了「暂停」（创建 AAC_PAUSE_FILE）就在这里等，点「继续」（删掉文件）再往下走；暂停过返回 True。
    只放在安全的位置：机型脚本每段开始前（段首的锁屏检查）、营销通知每个渠道开始前。
    暂停期间不读屏、不点击；继续后重新读页面，不用暂停前的坐标。"""
    path = os.environ.get("AAC_PAUSE_FILE")
    if not path or not os.path.exists(path):
        return False
    print("⏸ 已暂停：现在可以操作手机。操作完回到桌面、保持解锁，再点「继续」", flush=True)
    while os.path.exists(path):
        time.sleep(0.5)
    print("▶ 继续执行", flush=True)
    return True


def bounds(n):
    m = BOUNDS.match(n.get("bounds", ""))
    return tuple(map(int, m.groups())) if m else (0, 0, 0, 0)


def switch_row(node, parents, depth=6):
    """文字所在的那一行（往上第一个可点 / 可勾选的控件）里有开关：这一行是开关，不是导航入口。"""
    row = node
    for _ in range(depth):
        if row is None:
            return False
        if row.get("clickable") == "true" or row.get("checkable") == "true":
            return any(x.get("checkable") == "true" and "RadioButton" not in (x.get("class") or "") for x in row.iter())
        row = parents.get(row)
    return False


# 「防止/限制/阻止广告跟踪」「关闭个性化推荐」这类开关是反着的：打开才是保护。不能当广告开关关掉。
NEG_PREFIX = re.compile(r"^(防止|限制|阻止|禁止|拒绝|不允许|屏蔽|关闭|停用|不接收|不显示|不推送|停止)")
AD_WORDS = re.compile(r"广告|跟踪|追踪|推荐|个性化|营销|资讯|热搜|热点|定向|画像")   # 不含「推送」：「关闭推送」会连订单通知一起关
TRACK_WORDS = re.compile(r"广告|跟踪|追踪")


def want_state(title):
    """这个开关该处在什么状态：False=关（普通广告开关）；True=开（保护类开关）；None=不碰。"""
    if NEG_PREFIX.search(title or ""):
        return True if AD_WORDS.search(title) else None
    return False


class Phone:
    def __init__(self, serial, log=True):
        if log:
            print("正在连接手机读屏服务……", flush=True)
        try:
            self.d = connect(serial)
        except u2.exceptions.AccessibilityServiceAlreadyRegisteredError as e:
            raise RuntimeError("UIAUTOMATION_BUSY：手机读屏服务已被占用，本次未点击开关。"
                               "已清理本次失败的启动并重试一次，仍无法连接。"
                               "请退出旧版客户端，只保留一个客户端。\n"
                               f"{accessibility_summary(serial)}\n{UI_RECOVERY}\n"
                               f"原始异常：{type(e).__name__}: {e}") from e
        except u2.exceptions.UiAutomationError as e:
            raise RuntimeError("手机读屏服务（UiAutomation）启动失败，本次未点击开关。"
                               f"\n{accessibility_summary(serial)}\n{UI_RECOVERY}\n"
                               f"原始异常：{type(e).__name__}: {e}") from e
        except (u2.exceptions.AdbShellError, adbutils.AdbError) as e:
            # 读屏服务文件传不进手机（adb push 返回 FAIL）或命令无回应：多半是连接中途断了（错误日志 10-27）。
            if not adb_link.present(serial):
                raise adb_link.lost(f"{type(e).__name__}: {e}") from e
            raise RuntimeError("读屏服务没能装到手机上（adb 传文件失败），本次未点击开关。请拔插数据线、"
                               "退出电脑上的手机助手类软件后重试；仍失败请重启手机。"
                               f"\n原始异常：{type(e).__name__}: {str(e)[:200]}") from e
        self.serial, self.lost = serial, False
        self._shell, self.d.shell = self.d.shell, self._resilient_shell
        try:
            self.d.settings["operation_delay"] = (0, 0)
            self.W, self.H = self.d.window_size()
            # 小米没开「USB 调试（安全设置）」时能读不能点：先探一下，别跑几分钟全是「没找到」。
            if input_blocked(self.d.shell("input keyevent 0").output):
                raise RuntimeError("INPUT_BLOCKED：系统拒绝了电脑发出的点击，本次未点击开关。\n" + XIAOMI_INPUT)
        except BaseException:
            self.d.close()
            raise
        self.log = log
        self.pause_at_lock_check = True     # 机型脚本每段开头都查锁屏：这里就是段与段之间，可以暂停
        self.changed = []          # (页面, 标题) 记录本次关掉的
        self.miss = 0              # 本段已经没找到几次；>0 说明路径对不上，后面只看当前屏、不再翻页找

    def _resilient_shell(self, *args, **kwargs):
        """手机短暂掉线（另一个 adb 服务重启、接口抖动）等它回来重试一次；仍不在就整段停下。"""
        if self.lost:
            raise adb_link.lost()
        try:
            return self._shell(*args, **kwargs)
        except Exception as e:
            # 「shell output invalid … b''」：命令没有任何回应，连接正在断开（错误日志 10-27）。
            if not (adb_link.lib_gone(str(e)) or (isinstance(e, u2.exceptions.AdbShellError) and "output invalid" in str(e))):
                raise
            if not adb_link.wait_for(self.serial):
                self.lost = True
                raise adb_link.lost(str(e)) from e
            return self._shell(*args, **kwargs)

    def close(self):
        self.d.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def say(self, *a):
        if self.log:
            print(*a, flush=True)

    # ---------- 读屏 ----------
    def tree(self):
        root = ET.fromstring(self.d.dump_hierarchy())
        # Mi 10 的热榜子页会横屏；不能一直用连接时的竖屏尺寸过滤节点。
        self.W, self.H = self.d.window_size()
        return root

    def focus(self):
        """当前焦点窗口（~0.1 秒；u2 的 app_current 在浮窗上会卡 10 秒）。"""
        # 不能加 grep -m / head：提前退出会让 dumpsys 收到 SIGPIPE，u2 判「shell output invalid」（#205）。
        # sed 读完整个流再截断，行数与原来一致。
        out = self.d.shell("dumpsys window | grep -E 'mCurrentFocus|mFocusedApp' | sed -n '1,4p'").output
        # vivo OriginOS 3 / Android 13 行尾是「Activity}}」（错误日志 10-27）。
        # 焦点窗口为 null 时看 mFocusedApp：华为 HarmonyOS 4.2、vivo OriginOS Ocean 页面明明在，以前报「停在 未知页面」（错误日志 10-29）
        for field in ("mCurrentFocus", "mFocusedApp"):
            m = re.search(field + r"=.*? u0 ([^\s}]+)", out)
            if m:
                return m.group(1)
        out = self.d.shell("dumpsys activity activities | grep -E 'topResumedActivity|mResumedActivity|ResumedActivity:'"
                           " | sed -n '1p'").output
        m = re.search(r"u0 (\S+/[^\s}]+)", out) or re.search(r" (\S+/[^\s}]+)", out)
        return m.group(1) if m else ""

    def texts(self, root=None):
        root = root if root is not None else self.tree()
        out = []
        for n in root.iter("node"):
            if n.get("package") == "com.android.systemui" and not getattr(self, "sysui", False):
                continue                      # 状态栏/通知栏文字不算
            t = (n.get("text") or n.get("content-desc") or "").strip()
            if t and self.on_screen(n):
                out.append((t, bounds(n), n))
        return out

    def on_screen(self, n):
        """折叠屏合上时，dump 里还留着内屏那份节点，坐标在外屏之外（Issue #2）；点上去没反应。"""
        if n.get("visible-to-user") == "false":
            return False
        l, t, r, b = bounds(n)
        cx, cy = (l + r) // 2, (t + b) // 2
        return r > l and b > t and 0 <= cx < self.W and 0 <= cy < self.H

    def switches(self, root=None):
        """[(标题, checked, (cx,cy))]，标题取开关所在行的第一段文字。"""
        root = root if root is not None else self.tree()
        parent = {c: p for p in root.iter() for c in p}
        out = []
        shot = None
        for n in root.iter("node"):
            if not self.on_screen(n) or "RadioButton" in n.get("class", ""):
                continue
            if n.get("checkable") != "true":
                rid = (n.get("resource-id") or "").lower()
                if "switch" in rid and "switcher" not in rid and n.get("clickable") == "true":      # 自绘开关：看颜色；TextSwitcher 是文字轮播
                    l, t, r, b = bounds(n)
                    if r - l > 0 and b - t > 0:
                        if shot is None:
                            shot = self.d.screenshot()
                        # UI 坐标与截图可能来自不同分辨率/旋转状态。不能越界取样，也不能把未知状态当关。
                        if shot.size != (self.W, self.H):
                            continue
                        on = self._pixel_on(shot, l, t, r, b)
                        if on is None:
                            continue
                        n.set("checked", "true" if on else "false")
                        n.set("checkable", "true")
                        n.set("class", "SelfDrawnSwitch")
                if n.get("checkable") != "true":
                    continue
            cls = n.get("class", "")
            if not any(k in cls for k in ("Switch", "CheckBox", "ToggleButton", "Compound")) and n.get("clickable") != "true":
                continue
            l, t, r, b = bounds(n)
            if r - l <= 0 or b - t <= 0 or not self.on_screen(n):
                continue
            cy = (t + b) // 2
            states = ("开", "关", "已开启", "已关闭", "开启", "关闭", "ON", "OFF",
                      "开启，开关", "关闭，开关", "已开启，开关", "已关闭，开关", "开启，按钮", "关闭，按钮")
            label = (n.get("text") or n.get("content-desc") or "").strip().split("\n", 1)[0]
            label = label if label not in states else ""
            title, p = "", n
            for _ in range(6):
                # 有自己的可访问标签时，不从包含多个开关的公共列表借用相邻行标题。
                # 单行容器仍优先取子标题，避免把「标题 + 长说明」整段当标题。
                if label and p is not n and sum(
                    1 for x in p.iter("node") if "Switch" in x.get("class", "")
                    and "Switcher" not in x.get("class", "") and self.on_screen(x)
                ) > 1:
                    title = label
                    break
                cand = []
                for x in p.iter("node"):
                    tx = (x.get("text") or x.get("content-desc") or "").strip().split("\n", 1)[0]
                    if x is n or not tx or tx in states:
                        continue
                    xl, xt, xr, xb = bounds(x)
                    if xb <= xt or not self.on_screen(x):
                        continue
                    cand.append((xt, xl, xb, tx))
                if cand:
                    pl, pt, pr, pb = bounds(p)
                    if pb - pt <= max(self.H * 0.18, (b - t) * 3):
                        title = min(cand)[3]          # 开关所在的这一行：最上面那段是标题，下面是说明
                    else:
                        # 往上找到的是整个列表：取竖直方向离开关最近的文字（Issue #2：不然会把
                        # 「自动更新」那行认成上一行的「每次联网时通知」）
                        near = sorted((0 if xt <= cy <= xb else min(abs(xt - cy), abs(xb - cy)), xt, tx)
                                      for xt, xl, xb, tx in cand)
                        if near[0][0] <= max(60, b - t):
                            title = near[0][2]
                    break
                p = parent.get(p)
                if p is None:
                    break
            out.append((title or label, n.get("checked") == "true", ((l + r) // 2, cy)))
        # 同一行有「整行」和「开关」两个 checkable 时，留最靠右的那个
        rows = []
        for sw in sorted(out, key=lambda s: s[2][1]):
            if rows and abs(rows[-1][2][1] - sw[2][1]) < 30:
                if sw[2][0] > rows[-1][2][0]:
                    rows[-1] = sw if sw[0] else (rows[-1][0], sw[1], sw[2])
            else:
                rows.append(sw)
        return rows

    def locked(self):
        if getattr(self, "pause_at_lock_check", False) and pause_point():
            return not self.wait_unlocked()      # 暂停时机主可能锁了屏：亮屏等他解锁
        out = self.d.shell(adb_link.KEYGUARD_CMD).output
        if adb_link.focus_window(out) == "NotificationShade" and not adb_link.LOCK_FIELD.search(out):
            # 可能只是通知栏被拉下来了：收起后再看；锁屏界面收不起来，焦点仍是 NotificationShade
            self.d.shell("cmd statusbar collapse")
            time.sleep(0.4)
            out = self.d.shell(adb_link.KEYGUARD_CMD).output
        return adb_link.keyguard_showing(out)

    def wait_unlocked(self, timeout=90):
        """锁屏时点亮屏幕，等机主解锁（不代替解锁）。等到了返回 True。
        错误日志 10-27：约 15 份报告在开始执行时手机已锁屏，以前直接报失败，后面每一项都重复「锁屏了」。"""
        self.d.shell("input keyevent KEYCODE_WAKEUP")
        if not self.locked():
            return True
        print(f"  ! 手机锁屏了：请解锁手机并保持亮屏，解锁后自动继续（最多等 {timeout} 秒）", flush=True)
        t = time.time()
        while time.time() - t < timeout:
            time.sleep(1)
            if not self.locked():
                time.sleep(0.8)
                return True
        return False

    def sig(self):
        return "|".join(t for t, _, _ in self.texts())

    def scroll_more(self):
        """翻一页；翻完没出现新文字（到底、回弹）返回 False。"""
        if not any(n.get("scrollable") == "true" and self.on_screen(n) for n in self.tree().iter("node")):
            return False                       # 单屏面板上滑动可能直接关掉页面
        focus = self.focus()
        before = {t for t, _, _ in self.texts()}
        self.scroll()
        if self.focus() != focus:
            raise RuntimeError("翻页离开了当前设置页，停止本段以免操作其他 App")
        after = {t for t, _, _ in self.texts()}
        return not after <= before

    @staticmethod
    def _pixel_on(img, l, t, r, b):
        """开关轨道取几个点：彩色（蓝/绿/橙，饱和度高）=开，灰白=关。"""
        w, h = img.size
        if not (0 <= l < r <= w and 0 <= t < b <= h):
            return None
        img = img.convert("RGB")
        sat = 0
        for fx in (0.25, 0.5, 0.75):
            R, G, B = img.getpixel((int(l + (r - l) * fx), (t + b) // 2))
            sat = max(sat, max(R, G, B) - min(R, G, B))
        return sat > 60

    def ls(self):
        root = self.tree()
        print("·", self.focus())
        print(" / ".join(t for t, _, _ in self.texts(root)))
        for t, c, xy in self.switches(root):
            print(f"  [{'开' if c else '关'}] {t}  @{xy}")

    # ---------- 动作 ----------
    def click(self, x, y):
        size = self.d.window_size()
        if tuple(size) != (self.W, self.H):
            self.W, self.H = size
            raise RuntimeError("屏幕方向或尺寸已变化，停止使用旧坐标；请重新读取页面")
        if not (0 <= x < self.W and 0 <= y < self.H):
            raise RuntimeError("点击坐标在屏幕外，未操作")
        out = self.d.shell(f"input swipe {x} {y} {x} {y} 80").output   # 有的 App 吞 input tap
        if input_blocked(out):
            raise RuntimeError("系统拒绝了电脑发出的点击。" + XIAOMI_INPUT)

    def scroll(self, frac=0.45, up=False):
        """按下-移动-停 0.12 秒-松开：没有惯性，翻多少是多少，约 0.45 秒。"""
        x = self.W * 7 // 10 if self.W > 2000 else self.W // 2
        frac = min(frac, 0.58)                   # 留在 0.22H~0.80H 之间拖，避开标题栏和底栏
        y1, y2 = int(self.H * 0.80), int(self.H * (0.80 - frac))
        if up:
            y1, y2 = y2, y1
        c = [f"input motionevent DOWN {x} {y1}"]
        c += [f"input motionevent MOVE {x} {int(y1 + (y2 - y1) * i / 6)}" for i in range(1, 7)]
        c += ["sleep 0.12", f"input motionevent UP {x} {y2}"]
        self.d.shell(";".join(c))
        time.sleep(0.15)

    def top(self, n=4):
        for _ in range(n):
            if not any(x.get("scrollable") == "true" and self.on_screen(x) for x in self.tree().iter("node")):
                break
            focus = self.focus()
            before = {t for t, _, _ in self.texts()}
            self.scroll(0.58, up=True)
            if self.focus() != focus:
                raise RuntimeError("回到页顶时离开了当前设置页，停止本段")
            if {t for t, _, _ in self.texts()} <= before:
                break

    def find(self, text, exact=False, root=None, edge_ok=False, nav=False):
        """先找文字完全相同的，再找包含的。nav=True（tap 导航用）：包含匹配不点开关所在行里的文字——
        那是开关的说明，点了等于拨开关（#247：「隐私」命中「边下边玩」的说明「不涉及隐私数据」，把功能关了）。"""
        root = root if root is not None else self.tree()
        items, parents = self.texts(root), None
        for whole in ((True,) if exact else (True, False)):
            for t, (l, tp, r, b), n in items:
                if not ((t == text) if whole else (text in t and t != text)):
                    continue
                if b <= tp or r <= l:
                    continue
                if nav and not whole:
                    parents = parents or {c: q for q in root.iter() for c in q}
                    if switch_row(n, parents):
                        continue
                cy = (tp + b) // 2
                if cy < self.H * 0.92:
                    return ((l + r) // 2, cy)
                if edge_ok == "tab":                     # 底部标签栏：直接点中心
                    return ((l + r) // 2, cy)
                if edge_ok and tp < self.H * 0.975:      # 已到页底翻不上来：点这一行的上沿
                    return ((l + r) // 2, tp + 15)
        return None

    CLOSE = re.compile(r"close|关闭|跳过|skip|cancel|dismiss|iv_x\b|btn_x\b", re.I)

    def dismiss(self):
        """挡路的更新/推荐/权限弹窗：点拒绝类按钮（不替用户同意任何东西）。
        纯图片的广告弹窗没有文字，只有一个 ✕ 图标：找 desc/id 里带 close 的可点元素。"""
        root = self.tree()
        # Android 运行时权限页只点明确的拒绝按钮，不替用户授予权限或修改“不再询问”。
        if (any(n.get("package") in PERMISSION_CONTROLLERS for n in root.iter("node"))
                and self.focus().split("/", 1)[0] in PERMISSION_CONTROLLERS):
            for n in root.iter("node"):
                if (n.get("package") in PERMISSION_CONTROLLERS and "Button" in n.get("class", "")
                        and n.get("text") in ("拒绝", "不允许", "Deny", "Don't allow") and self.on_screen(n)):
                    l, t, r, b = bounds(n)
                    self.click((l+r)//2, (t+b)//2); time.sleep(.4)
                    self.say("  · 已拒绝运行时权限申请，未授予权限")
                    return "拒绝权限"
            return None
        parent = {c: p for p in root.iter() for c in p}

        def in_list(n):
            # 列表里卡片的 ✕（ColorOS 17 隐私页「关闭提示」）点了会打开别的页面；广告弹窗的 ✕ 在列表外的浮层里。
            n = parent.get(n)
            while n is not None:
                if n.get("scrollable") == "true":
                    return True
                n = parent.get(n)
            return False

        for n in root.iter("node"):
            if n.get("clickable") != "true" or n.get("package") == "com.android.systemui":
                continue
            key = (n.get("content-desc") or "") + " " + (n.get("resource-id") or "")
            if self.CLOSE.search(key) and not (n.get("text") or "").strip() and not in_list(n):
                l, t, r, b = bounds(n)
                # 只点屏幕内的图标：屏幕外还留着上一层的节点，点它会抛「点击坐标在屏幕外」把整段打断
                if 0 < r - l < self.W * 0.3 and 0 < b - t < self.H * 0.12 and self.on_screen(n):
                    self.click((l + r) // 2, (t + b) // 2); time.sleep(0.6)
                    self.say(f"  · 弹窗点了 ✕（{key.strip()[:40]}）")
                    return "✕"
        tx = self.texts(root)
        if len(tx) > 16:
            return None
        # 天气等 App 的正常设置面板也有「取消」。带开关/滚动列表的页面不能仅凭文字当弹窗关掉。
        if any(n.get("checkable") == "true" or n.get("scrollable") == "true" for n in root.iter("node")):
            return None
        for w in DISMISS:
            for t, (l, tp, r, b), _ in tx:
                if t == w:
                    self.click((l + r) // 2, (tp + b) // 2); time.sleep(0.6)
                    self.say(f"  · 弹窗点了「{w}」")
                    return w
        return None

    def tap(self, text, exact=False, scrolls=6, wait=0.6):
        """找到就点。往下翻着找；翻到底没有，就回顶部再找一遍。
        scrolls=0（点底栏/按钮）：不翻页，但 3 秒内边等边关弹窗。"""
        if scrolls == 0:
            t0 = time.time()
            while time.time() - t0 < 3.0:
                xy = self.find(text, exact, edge_ok="tab", nav=True)
                if xy:
                    b = self.sig(); self.click(*xy); self.settle(b, wait + 0.4)
                    return True
                self.dismiss() or time.sleep(0.2)
            self.say(f"  ✗ 没找到「{text}」")
            return False
        if self.miss:                                   # 本段已经走丢：只看当前这一屏
            xy = self.find(text, exact, nav=True)
            if xy:
                b = self.sig(); self.click(*xy); self.settle(b, wait + 0.4)
                self.miss = 0
                return True
            self.miss += 1
            self.say(f"  ✗ 没找到「{text}」（快速放弃）")
            return False
        for rnd in range(2 if scrolls else 1):
            for i in range(scrolls + 1):
                edge = "tab" if scrolls == 0 else False
                xy = self.find(text, exact, edge_ok=edge, nav=True)
                if not xy and self.dismiss():
                    xy = self.find(text, exact, edge_ok=edge, nav=True)
                if xy:
                    b = self.sig(); self.click(*xy); self.settle(b, wait + 0.4)
                    return True
                if i < scrolls and not self.scroll_more():
                    xy = self.find(text, exact, edge_ok=True, nav=True)
                    if xy:
                        self.click(*xy); time.sleep(wait)
                        return True
                    break
            if rnd == 0 and scrolls:
                self.top(scrolls + 2)
        self.miss += 1
        self.say(f"  ✗ 没找到「{text}」")
        return False

    def go(self, text, expect, tries=3, exact=True):
        """点 text，直到 expect 出现在屏幕上（被弹窗吞掉就再点）。"""
        for _ in range(tries):
            self.tap(text, exact=exact, scrolls=0)
            for _ in range(5):
                if self.find(expect) or self.find(expect, edge_ok="tab"):
                    return True
                self.dismiss() or time.sleep(0.3)
        self.say(f"  ✗ 点「{text}」后没出现「{expect}」")
        return False

    def settle(self, before, maxwait=0.8):
        """等新的非空页面稳定；跳页动画中的空树不算已经加载好。"""
        t0, previous, stable_since = time.time(), None, None
        while time.time() - t0 < maxwait:
            time.sleep(0.1)
            cur = self.sig()
            if cur and cur != before:
                if cur != previous:
                    stable_since = time.time()
                elif stable_since is not None and time.time() - stable_since >= 0.2:
                    return True
            else:
                stable_since = None
            previous = cur
        return False

    def back(self, n=1):
        for _ in range(n):
            b = self.sig()
            self.d.shell("input keyevent BACK")
            self.settle(b, 0.6)

    def confirm(self):
        """开关后弹确认框就点确认类按钮。只认真按钮（Button 类），
        ColorOS 开关旁边的「开启/关闭」状态文字不算——点了会把开关又拨回去。
        按钮文字不一定在 text 上：vivo 阅图锁屏的 Button text 为空、文字在 content-desc（#246 / PR #249）；
        vivo / iQOO 另一种弹窗把文字放在 Button 下级的 TextView（vbutton_title，PR #239）。
        都要整段等于确认词，避免点到说明文字。
        屏幕外的节点跳过：页面里常留着上一层对话框的按钮，点它会抛「点击坐标在屏幕外」把整段打断（PR #248）。"""
        time.sleep(0.2)
        root = self.tree()
        for c in CONFIRM:
            for n in root.iter("node"):
                if "Button" not in (n.get("class") or ""):
                    continue
                label = (n.get("text") or "").strip() or (n.get("content-desc") or "").strip()
                inner = {(x.get("text") or "").strip() for x in n.iter("node") if x is not n}
                if label != c and not (not label and c in inner):
                    continue
                l, t, r, b = bounds(n)
                if r > l and b > t and self.on_screen(n):
                    self.click((l + r) // 2, (t + b) // 2)
                    time.sleep(0.3)
                    return c
        return None

    def off(self, keep=(), only=None, page="", max_screens=40):
        """当前列表：关掉开着的开关。keep=标题含这些词的不动；only=只关含这些词的。
        每屏第一下单独点、看有没有弹窗/跳页；没有就把这一屏剩下的连着点完，最后统一核对。"""
        for _ in range(2 if self.miss else 10):  # 页面刚打开还没画完：等开关出现，最多 2 秒（本段已走丢就不等）
            if self.switches():
                break
            time.sleep(0.2)
        start = self.focus()
        done, slow, checked, kept = 0, False, set(), set()
        for _ in range(max_screens):
            root = self.tree()
            targets = []
            for t, c, xy in self.switches(root):
                if not t:
                    continue
                want = want_state(t)
                if want is None:
                    continue
                if any(k in t for k in keep):
                    continue
                if only is not None and not any(k in t for k in only) and not (want and TRACK_WORDS.search(t)):
                    continue                              # 「限制广告跟踪」这类保护开关：不在名单里也要打开
                if os.environ.get("AAC_REF") and only is None and not want:
                    kept.add(t)
                    continue                              # 参考脚本（同品牌别的机型录的）：不做整页全关
                checked.add(t)
                if c == want:
                    continue
                if xy[1] < self.H * 0.08 or xy[1] > self.H * 0.985:
                    continue
                targets.append((t, xy, want))
            for i, (t, xy, _) in enumerate(targets):
                self.click(*xy)
                if i == 0 or slow:
                    if self.confirm():
                        slow = True                     # 这页会弹确认框，逐个点
                    elif self.focus() != start:
                        self.say(f"  ! 页面变了（{self.focus()}），停")
                        self.back()
                        return done
                else:
                    time.sleep(0.06)
            if targets:
                time.sleep(0.25)
                self.confirm()

                def wrong():                            # 还没到目标状态的标题
                    now = {t: c for t, c, _ in self.switches()}
                    return {t for t, _, w in targets if now.get(t) != w}

                def retry(still):
                    # 只重试当前仍能识别的开关，不能在节点消失后沿用旧坐标。
                    now = {t: (c, xy) for t, c, xy in self.switches()}
                    for t, _, w in targets:
                        if t in still and t in now and now[t][0] != w:
                            self.click(*now[t][1]); self.confirm()
                still = wrong()
                retry(still)
                still = wrong()
                if still:                               # 还有没拨过去的：等动画结束再点一次
                    time.sleep(0.8)
                    retry(still)
                    time.sleep(0.4)
                    still = wrong()
                for t, _, w in targets:
                    if t in still:
                        self.say(f"  ✗ {'打不开' if w else '关不掉'} {t}")
                    else:
                        self.say(f"  {'开（保护类开关）' if w else '关'} {t}")
                        self.changed.append((page, t))
                        done += 1
            if not self.scroll_more():
                break
        if page:
            if kept and not checked:
                # 页面找到了，只是安全模式不整页全关；不能写成「未找到」
                self.say(f"  · {page}：安全模式不做整页全关，本页 {len(kept)} 个开关未改动，需要时请按清单手动关")
            else:
                self.say(f"  · {page}：核对 {len(checked)} 项，调整 {done} 项" + ("（本页未找到目标开关）" if not checked else ""))
        return done

    def focused_text(self):
        for n in self.tree().iter("node"):
            if n.get("focused") == "true" and EDIT.search(n.get("class") or "") and self.on_screen(n):
                return n.get("text") or ""
        return None

    def type_text(self, kw, timeout=4.0):
        """往当前输入框打字。部分机型（小米 HyperOS 设置搜索）用 setText 会卡住、一直打「%」：
        加超时，打完核对；不对就清掉、改用剪贴板粘贴；还不对就关掉键盘返回 False，不卡住。"""
        if not self.edit_ready():
            return False

        def attempt(fn):
            try:
                fn()
            except Exception:
                return False
            time.sleep(0.4)
            return (self.focused_text() or "").strip() == kw

        def clear():
            if not self.edit_ready():
                return
            try:
                self.d.jsonrpc.clearTextField(selector, http_timeout=timeout)
            except Exception:
                pass

        # 直接对已确认的输入框发有超时的 RPC，不启动无法取消的后台线程。
        # 旧线程超时后仍会等控件出现，可能在下一页补打文字；也不能退回任意 focused 节点（键盘也有）。
        selector = self.d(classNameMatches=r".*(EditText|AutoCompleteTextView)$", focused=True).selector
        def set_text():
            self.d.jsonrpc.setText(selector, kw, http_timeout=timeout)
        if attempt(set_text):
            return True
        if not self.edit_ready():
            return False
        clear()
        def paste():
            self.d.jsonrpc.setClipboard(None, kw, http_timeout=timeout)
            self.d.shell("input keyevent KEYCODE_PASTE", timeout=timeout)
        if attempt(paste):
            return True
        clear()
        self.d.shell("input keyevent BACK")
        return False

    BOX = re.compile(r"^搜索.{0,6}设置|^Search settings", re.I)

    def edit_ready(self):
        """搜索页打开了：屏幕上有获得焦点的输入框。"""
        for n in self.tree().iter("node"):
            if EDIT.search(n.get("class") or "") and n.get("focused") == "true" and self.on_screen(n):
                return True
        return False

    def setting(self, kw, entry=None, box=None):
        """系统设置里搜 kw，点结果 entry（默认就是 kw）。
        box：搜索框文字，不给就自动认（小米「搜索系统设置项」、OPPO「搜索设置项」等）。
        设置首页刚打开时点搜索框会被忽略（小米 18 Pro Max 实测）：点完要看到输入框才往下走，没打开就再点。"""
        self.miss = 0
        self.d.shell("am start -f 0x10008000 -a android.settings.SETTINGS")
        opened = False
        for _ in range(4):
            xy, t0 = None, time.time()
            while time.time() - t0 < 3 and not xy:
                for t, (l, tp, r, b), _ in self.texts():
                    if (box and box in t) or (not box and self.BOX.search(t)):
                        xy = ((l + r) // 2, (tp + b) // 2); break
                if not xy:
                    time.sleep(0.15)
            if not xy:
                break
            time.sleep(0.4)                      # 首页还在加载时点击会被吞
            self.click(*xy)
            t0 = time.time()
            while time.time() - t0 < 2 and not opened:
                opened = self.edit_ready()
                if not opened:
                    time.sleep(0.15)
            if opened:
                break
        if not opened:
            self.say(f"  ✗ 设置搜索框没打开，跳过「{kw}」")
            return False
        if not self.type_text(kw):
            self.say(f"  ✗ 设置搜索框输入「{kw}」失败，跳过")
            return False
        # 输入框里也有同一段文字；只认非输入框的结果，不能点回搜索框后假报成功。
        t0, xy = time.time(), None
        while time.time() - t0 < 3:
            for t, (l, tp, r, b), n in self.texts():
                if t == (entry or kw) and not EDIT.search(n.get("class", "")):
                    xy = ((l + r) // 2, (tp + b) // 2)
                    break
            if xy:
                break
            time.sleep(0.15)
        if not xy:
            self.say(f"  ✗ 没搜到「{entry or kw}」，跳过")
            return False
        before = self.focus()
        self.click(*xy)
        t0 = time.time()
        while time.time() - t0 < 3:
            if self.focus() != before or not self.edit_ready():
                time.sleep(0.3)
                return True
            time.sleep(0.15)
        self.say(f"  ✗ 搜索结果「{entry or kw}」没有打开，跳过")
        return False

    def start(self, pkg, activity=None, settle=1.2, foreground=None):
        """拉起 App；之后 settle 秒内冒出来的更新/推荐弹窗顺手点掉。"""
        self.miss = 0
        if activity:
            result = self.d.shell(f"am start -f 0x10008000 -n {pkg}/{activity}")
        else:
            self.d.app_stop(pkg)
            result = self.d.shell(f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1")
        if result.exit_code or re.search(r"Error|Exception|No activities found|monkey aborted", result.output, re.I):
            # 同品牌参考脚本里的 App 本机可能没装或换了包名（#87 #165），说清楚，别报成打开失败。
            if "package:" not in self.d.shell(f"pm path {pkg}").output:
                raise RuntimeError(f"本机没有安装 {pkg}，跳过本段")
            raise RuntimeError(f"无法打开 {pkg}：{result.output.strip()[-250:]}")
        deadline = time.monotonic() + 5
        expected = foreground or pkg
        while self.focus().split("/", 1)[0] != expected:
            if self.focus().split("/", 1)[0] in PERMISSION_CONTROLLERS:
                self.dismiss()
            if time.monotonic() >= deadline:
                raise RuntimeError(f"{pkg} 没有进入前台，跳过本段")
            time.sleep(0.2)
        def check_foreground():
            current = self.focus().split("/", 1)[0]
            # 权限申请可能在首页已出现后才弹出，也只能拒绝；不在其他 App 上找关闭按钮。
            if current in PERMISSION_CONTROLLERS:
                until = time.monotonic() + 3
                while current in PERMISSION_CONTROLLERS or not current:
                    if time.monotonic() >= until:
                        break
                    if current and not self.dismiss():
                        break
                    time.sleep(.2)
                    current = self.focus().split("/", 1)[0]
            if current != expected:
                raise RuntimeError(f"{pkg} 启动后离开前台，停止本段以免操作其他 App")

        # 旧版商店冷启动可能暂时没有可读文字；空白不等于广告，不能盲按返回退出 App。
        t = time.time()
        while time.time() - t < 8:
            check_foreground()
            if self.texts():               # 一两个标签也可能是正常首页
                break
            self.dismiss()                # 仅尝试可识别的关闭 / 拒绝按钮
            time.sleep(.2)
        else:
            raise RuntimeError(f"{pkg} 启动后 8 秒仍读不到页面，停止本段；请确认首页已加载后重试")

        t = time.time()                    # 首屏加载较慢时，也要给引导/更新弹窗留下处理时间
        while time.time() - t < settle:
            check_foreground()
            self.dismiss()
            time.sleep(0.4)
        check_foreground()


def main():
    a = sys.argv[1:]
    if a in ([], ["--help"], ["-h"]):
        print(__doc__); return
    if len(a) < 3 or a[0] != "-s":
        print(__doc__); sys.exit(1)
    try:
        with Phone(a[1]) as p:
            execute(p, a[2], a[3:])
    except RuntimeError as e:
        # 断线、读屏服务被占用、启动失败：给出原因，不打印 Python 报错堆栈（错误日志 10-27）
        print(f"✗ {e}", flush=True)
        sys.exit(1)
    except Exception as e:
        gone = adb_link.lost_from(e, a[1])     # 读屏库的断线异常不是 RuntimeError（错误日志 10-28）
        if gone is None:
            raise
        print(f"✗ {gone}", flush=True)
        sys.exit(1)


def execute(p, cmd, rest):
    if cmd == "check":
        if p.locked():
            sys.exit("手机锁屏了，请机主解锁后重试")
        if not list(p.tree().iter("node")):
            sys.exit("读屏服务已连接，但没有读到页面节点，请解锁并停在设置首页后重试")
        print(f"读屏检查通过：{p.W} × {p.H}；未点击或修改任何开关")
    elif cmd == "ls":
        p.ls()
    elif cmd == "tap":
        for t in rest:
            p.tap(t)
        p.ls()
    elif cmd == "off":
        keep = rest[0].split(",") if rest and rest[0] else ()
        t = time.time(); n = p.off(keep=keep)
        print(f"关了 {n} 个，{time.time()-t:.1f} 秒")
    elif cmd == "scan":
        t = time.time(); seen = {}
        for _ in range(60):
            for k, c, _ in p.switches():
                seen.setdefault(k, c)
            if not p.scroll_more():
                break
        for k, c in seen.items():
            print(f"  [{'开' if c else '关'}] {k}")
        if not seen:
            p.top(); p.ls()
        print(f"{len(seen)} 个开关，开着 {sum(seen.values())} 个，{time.time()-t:.1f} 秒")
    elif cmd == "only":
        t = time.time(); n = p.off(only=rest[0].split(","))
        print(f"关了 {n} 个，{time.time()-t:.1f} 秒")
    elif cmd == "run":
        if not p.wait_unlocked():
            print("✗ 手机一直锁屏，本步骤没有执行。请解锁手机、保持亮屏后重试"); sys.exit(2)
        g = {"p": p, "__name__": "__recipe__", "ONLY": rest[1:]}
        with open(rest[0], encoding="utf-8") as f:
            src = f.read()
        build = p.d.shell("getprop ro.build.display.id").output.strip()
        osv = p.d.shell("getprop ro.mi.os.version.incremental").output.strip()     # 小米：HyperOS 版本号
        m = re.search(r'^BUILD\s*=\s*"([^"]+)"', src, re.M)
        if m and not (build.startswith(m.group(1)) or osv.startswith(m.group(1))):
            os.environ["AAC_REF"] = "1"
            print(f"⚠ 机型脚本是按 {m.group(1)} 录的，这台是 {osv or build}：用安全模式跑（只关点名的开关），没找到的段会快速跳过")
        t = time.time()
        try:
            exec(src, g)
        except adb_link.DeviceLost as e:
            print(f"\n✗ {e}\n已停止：关了 {len(p.changed)} 个，{time.time()-t:.0f} 秒", flush=True)
            sys.exit(1)
        print(f"\n机型脚本跑完：关了 {len(p.changed)} 个，{time.time()-t:.0f} 秒")
        import json, datetime
        logdir = os.environ.get("AAC_BACKUPS") or os.path.dirname(os.path.abspath(rest[0]))
        try:
            os.makedirs(logdir, exist_ok=True)
            with open(os.path.join(logdir, "run-log.txt"), "a", encoding="utf-8") as f:
                f.write(f"\n# {datetime.datetime.now():%Y-%m-%d %H:%M} {' '.join(rest[1:]) or '全跑'}  {time.time()-t:.0f}s\n")
                for pg, tt in p.changed:
                    f.write(f"{pg}\t{tt}\n")
        except OSError:
            pass
        if g.get("FAILED_STEPS"):
            print("未完成步骤：" + "、".join(g["FAILED_STEPS"]), flush=True)
            sys.exit(1)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
