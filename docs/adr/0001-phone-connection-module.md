# 手机连接是一个 module，传输是它的 adapter

一台 adb 连接与「这台手机断了没有」由 `tool/adb_link.py` 的 `Connection` 一处拥有，调用方只拿结论：这次调用算不算断线、断了之后本段还要不要继续。之前同一件事散在 `run.adb_shell`、`chan_fast.ShellPhone`、`fast.Phone._resilient_shell`、`gui.adb_present` 四处，各写一遍「找 adb → 带 `-s` 执行 → 认 `client_gone` → `wait_for` → 抛 `lost`」，三份 adb 查找列表还互不相同。

## Considered Options

- **传输当 adapter 注入**（采纳）vs **模块只认 subprocess adb**。后者会让 `fast.Phone` 的每一次 `d.shell()` 换成额外一次 subprocess 调用，并丢掉 u2 特有的 `shell output invalid` 串——那是行为变化，不是搬家。所以 seam 上真实的 adapter 是三个：subprocess adb、u2 的 shell、测试假 transport（报告与初版方案写「两个」，把 u2 那一层漏了）。
- **`REPEAT` 由模块拥有**（采纳）vs 调用方各记一个 `lost` 布尔量。现在有三份：`fast.Phone.check_alive`、`_resilient_shell` 开头、`run.adb_shell` 的 `sys.exit`。
- **`adb_link.py` 就地长大**（采纳）vs 新建 `tool/phone.py` 或改名。改名会动 8 个测试文件的 import，换不来任何东西；类名叫 `Connection`，因为 `fast.Phone` 已经占了「Phone」。
- **版本闸门（adb ≥ 1.0.41，见 #25 #75）留在 gui**（采纳）vs 一并前移到 `run.py`。后者会让本机装旧 adb 的用户从「挂起 / 快应用莫名失败」变成提前报「找不到 adb」，是行为变更，不在这项里挣。

## Consequences

- `Connection` 比原方案多了两个开关，都是拿对拍逼出来的、不是预先设计：`lost_on_retry=False`（读屏库那条路径在「手机回来了、第二轮仍断」时抛原异常，不判成断开）、`sticky=False`（一个 `reader` 跑一整批，一次掉线不该让它后面永久只报 `REPEAT`）。默认值即另外两条入口的口径。
- `alive(wait)` 等超时就返回 `False`，不再追一次 `get-state`：这是客户端 `adb_present` 原来就有的口径，不是新决定。
- 插电常亮故意不收：`run.py` 是「备份原值 → 收尾还原」，`chan_fast.keep_awake()` 是「批开头打开 → finally 还原」，两种生命周期不是同一件事。收进来只是把浅逻辑伪装成深模块。
- 模块级函数（`adb_path` / `present` / `detached` / `wait_for` / `client_gone` / `lib_gone` / `lost` / `lost_from` / `keyguard_showing`）保留原名与语义：多处测试直接 patch 它们，改名要连测试一起动。
- 没有真机可验，验收是单测加改前改后对拍（argv / 重试次数 / 异常类型与消息 / 返回码）。真机上「确认断线后剩余段不再逐段重试」只能靠 #293 的报告者复测。
