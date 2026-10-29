"""给文档截客户端各页面：程序自己切换页面、截自己的窗口，不模拟鼠标。
用法（macOS，手机连着且已解锁）：gui/.venv/bin/python gui/shots.py <序列号> <输出目录>"""
import os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app, webview, Quartz

SERIAL, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)


def wid():
    for w in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID):
        if w.get("kCGWindowOwnerPID") == os.getpid() and w.get("kCGWindowName") == app.APP_NAME and w.get("kCGWindowLayer") == 0:
            return w["kCGWindowNumber"]


def shot(name):
    time.sleep(0.6)
    subprocess.run(["screencapture", "-x", "-o", "-l", str(wid()), os.path.join(OUT, name + ".png")])
    print("截图", name, flush=True)


def wait_js(w, expr, timeout=120):
    t = time.time()
    while time.time() - t < timeout:
        if w.evaluate_js(expr):
            return True
        time.sleep(0.5)
    print("等待超时：", expr, flush=True)
    return False


def run(w):
    time.sleep(3)
    wait_js(w, "!!document.querySelector('.dev .btn')")
    shot("gui-1-connect")
    w.evaluate_js("showConnect(); document.querySelector('#tutbox').open = true;")
    wait_js(w, "!!document.querySelector('.dev .btn')")
    w.evaluate_js("document.querySelector('#tutbox').scrollIntoView()")
    shot("gui-2-tutorial")
    w.evaluate_js("document.querySelector('.dev .btn').click()")
    wait_js(w, "S.step === 2 && !!document.querySelector('.grid')")
    shot("gui-3-detect")
    w.evaluate_js("showChoose()")
    wait_js(w, "!!document.querySelector('#chancount') && document.querySelector('#chancount').textContent !== '' || (S.chans && S.chans.length === 0)")
    shot("gui-4-choose")
    w.evaluate_js("document.querySelector('main').scrollTop = 99999")
    shot("gui-5-choose-more")
    # 执行页和完成页：只跑「快照 + 收尾」，不改手机设置
    w.evaluate_js(f"api.start('{SERIAL}', {{backup: true, model: S.status.info.model, steps: [], channels: [], quickapp: false, ads: []}}).then(() => {{ S.logNext = 0; showRun(); }})")
    wait_js(w, "S.step === 5", 120)
    # 执行太快，截不到进行中的页面：用这次的真实日志重新显示执行页（停在第 2 步）
    w.evaluate_js("""(async () => { const r = await api.poll(0); const done = r; showRun(); clearInterval(pollJob);
      const lines = r.lines.filter(l => l.trim()).slice(0, 3);
      document.querySelector('#log').textContent = lines.join('\\n') + '\\n';
      document.querySelector('#jt').textContent = '第 2 / 2 步：收尾';
      document.querySelector('#js').textContent = '已用 1 秒';
      document.querySelector('#jb').style.width = '75%'; window._done = done; })()""")
    time.sleep(1.5)
    shot("gui-6-run")
    w.evaluate_js("showDone(window._done)")
    wait_js(w, "S.step === 5", 120)
    shot("gui-7-done")
    w.evaluate_js("openFeedback('bug').then(() => { document.querySelector('#fbtext').value = '执行到「关闭营销通知」时卡住了'; document.querySelector('details:has(#fbdiagtext)').open = true; })")
    wait_js(w, "!!document.querySelector('#fbdiagtext')")
    shot("gui-8-feedback")
    w.evaluate_js("closeModal(); openRestore()")
    shot("gui-9-restore")
    w.destroy()


api = app.Api()
w = webview.create_window(app.APP_NAME, os.path.join(app.BASE, "gui", "web", "index.html"), js_api=api, width=1080, height=780)
webview.start(run, w)
