# OPPO Find X8s（PKT110），ColorOS 17.0.0.102(CN01) / Android 17。
# 路径与开关来自 2026-10-28 在 PKT110 真机上逐段实测。
# 只覆盖下面列出的入口：软件商店在 ColorOS 17 的设置页里没有「隐私」「服务管理」，
# 商店首页的推广位无法关闭；负一屏（速览）没有「推荐服务」分组，未处理。
# 详见 docs/清单/OPPO-ColorOS.md。
BUILD = "PKT110_17.0.0.102(CN01)"
import time

ONLY = globals().get("ONLY") or []
FAILED_STEPS = []
VERIFIED_SWITCHES = 0
# 下拉搜索「场景服务」里的两个内容资讯入口，各在一级页里。
SCENE_SERVICES = ["小红书资讯", "视界日报"]


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def step(name):
    def decorate(action):
        if ONLY and name not in ONLY:
            return action
        print(f"\n== {name}", flush=True)
        p.miss = 0
        try:
            require(not p.locked(), "手机锁屏了，请机主解锁后再跑")
            action()
        except Exception as error:
            FAILED_STEPS.append(name)
            print(f"  ✗ 未完成：{error}", flush=True)
        return action
    return decorate


def tap(name, scrolls=4, exact=True):
    require(p.tap(name, exact=exact, scrolls=scrolls), f"未找到入口「{name}」")


def read_switches(max_screens):
    current = {}
    for index in range(max_screens):
        current.update({title: on for title, on, _ in p.switches()})
        if index + 1 == max_screens or not p.scroll_more():
            break
    return current


def close_named(names, page, max_screens=1, reopen=None):
    """关掉点名的开关并回读确认；其他开关的状态不能变。
    reopen：有的页点完开关会弹确认框、确认后退回上一级，回读前用这个回调重新进一次。"""
    global VERIFIED_SWITCHES
    p.top(max_screens)
    before = read_switches(max_screens)
    require(all(name in before for name in names), f"{page}：未识别全部目标开关，未操作")
    p.top(max_screens)
    p.off(only=names, page=page, max_screens=max_screens)
    if reopen:
        reopen()
    p.top(max_screens)
    current = read_switches(max_screens)
    require(all(current.get(name) is False for name in names), f"{page}：回读未确认关闭")
    require(all(current.get(name) == state for name, state in before.items() if name not in names),
            f"{page}：其他开关状态变化，请核对")
    VERIFIED_SWITCHES += len(names)


def close_all(page, max_screens):
    """整页关掉所有开关（逐 App 的广告跟踪列表用），关完回读确认。"""
    global VERIFIED_SWITCHES
    p.top(max_screens)
    before = read_switches(max_screens)
    require(before, f"{page}：没读到开关，未操作")
    p.off(page=page, max_screens=max_screens)
    p.top(max_screens)
    current = read_switches(max_screens)
    still = sorted(name for name, on in current.items() if on)
    require(not still, f"{page}：回读未确认关闭（仍有 {len(still)} 项开着）")
    VERIFIED_SWITCHES += len(before)


@step("广告跟踪")
def _():
    """设置 → 隐私与安全 → 设备标识与广告 → 广告跟踪。
    每个 App 一个开关、没有总开关，本机 96 个 App，分五屏。"""
    p.d.shell("am start -f 0x10008000 -a android.settings.SETTINGS"); time.sleep(1.2)
    p.miss = 0
    if not p.tap("隐私", exact=True):          # ColorOS 16 叫「隐私」，17 改叫「隐私与安全」
        p.miss = 0
        tap("隐私与安全")
    tap("设备标识与广告")
    tap("广告跟踪")
    time.sleep(1)
    close_all("广告跟踪", max_screens=40)


