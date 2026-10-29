# CLAUDE.md

本仓库的操作规范写在 [AGENTS.md](AGENTS.md)。开工前读完它。

## 开发

- 回归：`python -m unittest discover -s tests`；本机用仓库根的 `.venv/bin/python`（系统 python 缺 adbutils，会报一串 ModuleNotFoundError）。只装 `requirements.txt` 就够，不需要 pywebview / pillow。
- CI：`.github/workflows/test.yml` 在 PR 和 main 推送时自动跑同一套；`build-windows.yml` 只在 `v*` 标签或手动触发时打包，不守 PR。

## 2026-10-29 一夜的上报、GitHub 新 Issue、合并 8 个 PR（0.2.7）

- 0.2.6 一夜 68 份上报多数已由下节修掉；新问题与处理见 CHANGELOG「10-29」。原始导出在 `.private/reports/`、`.private/github/`。
- `fast.find()` 先找完全相同的文字；`tap()` 传 `nav=True`，包含匹配跳过开关所在行（`switch_row()`），#247 误关「边下边玩」。`confirm()` 合了 #249（content-desc）、#239（子节点文字）、#248（屏幕外）。
- 应用通知整体关闭（`POST_NOTIFICATIONS` 被拒）而 dumpsys notification 看不出来时，渠道记为 `APP_DENIED`，不算失败。焦点读不到时看 `mFocusedApp`。安卓 8 / 9 的 dumpsys 段名 `per-package config:`。
- adb 下载：固定 platform-tools 37.0.1，Google → 腾讯云镜像，核对 SHA-256，最后才下官网最新版。升级版本时改 `ADB_PINNED`，校验值按 Google `repository2-3.xml` 的 SHA-1 核对。
- 提示音 `gui/web/chime.wav` 由 `gui/make_chime.py` 生成；测试设 `AAC_NO_SOUND=1` 不出声。
- 合并 #249 #248 #239 #262 #243 #237 #232 #231（随 0.2.7 推送）。GitHub 上的 Issue 还没回复；#275 #277 是之后新来的 PR，待审。

## 2026-10-28 0.2.6 当天的错误日志与三项新功能（0.2.7）

- 0.2.6 发布后 4 小时 33 份报告，归类与处理见 CHANGELOG「未发布」。华为 / 旧版荣耀 9 份是真问题：0.2.6 找到的「行」是一张卡片，里面不止一个开关；`own_row()` 从渠道名往上找第一个只含一个开关的控件。卡片结构是推断，失败时日志带 `chain()` 控件链（不含文字），下一轮上报核对。
- vivo：直达渠道页按规则不能直接用，认出 vivo（`p.vivo_seen`）后不再走直达链接；`via_app_page` 等上一页换下去（`titled()`）再读。OriginOS Ocean 的通知页在 `com.android.systemui`，读它时 `p.sysui=True`。
- 一批跑完后「未确认」类失败重试一次（本机关成功过、最多 10 个）。读屏库的断线异常经 `adb_link.lost_from()` 认成断开。
- 软件名：`tool/applabels.dex`（源码 `tool/applabels/`，`build.sh` 重建）经 `app_process` 读应用名，用完删除；只进界面和清单第四列，不进日志。
- 暂停：`AAC_PAUSE_FILE` 存在时 `fast.pause_point()` 等待。安全位置只有三处：机型脚本段首的锁屏检查、营销通知两个渠道之间、客户端两步之间。chan_fast 里把 `pause_at_lock_check` 关掉，渠道里面的锁屏检查不暂停。停止后仍跑收尾。
- 新版本提示读 OSS 上的 `android-ad-cleaner-latest.json`，发版后要更新它（步骤记在本机 `CLAUDE.local.md`）。
- 237 项回归通过；模拟器验证读名、扫描、关闭 / 暂停 / 继续 / 还原。华为、旧版荣耀、vivo 没有真机。

## 2026-10-28 错误日志与社区 PR（0.2.6，已发布）

- 0.2.5 上线一天收到 122 份确认上报的错误日志，归类与处理见 CHANGELOG「未发布」。原始日志只在本机被忽略的 `.private/`，不进仓库。
- 锁屏判断统一在 `adb_link.keyguard_showing()`：ColorOS 没有 `isKeyguardShowing`，焦点在 NotificationShade 又没有锁屏字段就按锁屏处理；通知栏被拉下时先 `cmd statusbar collapse`。锁屏时点亮屏幕等机主解锁（`wait_unlocked`），不代替解锁。
- 系统锁定（灰色开关）的渠道不算失败；手机确实断开后客户端跳过剩余步骤；引擎和 chan_fast 的启动失败只打印原因。
- 同品牌参考脚本由 `run.py` 的 `REFERENCE` 指定，不再按目录名排序取第一份。
- 合并社区 PR：#3 #10 #15 #27 #72 #100 #107 #152 #198 #204。关闭 #4（18 Fold 已由 M154FF 覆盖，且改浏览器主页）、#19（引擎已有更稳的退路）、#20（整包关通知不做）、#108（设备锁自带等待）。#54 待改两处后再合；#61 待 rebase；#32 超出范围暂不合。
- 204 项回归通过；Android 15 模拟器验证锁屏等待、通知栏收起、灰色渠道、关闭与还原。华为、ColorOS 锁屏、vivo OriginOS 3 没有真机，等下一版的上报复核。

