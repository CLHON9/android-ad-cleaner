# 发版后复测清单

Issues labelled `waiting-for-verify` have a fix on `main` that the reporter has not confirmed on hardware yet. Nothing closes them except the reporter's own reply after installing the release that contains the fix. This file is the queue of what each release owes.

## 每次发版后照做

1. 取出当前队列：

   ```bash
   gh issue list --label waiting-for-verify --state open
   ```

2. 逐条确认修复是否进了本次构建。版本号对不上就跳过 —— 让报告者跑旧版去验新代码，只会再收一份重复上报。

3. 在每条 issue 上留一条复测请求，`@` 报告者，写清装了哪个版本、要观察哪一句输出。模板见下。

4. 报告者确认后关闭 issue 并摘掉 `waiting-for-verify`；报告失败就摘标、改回 `needs-triage`，把日志当新证据重新归类。

## 复测请求模板

```text
0.2.x 已经发布，包含这次的修复（PR #NNN）。如果你还方便，请装新版再跑一次，把下面这一段的输出贴上来：

- 期望看到：<具体那一行的正确形态>
- 之前看到：<原来那句错误输出>

不方便复测也没关系，这条先留着，等有同机型的反馈再一起确认。
```

要点：说清装哪个版本、看哪一行、正确长什么样。别问「好了吗」—— 报告者没法据此判断，只会再发一张截图。

## 当前队列

| Issue | 报告者 | 机型 / 系统 | 修复 | 要观察的输出 |
| ----- | ------ | ----------- | ---- | ------------ |
| #286 | @xicong | OPPO Find X8s / PKT110 / ColorOS 17.0.0.102 | #296 #297 | 母 issue：整轮四段走完，游戏中心与广告跟踪不再报入口缺失，adb 断连不再误报「本机没有安装」。确认后与 #292 / #293 一并关闭 |
| #292 | @xicong | OPPO Find X8s / PKT110 / ColorOS 17.0.0.102 | #297 | 游戏中心段不再以「未找到入口『设置』」结束；广告跟踪段不再打印「✗ 没找到『隐私』」 |
| #293 | @xicong | 同上 | #296 | 复用外部 adb server 后再关掉对方程序，报「手机和电脑的 adb 连接断开了」，后续段跳过；不再出现「本机没有安装 com.heytap.yoli」 |
| #287 | @zhxhstc92 | 华为 mate50 / 鸿蒙 4.0 | #299 | 页面出现两个同名渠道时，点到的是带开关的那一行 |

三条修复都在 0.2.7 发布（2026-10-29T02:56Z）之后合入 `main`，所以 0.2.7 不包含它们。0.2.8（2026-10-30T05:29Z）包含全部四条；同日已在 #286、#287 上 @ 报告者发复测请求，#292、#293 留言指向 #286。

## 为什么不用 `ready-for-agent` 顶着

一个已修完、只等真机确认的 issue，长着和待实现 issue 一模一样的外观：代码不在发布版里，报告者还在遇到问题。`ready-for-agent` 会让下一个接手的智能体（或人）从头再实现一遍；`needs-info` 会让人以为缺的是诊断数据。两种误判在 2026-10-29 都发生过一次。