@step("下拉搜索")
def _():
    """下拉搜索 → 设置：服务设置里的「资讯服务」，场景服务里的两个内容资讯入口。"""
    p.d.shell("input keyevent HOME"); time.sleep(.6)
    p.d.shell(f"input swipe {p.W//2} {p.H*3//10} {p.W//2} {p.H*7//10} 300"); time.sleep(1.5)
    p.d.shell("input keyevent BACK"); time.sleep(.4)
    tap("设置", scrolls=0)
    close_named(["资讯服务"], "下拉搜索·资讯服务")
    if p.tap("场景服务", exact=True, scrolls=0):
        for name in SCENE_SERVICES:
            tap(name, scrolls=0)
            close_named([name], f"下拉搜索·{name}")
            p.back()
    p.back(2)


@step("浏览器")
def _():
    """浏览器 → 隐私：广告管理里的开屏/资讯列表广告、个性化管理里的个性化广告推荐。
    「摇一摇广告」在两个上级开关关掉后仍显示为开且点不动（系统置灰），不单独点。"""
    p.start("com.heytap.browser")
    # 这台机上「我的」点进去是菜单浮层，直接用公开入口进设置页
    p.d.shell("am start -n com.heytap.browser/.settings.component.BrowserPreferencesPage"); time.sleep(1.5)
    require("com.heytap.browser" in p.focus(), "浏览器设置页没有打开")
    tap("隐私")
    if p.tap("广告管理", exact=True, scrolls=0):
        close_named(["开屏广告", "资讯列表广告"], "浏览器·广告管理")
        p.back()
    tap("个性化管理")
    close_named(["个性化广告推荐"], "浏览器·个性化管理")


@step("主题商店")
def _():
    """主题商店 → 我的 → 设置：服务管理 → 消息与广告；隐私 → 个性化推荐设置。
    「个性化推荐设置」点下去先弹确认框，确认后页面退回「设置」，回读前要重新进一次。"""
    def to_privacy():
        p.start("com.heytap.themestore")
        p.d(text="我的").click(); time.sleep(1.5)
        tap("设置", scrolls=0)
        tap("隐私", scrolls=0)

    p.start("com.heytap.themestore")
    p.d(text="我的").click(); time.sleep(1.5)
    tap("设置", scrolls=0)
    tap("服务管理", scrolls=0)
    tap("消息与广告", scrolls=0)
    close_named(["消息通知", "开屏广告"], "主题·消息与广告")
    p.back(2)
    to_privacy()
    close_named(["个性化推荐设置"], "主题·个性化推荐", reopen=to_privacy)


@step("视频")
def _():
    """OPPO 视频 → 我的（底部标签）→ 设置 → 个性化管理。"""
    p.start("com.heytap.yoli")
    p.d(text="我的").click(); time.sleep(1.5)
    tap("设置", scrolls=0)
    tap("个性化管理")
    close_named(["个性化广告推荐", "个性化内容推荐"], "视频·个性化管理")


@step("游戏中心")
def _():
    """游戏中心 → 我的 → 设置 → 隐私开关设置 → 个性化推荐管理。
    「我的」页带「页面升级」弹窗，先关掉；「设置」那一行的文字是「设置,有新通知」。"""
    p.start("com.nearme.gamecenter")
    p.d(text="我的").click(); time.sleep(1.5)
    if p.find("我知道了", exact=True):
        p.tap("我知道了", exact=True, scrolls=0); time.sleep(1.2)
    tap("设置", scrolls=0, exact=False)
    tap("隐私开关设置")
    tap("个性化推荐管理")
    close_named(["个性化推荐"], "游戏中心·个性化推荐")


@step("小布建议")
def _():
    """设置 → OPPO AI → 小布建议 → 内容资讯 → 资讯服务。
    快递、航班、日程提醒、商圈服务在同一页，保持不动。"""
    p.d.shell("am start -f 0x10008000 -a android.settings.SETTINGS"); time.sleep(1.2)
    tap("OPPO AI")
    tap("小布建议")
    tap("内容资讯")
    tap("资讯服务", scrolls=0)
    close_named(["资讯服务"], "小布建议·资讯服务")


print(f"\n已回读确认 {VERIFIED_SWITCHES} 项；未完成步骤 {len(FAILED_STEPS)} 个", flush=True)
