"""纯重构的对拍驱动：同一份页面样本喂给两份 `tool/`，比较可观察输出。

基线取改动前的 worktree，样本取本仓库 `tests/` 里的 `<hierarchy>` 字面量：

    git worktree add /tmp/aac-baseline <改动前的提交>
    python tests/compare_phone_state.py /tmp/aac-baseline/tool

比三处：`Phone.texts()`（页面 × 两种屏尺寸 × 读屏策略开 / 关）、
`explore.entries()`（页面 × 包名）、`Phone.off()`（安全模式开 / 关）。
两边必须各起一个子进程：模块名相同，同进程里 import 不了两份 `fast`。

结论不只看「相等」——驱动同时打印守卫数字（策略 / 包名 / 安全模式是否真的改变了输出），
全是 0 就说明对拍什么也没测到。
"""
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

TESTS = Path(__file__).resolve().parent

SIZES = ((1080, 2340), (720, 1600))

TWO_WINDOWS = '''<hierarchy rotation="0">
  <node package="com.android.settings" text="隐私" bounds="[60,300][400,360]"/>
  <node package="com.example.overlay" text="别的窗口" bounds="[60,420][400,480]"/>
  <node package="com.android.settings" text="广告" bounds="[60,540][400,600]"/>
</hierarchy>'''

# 一个普通广告开关（安全模式不该碰）+ 一个保护类开关（安全模式照样要拨开）
SAFE_MODE_PAGE = '''<hierarchy rotation="0">
  <node package="com.android.settings" clickable="true" bounds="[0,300][1080,380]">
    <node text="个性化推荐" bounds="[60,310][400,370]"/>
    <node class="android.widget.Switch" checkable="true" checked="true" bounds="[950,300][1060,380]"/>
  </node>
  <node package="com.android.settings" clickable="true" bounds="[0,500][1080,580]">
    <node text="限制广告跟踪" bounds="[60,510][400,570]"/>
    <node class="android.widget.Switch" checkable="true" checked="false" bounds="[950,500][1060,580]"/>
  </node>
</hierarchy>'''


def dump(tool_dir):
    """跑一份 `tool/`，把三处可观察输出整理成 JSON。"""
    sys.path.insert(0, str(TESTS))
    sys.path.insert(0, tool_dir)
    import fast
    import explore
    import fixtures

    def page_phone(xml, size):
        p = fixtures.phone_stub("test", fast_mod=fast)
        p.W, p.H = size
        p.d = fixtures.Device(fixtures.Timeline([(0.0, xml)]), size, fixtures.Clock())
        return p

    def texts():
        out = []
        for label, xml in fixtures.all_pages(str(TESTS)):
            for size in SIZES:
                for flag in (False, True):
                    p = page_phone(xml, size)
                    p.sysui = flag            # 改前的名字
                    p.systemui_text = flag    # 改后的名字
                    try:
                        got = [(t, b) for t, b, _ in p.texts(ET.fromstring(xml))]
                    except Exception as e:
                        got = ["ERROR", type(e).__name__]
                    out.append({"id": f"{label}|{size}|{flag}", "got": got})
        return out

    def entries():
        takes_pkg = explore.entries.__code__.co_argcount == 2      # 改前 1 个参数，改后 2 个
        out = []
        for label, xml in [("two-windows", TWO_WINDOWS)] + fixtures.all_pages(str(TESTS)):
            p = page_phone(xml, SIZES[0])
            for pkg in ("com.android.settings", ""):
                try:
                    if takes_pkg:
                        got = explore.entries(p, pkg)
                    else:
                        p.pkg_now = pkg
                        got = explore.entries(p)
                except Exception as e:
                    got = ["ERROR", type(e).__name__]
                out.append({"id": f"{label}|{pkg}", "got": got})
        return out

    def off():
        out = []
        for safe in (True, False):
            clock = fixtures.Clock()
            fixtures.install_clock(fast, clock)
            lines = []
            p = fixtures.fake_phone(clock=clock, stages=[(0.0, SAFE_MODE_PAGE)], fast_mod=fast,
                                    say=lines.append)
            p.safe_mode = safe
            if safe:
                os.environ["AAC_REF"] = "1"      # 改前靠环境变量；改后忽略它
            else:
                os.environ.pop("AAC_REF", None)
            done = p.off(page="系统·广告服务")
            os.environ.pop("AAC_REF", None)
            out.append({"id": f"safe={safe}", "done": done, "clicks": clock.clicks,
                        "changed": p.changed, "lines": lines})
        return out

    return {"texts": texts(), "entries": entries(), "off": off()}


def collect(tool_dir):
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--dump", str(tool_dir)],
                          capture_output=True, text=True, encoding="utf-8")
    if proc.returncode:
        sys.exit(f"跑不通 {tool_dir}：\n{proc.stderr}")
    return json.loads(proc.stdout)


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--dump":
        print(json.dumps(dump(sys.argv[2]), ensure_ascii=False, sort_keys=True))
        return
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    before, after = collect(sys.argv[1]), collect(str(TESTS.parent / "tool"))
    bad = 0
    for key in before:
        bm, am = {x["id"]: x for x in before[key]}, {x["id"]: x for x in after[key]}
        diff = [i for i in bm if bm[i] != am.get(i)]
        bad += len(diff)
        print(f"{key}: {len(bm)} 组，一致 {len(bm) - len(diff)}，不一致 {len(diff)}")
        for i in diff[:5]:
            print(f"  {i}\n    改前 {json.dumps(bm[i], ensure_ascii=False)}\n    改后 {json.dumps(am.get(i), ensure_ascii=False)}")
    # 守卫：对拍必须真的走到目标分支，否则「两边一样」是必然的
    t = {x["id"]: x["got"] for x in after["texts"]}
    flipped = sum(1 for k in t if k.endswith("|True") and t[k] != t[k[:-5] + "|False"])
    e = {x["id"]: x["got"] for x in after["entries"]}
    filtered = sum(1 for k, v in e.items() if k.rsplit("|", 1)[1] == "com.android.settings"
                   and v != e[k.rsplit("|", 1)[0] + "|"])
    clicks = {x["id"]: x["clicks"] for x in after["off"]}
    print(f"守卫：读屏策略改变输出的组数 {flipped}，包名过滤改变输出的页数 {filtered}，"
          f"安全模式点击 {clicks.get('safe=True')} vs {clicks.get('safe=False')}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
