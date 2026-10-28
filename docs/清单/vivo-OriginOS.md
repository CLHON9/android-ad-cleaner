# vivo / OriginOS 手动清单

路径实测机型：

- vivo X300 Ultra（V2547DA，OriginOS 6，Android 16），2026-10-22。
- vivo X300 Ultra（V2547A，OriginOS 7，Android 17），2026-10-25。

iQOO 结构相近。当前源码有 `recipes/vivo-V2547DA/` 和 `recipes/vivo-V2547A/` 两份机型脚本：V2547DA 整段自动执行仍待真机验证；V2547A 已真机整段跑通（重跑 126 秒）。两者系统版本不同，入口差异见下文「OriginOS 7（Android 17）的不同之处」，版本对不上时引擎会走安全模式。发布与验证范围见[更新记录](../../CHANGELOG.md)。
符号：🔴 关掉　🟢 保留　⚠️ 注意

---

## 1. 系统：广告与隐私

**路径**：设置 → 安全 → 更多安全设置 → 广告与隐私

- 🔴 个性化广告、个性化推荐、智能推荐服务

## 2. 负一屏

**路径**：桌面从左边缘向右滑 → 右上齿轮 → 更多设置 → 个性化推荐

- 🔴 服务推荐、资讯推荐
- 🔴 内容精选、热点资讯
- 🟢 小V建议（航班、快递提醒）
- ⚠️ 便捷生活 → 推荐服务不要关：那 10 个图标（扫码、手电筒、计算器等）都靠它补位，关了整块变空。

## 3. 全局搜索

**路径**：设置 → 系统管理与升级 → 全局搜索

- 🔴 首页展示内容 → 搜索框推荐词、推荐卡片
- 🔴 推荐热搜榜单 → 热门搜索
- 🔴 个性化内容 → 广告个性化
- 🟢 历史记录、应用建议、搜索结果个性化

## 4. 应用商店

**路径**：应用商店 → 我的 → 设置

- 🔴 关于 → 个性化推荐
- 🔴 服务管理 → 签到有礼、顶部轮播图、顶部栏目、开屏、摇一摇、悬浮窗、限时推广
- 🟢 我的服务、空间清理
- ⚠️ 开屏引导页「开启消息推送接收活动」取消勾选。

## 5. 浏览器

**路径**：浏览器 → 我的 → 齿轮

- 🔴 首页设置 → 极简首页；首页上滑展示资讯
- 🔴 隐私权限设置 → 个性化内容、第三方应用来源个性化推荐
- 🔴 网页浏览设置 → 网页下载相关推荐
- 🔴 更多设置 → WiFi 连接跳转新闻资讯
- ⚠️ 浏览器页面常跳到资讯、小说、领金币弹窗，一步一看。

## 6. 阅图锁屏

**路径**：设置 → 桌面、锁屏与壁纸 → 锁屏设置 → 阅图锁屏

- 🔴 阅图锁屏（关「锁屏横滑进入阅图」时总开关跟着关）
- 🟢 锁屏壁纸不变

## 7. i 管家

**路径**：i 管家 → 设置 → 关于 → 个性化设置

- 🔴 应用个性化推荐

## 8. 天气

**路径**：天气 → 设置 → 天气服务

- 🔴 天气相关热点资讯通知
- 🟢 气象预警、异常天气、地震预警

## 9. 营销通知

vivo 推送分类的渠道：`VPushChannel_0`（运营消息）、`VPushChannel_4`（精彩消息）、`VPushChannel_6`（推荐消息）。