## 2026-10-27 社区批量反馈（0.2.4，已发布）

- 137 个打开的 Issue 按日志归类，逐条去向见 [docs/09](docs/09-社区问题处理.md) 首节。原始 Issue 导出和 GBK 乱码还原不进仓库。
- 营销通知：ColorOS `com.oplus.notificationmanager`、荣耀 / 华为系统管家渠道页、三星 `entity_header_title`、Android 16 内联渠道行；回读只取 user 0；缩略 ID 与系统锁定渠道不进扫描结果；点击后同 App 其他渠道或总开关变化 → 原位点回并停止整批（`StopBatch`）。「未确认」日志附包名 / Activity。
- 小米「USB 调试（安全设置）」：`input keyevent 0` 返回 `INJECT_EVENTS` 即判定被拒，检测页阻止下一步，引擎点击时同样报错。锁屏只认 `isKeyguardShowing=true`。
- adb 掉线：`tool/adb_link.py`，等 `wait-for-device` 15 秒重试一次，仍断开就退出本步骤；不再把空输出当成功。营销通知一步也设插电常亮。客户端拒用低于 1.0.41 的 adb；Windows 等不到手机时只读查询设备管理器。
- Windows 剪贴板改 ctypes Unicode；反馈网址带诊断摘要。
- Mac Intel：旧 `gui/.venv-x86` 用了 Homebrew Python（minos 26.0），已改名 `gui/.venv-x86-brew-old`；`build_mac.sh` 只用 uv managed Python，并扫描包内文件最低系统版本，高于 11 即失败。
- 真机（无线调试）：一台 ColorOS 17 与荣耀 MagicOS 10 通知渠道来回测试通过，测试后回读一致。真机发现并修复：列表卡片里的 ✕ 不点、「不同意」算拒绝按钮、`AutoCompleteTextView` 搜索框。
- vivo OriginOS 6：总页与渠道页同 Activity，靠顶栏标题区分，App 名在总页找到渠道行的同一次读屏里记录。
- 162 项回归通过；Android 15 模拟器 scan / off / on 通过。三星、华为、荣耀内联布局与旧版仍无真机，以 docs/09 的「待复测」为准。

## 错误日志上报（客户端待发 0.2.5）

- 用户说明见 [docs/12](docs/12-错误日志上报.md)。服务器、数据库、部署与运维信息只记在本机 `CLAUDE.local.md` 和 `.private/`，不进仓库。

## 发版后上传百度网盘

官网另有一份放在机主的服务器上，发版后同步，方法记在本机 `CLAUDE.local.md`。

`gui/upload_baidu.sh [版本]`：从公开的 GitHub Release 下载安装包并核对 SHA256，经本机已登录的 BaiduPCS-Go 上传，生成分享链接写进 index.html 后提交推送。网盘账号凭证不进仓库和对话。

发完版还有一件事：按 [docs/agents/release-followup.md](docs/agents/release-followup.md) 把 `waiting-for-verify` 的 issue 逐条发给报告者复测。新版不送到报告者手上，这些 issue 永远关不掉。

## 2026-10-26 用户反馈改进（已随 0.2.4 发布）

- 用户称 0.2.3 仍失败，同时关闭 GKD、自动记账后可执行。只视作冲突排查线索，单一工具或模式尚未验证；取消“无需关闭无障碍服务”的绝对提示。错误时限时只读检查总开关 / 服务数量，不写服务名单到诊断，不自动停用无障碍。
- 错误摘要和完成页提示逐项暂停可暂停的自动化 / Shizuku 功能，再检查连接；保留依赖的辅助服务，结束后按需恢复。
- 找机位 / 机位推荐等功能通知在扫描、GUI 列表、旧清单和点击前均保护；不会自动恢复已有关闭状态，明确的 `chan-on` 仍可用。真实包名与渠道 ID 尚未取得，不能声称反馈手机已复测。
- 123 项回归通过；新原生 GUI 冒烟会检查模拟失败提示。处理与还原说明见 [docs/11-读屏冲突与功能通知保护.md](docs/11-读屏冲突与功能通知保护.md)。发布版仍为 0.2.3，本节不代表安装包已更新。

## 一加 ColorOS 14 实测（已随 0.2.4 发布）

