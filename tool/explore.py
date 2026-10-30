#!/usr/bin/env python3
"""新品牌自动探路：挨个打开系统 App → 我的 → 设置 → 每个子页，列出像广告/推荐的开关。只读，不拨开关。
  explore.py -s SERIAL [包名 …]        不给包名=自动挑系统里带界面的厂商 App
输出：探路-<型号>.tsv（包名、页面路径、开关、当前状态），给人挑完写进 recipe.py。
遇到「同意」协议页直接跳过；只点「以后再说/取消/禁止」这类拒绝按钮。
"""
import re, sys, time, os
for _st in (sys.stdout, sys.stderr):
    try:
        _st.reconfigure(encoding="utf-8", errors="replace")   # Windows 控制台默认不是 UTF-8
    except Exception:
        pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fast import Phone

AD = re.compile(r"广告|推荐|推送|营销|资讯|热搜|热点|热榜|热门|榜单|个性化|活动|福利|运营|精选|猜你|推广|开屏|摇一摇|轮播|提示词|兴趣|定向|商业|优惠|画报|新闻")
ENTRY_SKIP = re.compile(r"侧边栏|返回|关于|检查更新|版本|清单|协议|声明|帮助|客服|反馈|退出|注销|账号|缓存|清除|恢复默认|备案|许可|开源")
ME = ("我的", "我", "个人中心", "更多")
SET = ("设置", "设置中心")


def entries(p, pkg):
    """当前页可点的文字条目（不带开关的行），作为子页候选。pkg=这一页属于哪个 App。"""
    sw_rows = {xy[1] // 60 for _, _, xy in p.switches()}
    out = []
    for t, (l, tp, r, b), n in p.texts():
        cy = (tp + b) // 2
        if len(t) > 12 or len(t) < 2 or cy < p.H * 0.1 or ENTRY_SKIP.search(t) or cy // 60 in sw_rows:
            continue
        if n.get("package") != pkg or l > p.W * 0.5:     # 别的窗口的字、右侧的取值文字（默认/百度/已防护）
            continue
        if re.fullmatch(r"[\d.%:：/ ]+|已开启|已关闭|开启|关闭|未开启", t):
            continue
        out.append(t)
    return list(dict.fromkeys(out))


def read_page(p, path, rows, pkg):
    seen = set()
    for _ in range(8):
        for t, c, _ in p.switches():
            if t and t not in seen:
                seen.add(t)
                rows.append((pkg, " > ".join(path), t, "开" if c else "关", "★" if AD.search(t) else ""))
        if not p.scroll_more():
            break
    p.top(6)


def open_settings(p, pkg, rows=None):
    p.start(pkg, settle=2.5)
    tx = [t for t, _, _ in p.texts()]
    if "同意" in tx and len(tx) < 30:
        return "协议页"
    for me in ME:
        if p.find(me, exact=True, edge_ok="tab"):
            p.tap(me, exact=True, scrolls=0); break
    if not any(p.tap(s, exact=True, scrolls=3) for s in SET):
        return "没找到设置入口"
    return None


def explore(p, pkg, rows):
    print(f"\n### {pkg}")
    err = open_settings(p, pkg)
    if err:
        print("  " + err); rows.append((pkg, "", f"（{err}）", "", "")); return
    home = p.focus()
    read_page(p, ["设置"], rows, pkg)
    todo = entries(p, home.split("/")[0])[:25]      # 只收前台这个 App 的文字，浮窗与状态栏不算
    done = set()
    for e in todo:
        if e in done:
            continue
        done.add(e)
        if not p.tap(e, exact=True, scrolls=4):
            continue
        read_page(p, ["设置", e], rows, pkg)
        p.back()
        if p.focus() != home:
            p.back()
        if p.focus() != home:                     # 还回不去：重新进设置页，接着探下一个
            if open_settings(p, pkg):
                print(f"  （从「{e}」回不到设置页，停）"); break
    p.d.app_stop(pkg)


def main():
    a = sys.argv[1:]
    p = Phone(a[1], log=False)
    pkgs = a[2:]
    if not pkgs:
        vendor = re.compile(r"^(com\.(hihonor|honor|huawei|oplus|coloros|heytap|nearme|oppo|vivo|bbk|iqoo|miui|xiaomi|mi|android\.browser)|cn\.honor)")
        out = p.d.shell("cmd package query-activities --brief -a android.intent.action.MAIN -c android.intent.category.LAUNCHER").output
        pkgs = sorted({l.strip().split("/")[0] for l in out.splitlines() if "/" in l and vendor.match(l.strip())})
    model = p.d.shell("getprop ro.product.model").output.strip()
    rows, t0 = [], time.time()
    for pk in pkgs:
        try:
            explore(p, pk, rows)
        except Exception as e:
            print(f"  ✗ {e}")
    fn = f"探路-{model}.tsv"
    with open(fn, "w", encoding="utf-8") as f:
        f.write("包名\t页面\t开关\t状态\t像广告\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    star = [r for r in rows if r[4] and r[3] == "开"]
    print(f"\n探了 {len(pkgs)} 个 App，{time.time()-t0:.0f} 秒；开着的疑似广告开关 {len(star)} 个 → {fn}")
    for r in star:
        print(f"  {r[0]}  {r[1]}  「{r[2]}」")


if __name__ == "__main__":
    main()