- 🔴 支付宝运营、精彩；抖音运营、推荐；云服务推送；使用技巧智能推送建议；Play 特惠；Edge 热门资讯、突发新闻
- ⚠️ 最新 OriginOS 7 社区实测发现，`com.vivo.systemuiplugin` 页面的「允许通知」是应用级总开关，关闭会连订单、聊天通知一起关。当前源码在这个页面直接跳过，不继续按渠道操作；不能把它当作安全的渠道回退入口。依据 [PR #20](https://github.com/rddmwmddr/android-ad-cleaner/pull/20)，待其他版本逐一核实。
- ⚠️ 渠道页由 `com.vivo.systemuiplugin` 处理，不要强行停止它。

V2547A 上的实测数据（2026-10-25，改的就是页面顶部那个「允许通知」）：

| 操作 | dumpsys 里 AppSettings 的 importance | 该渠道自己的 mImportance |
|---|---|---|
| 点掉「允许通知」 | `DEFAULT` → `NONE`（整个 App 的通知全关） | `2`，一动不动 |
| 再点回来 | `NONE` → `DEFAULT` | `2` |

也就是说照着渠道名去关，实际关掉的是这个 App 的全部通知。**vivo 上请直接按「应用级」处理**，
不要指望只关某一个营销渠道。需要压掉某个 App 的推送就整包关（走 `POST_NOTIFICATIONS`
运行时权限，不用 root，可以还原）：

```bash
python3 tool/run.py -s <序列号> notif-off com.bbk.appstore com.vivo.browser
python3 tool/run.py -s <序列号> notif-on  com.bbk.appstore com.vivo.browser
# 等价写法（工具还没更新时也能用）：
adb shell pm revoke <包名> android.permission.POST_NOTIFICATIONS
adb shell pm grant  <包名> android.permission.POST_NOTIFICATIONS
```

另外 dumpsys 与手机页面会不一致：vivo 把渠道开关存在自家通知服务里，`dumpsys notification`
的 `mImportance` 不跟着变，所以别拿 dumpsys 判断 vivo 上到底关没关，以手机页面为准。

## 10. 广告包和快应用

这台没有挂起任何包，App 内开关够用。

- ⚠️ 快应用 `com.vivo.hybrid`：X300 Ultra（V2547A，Android 17）上系统拒绝挂起（[Issue #7](https://github.com/rddmwmddr/android-ad-cleaner/issues/7)）。根据 [PR #20](https://github.com/rddmwmddr/android-ad-cleaner/pull/20) 的真机证据，当前源码在能读到 `switch_quick_app_service` 时，通过系统服务开关关闭并验证，先备份原值；`quickapp on` 按本设备备份还原，找不到备份不会直接写成开启。这版实现在 V2547A 上已整段跑通：`quickapp off` 写入 `{"original": "1"}` 并把开关置 0，`quickapp on` 还原成 1 后自动删除记录文件。
- 🟢 智慧生活 `com.vivo.vhome` 属于智能家居功能，即使注册了 `hap://` 入口也不作为快应用广告组件处理。

原始实测（V2547A，2026-10-25）：`pm suspend`、`pm disable-user`、`pm uninstall --user 0`
三条路都要 root，全部抛 `SecurityException`，所以挂起这条路在 vivo 上不通：

```text
java.lang.SecurityException: Cannot suspend com.vivo.hybrid, no root permission
java.lang.SecurityException: Cannot disable com.vivo.hybrid no root permission
Failure [only root can delete system app for a particular user]
```

真正生效的是 secure 里的总开关 `switch_quick_app_service`（`quickapp off` 走的就是它）。
开关由 `1` 改成 `0` 之后逐入口用 `am start -W` 复核（`-W` 会直接回报实际启动的 Activity，
比事后看前台 Activity 可靠——上一版就是事后看，读到了残留记录，把第三行写错了）：

| 入口 | 结果 |
|---|---|
| `hap://` 链接（`DispatcherActivity`） | `Activity: com.vivo.hybrid/.main.activity.QuickAppSwitchOpenActivity` ——「快应用服务已关闭，是否重新开启服务？」，应用没起来 |
| 桌面「快应用中心」持久化快捷方式（`action.LAUNCH` + `EXTRA_APP=com.quickapp.center`） | 同上，落在同一个拦截页 |
| 直接启动 `com.vivo.hybrid/.main.DispatcherActivity` | `Status: ok` 但 Activity 随即自行结束，焦点退回桌面，没有进入任何快应用 |

- ⚠️ 关掉总开关后，桌面上那个「快应用中心」图标还在，点开会弹「快应用服务已关闭」，
  要点「确认开启」才会恢复。想去掉图标只能长按手动删。
- ⚠️ 如果靠快应用做签到、攒积分，别关这个开关：关掉后这些入口全部停在拦截页，签到会断。
- 还原：`quickapp on`。原值记在 `backups/<型号>-<时间>/quickapp-setting.json`。

---

## OriginOS 7（Android 17）的不同之处

实测机型 vivo X300 Ultra（V2547A，构建 `PD2547B_A_17.1.10.2.W10`），2026-10-25。
注意 `ro.vivo.os.name` 报的是 `Funtouch`，系统显示名要看 `ro.vivo.os.build.display.id`（OriginOS 7）。

| 项目 | OriginOS 6（V2547DA） | OriginOS 7（V2547A） |
|---|---|---|
| 广告与隐私 | 设置 → 安全 → 更多安全设置 → 广告与隐私 | 设置页搜「广告与隐私」，点结果直达 |
| 浏览器设置 | 我的 → 齿轮 | 首页右上「菜单」→ 设置（底部没有「我的」） |
| 浏览器隐私权限 | 个性化内容、第三方应用来源个性化推荐 | 多一项「个性化广告推荐」 |
| 天气设置 | 天气 → 设置 | 右上 `more_btn` → 设置（页内那个「更多」是展开按钮） |
| i 管家 | 设置 → 关于 → 个性化设置 | 同左，但首屏体检动画期间点「设置」会被吞，要重试 |
| 关开关的确认框 | — | 弹「温馨提示 → 取消 / 确认关闭」，按钮 `text` 是空的 |

几处实测到的 id 和 Activity（换机型或版本可能变）：

- 系统设置搜索框：`com.android.settings:id/vigour_search_edit`。首页那个「搜索设置项」本身是个 EditText，
  输入关键词后它自己也含这几个字，按文字查找会先命中它，点上去页面根本不跳、也不报错。
- 应用商店设置：`com.bbk.appstore/.ui.menu.AppstoreSettingsActivity`
- 浏览器菜单按钮：`com.vivo.browser:id/menu_btn`，设置页 `...setting.common.activity.SettingActivity`
- 负一屏设置面板：`com.vivo.hiboard/.settings.AppletSettingActivity`
- 阅图锁屏：`com.vivo.magazine/.ui.MagazineSettings`
- 天气：`com.vivo.weather:id/more_btn`，设置页 `com.vivo.weather/.WeatherSettings`

⚠️ 负一屏「热点资讯」页的 8 行开关，整行节点的标题全串成了页标题「热点资讯」；这一页还有 3 个单选钮
（悬浮 / 经典 / 卡片形态）也是 checkable，按「找 checkable 节点」的通用写法会把它当开关一起拨掉。
机型脚本 `recipes/vivo-V2547A/recipe.py` 里已按行还原标题、排除单选钮。

---

## vivo 的坑

| 现象 | 对策 |
|---|---|
| 负一屏、全局搜索、主题、i 管家的设置页拉不起来 | 只能从 App 或系统设置里点进去 |
| 列表行和开关各有一个状态 | 以开关本身为准 |

---

## V2324HA（iQOO，Android 16 / PD2324J_A_16.2.13.1.W10）差异

2026-10-27 实测，机型脚本 `recipes/vivo-V2324HA/`，七段全通、重跑约 2.5 分钟。和上面 X300 Ultra 的路径不一样的地方：

| 位置 | 本机实际路径 | 备注 |
|---|---|---|
| 应用商店·服务管理 | 商店 → 我的 → 设置 → **关于** → 下滑到「服务管理」 | 不在设置页第一层；页面是 `FunctionManagerActivity`，7 个营销开关 + 「管理页-我的服务」「空间清理」保留 |
| 应用商店·个性化推荐 | 设置 → 关于 → 「个性化推荐」 | `SettingUserRecommendActivity`；⚠️ 两个开关读屏里没有标题（只有「关闭，开关」），引擎会按保护类开关跳过，属安全策略，不绕过 |
| 应用商店·通知 | 设置 → 「应用商店提醒类型」 | 「消息通知设置」是标题行、点不动；提醒类型页 9 个开关 |
| 浏览器·设置入口 | 首页右上角 **菜单** → 设置 | 没有底部「我的」；`SettingActivity` |
| 浏览器·隐私 | 设置 → 隐私权限设置 | 是 `SettingActivity` 内的子页，4 个开关（含个性化广告推荐）|
| 全局搜索 | 设置 → 系统管理与升级 → 全局搜索 | 本版**没有「推荐热搜榜单」**入口，只剩首页展示内容、个性化内容 |
| 天气 | `am start -n com.vivo.weather/.WeatherSettings` | 天气首页只有「更多」，没有「设置」文字，齿轮找不到 |
| 快应用 | `com.vivo.hybrid` | 系统服务开关可关，`quickapp off` 备份原值后关闭并回读 |
## 补充：OriginOS 16 实测差异（V2361A，2026-10-26）
机型脚本：`recipes/vivo-V2361A/`。以下差异来自 V2361A 真机逐页实测。
| 位置 | V2547DA（OriginOS 6） | V2361A（OriginOS 16） |
| 系统设置页 | 普通列表 | 顶部有**悬浮搜索框**（y≈360-460），翻页后第一行会被盖住，直接点会误触搜索 |
| 开关控件 | 单个 Switch | 每行有**两个** Switch 节点：外层整行容器（clickable）、内层真开关。点外层会跳页不改状态 |
| 关闭确认 | 部分有 | 多数弹「确定 / 确认关闭」确认框，必须点掉 |
| 全局搜索 | 有独立的「推荐热搜榜单」入口 | 无该入口，热搜相关收在「首页展示内容 → 推荐卡片」 |
| 全局搜索·首页展示内容 | 搜索框推荐词、推荐卡片 | 搜索框推荐词、语音搜索、历史记录、推荐卡片 |
| 全局搜索·个性化内容 | 广告个性化 | 应用建议个性化、热门推荐个性化、搜索结果个性化、广告个性化 |
| 阅图锁屏 | 关「锁屏横滑进入阅图」带动总开关 | 反过来：关总开关「阅图锁屏」带动「锁屏横滑进入阅图」 |
| 应用商店 | 我的 → 设置 → 关于 | 一致；「个性化推荐」「服务管理」都在「关于」里 |
| 商店·个性化推荐 | 只有「个性化推荐」 | 多一项「个性化广告推荐」 |
| 天气 | 天气 → 设置 | 天气 → 更多 → 设置 |
| 浏览器 | 可正常进设置 | 本机为首次启动，停在「同意 / 不同意」协议页，未处理（规范不代用户同意协议） |
| 负一屏 | 左边缘右滑进入 | 左边缘右滑未进入，本机可能未开启或入口不同，待确认 |

| 关开关弹出的确认框，按钮点不到 | 按钮节点的 text 是空的，标题挂在子节点里，要按按钮子树里的文字找 |
| 点列表项左侧的文字没反应 | 点整行中间。商店「服务管理」、浏览器各设置项都这样 |
| 负一屏子页 back 多退一层，后面的项全找不到 | 用 Activity 确认还在 `AppletSettingActivity`，不在就重新滑进来 |
| 渠道页只有一个「允许通知」，关完整个 App 的通知都没了 | vivo 没有渠道级开关，按应用级处理；`notif-off / notif-on` |
| `dumpsys notification` 的渠道状态和手机页面不一致 | vivo 开关存在自家通知服务里，以手机页面为准 |
| `pm suspend` / `disable-user` / `uninstall --user 0` 全报 SecurityException | 要 root。快应用用 `quickapp off`（改 `switch_quick_app_service`） |
| 备份里 `disabled.txt` 第一行是 `Error: Shell does not have permission to access user 666` | `pm list packages` 不带 `--user 0` 会遍历分身/隐私空间；工具已改成带 `--user 0` |