- 2026-10-25 实测一加 Ace 2 Pro / PJA110 / ColorOS 14.0.0.812 / Android 14。专用脚本限定四段，3 个个性化推荐和 6 个商店推广位均已关闭并回读；不宣称系统广告跟踪、负一屏、主题等全部适配。
- 商店最初提示无网络，机主联网后手机时间也恢复正常，列表增加项目；补跨页预检查、指定目标关闭及其他开关保留检查。没有自动修改网络或时间。
- ColorOS 14 独立通知管理包按实测 Activity 识别，23 个营销渠道关闭，应用通知总开关不变。联网后发现非目标「天气提醒」重要级别从 4 变为 3，仍开启，原因未确认；最终新增 13 个渠道。保留这项差异，不能写成全部状态未变。
- 修复稀疏首屏误判、冷启动空白误按返回、前台检查和运行时权限拒绝；商店沿用先停止再从桌面启动，浏览器使用实测 Activity。专用脚本失败返回非零，成功改动日志仍保存。112 项回归通过。
- 机主明确同意后，广告服务、乐划和两个快应用组件已挂起；商店、搜索及负一屏未挂起。旧系统会重新拉起部分进程，收尾广告服务仍运行，不能称为彻底停止。最终四段完整复跑 155 秒，9 项已关闭、调整 0 项、失败 0 项。还原方法见 [docs/10-一加旧系统实测.md](docs/10-一加旧系统实测.md)。用户备份和原始日志仅在忽略的 backups/，禁止上传或打包。
- 已发布最新版仍为 0.2.3；本节源码更新没有替换安装包或校验值。发布下一版时再生成并验证新包。

## 当前维护状态（2026-10-25，0.2.3）

- 0.2.2 完整诊断已确认 Windows 11 / M154FF / OS4.0.27 的失败类型为 `AccessibilityServiceAlreadyRegisteredError`：手机端 UiAutomation 已注册。具体占用进程未知，不能断言是某个 App 或 Android 17 不兼容。
- 0.2.3 用 `tool/ui_session.py` 管理读屏会话，固定 uiautomator2 3.7.1；启动失败、操作异常与正常退出均清理本次持有的 adb 连接并等退出，再释放本机跨进程锁。只对已注册错误重试一次，不杀其他进程、不自动停用无障碍、不自动重启手机。
- 持续占用时提示退出旧版及其他自动化工具，仍失败由机主手动重启手机后只运行一个客户端。任务跳过后续读屏操作并保留首个诊断，收尾继续执行，但不宣称去广告全部完成。
- 91 项回归通过；Android 15 模拟器连续连接、真实并发拒绝、外部服务占用复现及释放后重连通过，外部服务保持可用，没有点击广告开关。M154FF / OS4.0.27 仍待反馈者复测。
- 0.2.2 的 adb 只读通知扫描、完整诊断和脱敏保留。Windows 打包覆盖两层 CLI、原生 GUI / 图片 / JS API；各平台本轮安装包验证见更新记录。标签工作流不覆盖公开安装包和校验值。

### 0.2.1 已完成的工作

- 已发布 **0.2.1**：Mac Apple / Intel 两个已签名、公证的 DMG，Windows 安装版及免安装版。旧版不会自动升级，已有备份目录保留。版本变化、验证和限制统一见 [CHANGELOG.md](CHANGELOG.md)。
- 66 项设备无关回归通过。M154FF / HyperOS OS4.0.24 前轮九段实测通过；本轮 Android 15 模拟器完成旋转及测试通知关闭还原，服务通知与应用总开关不变，环境已还原。Windows 新版构建、原生 GUI / 图片 / JS API 和安装包生成通过（Actions #40190341584，运行代码 `310a3f9`）。
- Intel 打包后曾卡在 PyObjC / libffi 分配回调内存；仅 `allow-jit` 不足，`gui/entitlements-intel.plist` 的权限只赋给 Intel 主程序，保留 hardened runtime 和库校验（`73239d8`）。Mac 发布必须签名后验证 GUI，再重新公证；不能只看签名或命令行成功。
- 最新 #21 小米 10 横屏/混合热榜、msa 不支持时的失败状态，以及 #24 荣耀服务通知选择已修复。小米 10 / 荣耀 Magic7 Pro 专用机型适配与真机回归仍未完成。#22 / #23 原生鸿蒙仍不支持，不把连接提示当作适配完成。逐项见 [社区问题处理记录](docs/09-社区问题处理.md)。
- #19 / #20 的渠道、备份、快应用问题按当前引擎实现，未整单合并 PR，不提供关闭整应用通知来替代渠道的功能。#10 / #15 专用脚本仍待审查；对应 vivo / 荣耀 / Windows 报告者环境及 Intel 真机的验证需补齐。
- 发布资源由 `gui/bundle_data.py` 统一列出；原始日志、备份、本地测试机型不随源码或安装包发布。新版网盘文件尚未上传，不复用旧版网盘链接冒充新包。

## Agent skills

### Issue tracker

GitHub Issues（`gh` CLI）。见 `docs/agents/issue-tracker.md`。

### Triage labels

默认五个角色标签，标签名即角色名，另加本仓库的 `waiting-for-verify`（已修、等真机复测）。见 `docs/agents/triage-labels.md`。

### Release followup

发版后要催哪些复测、报告者确认前不关闭哪些 issue，见 `docs/agents/release-followup.md`。每次发版都要过一遍这张清单。

### Domain docs

single-context：根目录 `CONTEXT.md` + `docs/adr/`。见 `docs/agents/domain.md`。
