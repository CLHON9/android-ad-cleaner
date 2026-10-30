# CLAUDE.md

本仓库的操作规范写在 [AGENTS.md](AGENTS.md)。开工前读完它。

本文件只写会改变 agent 行为的指令。逐次处理记录、上报归类与每次发版的验证见 [CHANGELOG.md](CHANGELOG.md)，不在这里复述。

## 开发

- 回归：`python -m unittest discover -s tests`；本机用仓库根的 `.venv/bin/python`（系统 python 缺 adbutils，会报一串 ModuleNotFoundError）。只装 `requirements.txt` 就够，不需要 pywebview / pillow。并行会话在各自的 worktree 里干活时，那个目录没有 `.venv`，用主副本 `.venv/bin/python` 的绝对路径；Read/Edit 也一律用该 worktree 的绝对路径。
- CI：`.github/workflows/test.yml` 在 PR 和 main 推送时自动跑同一套；`build-windows.yml` 只在 `v*` 标签或手动触发时打包，不守 PR。
- 静态检查：`uvx ruff@0.17.3 check --select F,E9 tool tests gui`，本地与 CI 同一个版本（CI 就钉 0.17.3，`.venv` 里没有 ruff）。不查 `recipes/`——机型脚本靠注入作用域执行，静态分析看到的全是未定义名；也不开格式与行长规则。
- CHANGELOG 的新行加在 `## 未发布` 一节；rebase 到已经发过版的 main 之后，确认它没有落进已发版的小节。
- 审查标准：见 [CODING_STANDARDS.md](CODING_STANDARDS.md)，只放判断项；机械规则交给 CI。
- 社区问题的归类与真机缺口见 [docs/09](docs/09-社区问题处理.md)：那里只记 GitHub 上看不到的判据与缺口，逐条回复与 issue 编号留在 issue 里。
- 找「开关所属的行」先看 [tool/row.py](tool/row.py)：`line` 结构定界、`own` 多开关容器收窄、`title_of` 平铺列表按竖直距离分带；`fast.py` 与 `chan_fast.py` 消费它，不要另写一份。
- 找「等页面认得出」先看 [tool/wait.py](tool/wait.py)：`settle` / `setting` / `wait_page` / `off` 都消费 `until()`，不要另写轮询循环。
- 造不连手机的 `Phone` 用 [tests/fixtures.py](tests/fixtures.py) 的 `phone_stub()`（`fake_phone()` 就是它加一条时间轴），装配只此一处。纯重构要给对拍证据时，同一文件还有 `all_pages()` 取 `tests/` 里的页面样本、`Clock` 假时钟、`Timeline` + `Device` 按时间轴换页。
- adb 固定 platform-tools 37.0.1（`gui/app.py` 的 `ADB_PINNED`）；升级时改那张表，校验值按 Google `repository2-3.xml` 的 SHA-1 核对。

## 错误日志上报

- 用户说明见 [docs/12](docs/12-错误日志上报.md)。服务器、数据库、部署与运维信息只记在本机 `CLAUDE.local.md` 和 `.private/`，不进仓库。

## 发版

- 新版本提示读官网的 `android-ad-cleaner-latest.json`，发版后要更新它（步骤记在本机 `CLAUDE.local.md`）。
- 官网另有一份放在机主的服务器上，发版后同步，方法记在本机 `CLAUDE.local.md`。
- 网盘：`gui/upload_baidu.sh [版本]` 从公开的 GitHub Release 下载安装包并核对 SHA256，经本机已登录的 BaiduPCS-Go 上传，生成分享链接写进 index.html 后提交推送。网盘账号凭证不进仓库和对话。
- 发完版按 [docs/agents/release-followup.md](docs/agents/release-followup.md) 把 `waiting-for-verify` 的 issue 逐条发给报告者复测。新版不送到报告者手上，这些 issue 永远关不掉。

## Agent skills

### Issue tracker

GitHub Issues（`gh` CLI）。见 `docs/agents/issue-tracker.md`。

### Triage labels

默认五个角色标签，标签名即角色名，另加本仓库的 `waiting-for-verify`（已修、等真机复测）。见 `docs/agents/triage-labels.md`。

### Release followup

发版后要催哪些复测、报告者确认前不关闭哪些 issue，见 `docs/agents/release-followup.md`。每次发版都要过一遍这张清单。

### Domain docs

single-context：根目录 `CONTEXT.md` + `docs/adr/`。见 `docs/agents/domain.md`。`CONTEXT.md` 只放术语表（脚本 / 执行 / 等待 / 通知 / issue 状态五组定义）；模块边界的决定写进 `docs/adr/`（现有 `0001` 手机连接 module），架构描述仍不写，等主流程整体重构。
