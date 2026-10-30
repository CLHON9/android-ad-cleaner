# 华为 ALN-AL00 / HarmonyOS 4.2 通知路径，2026-10-30 逐项实测。
# 参数化版本只做了离线回归；不宣称这份新代码已在手机上整轮重跑。
BUILD = "ALN-AL00 4.2.0.223(C00E215R5P16)"
MODELS = ["ALN-AL00"]

import os
from pathlib import Path

import adb_link
from huawei_channels import execute, load_items

ONLY = globals().get("ONLY") or []
FAILED_STEPS = []


def step(name):
    def decorate(action):
        if ONLY and name not in ONLY:
            return action
        print("\n== " + name)
        p.miss = 0
        try:
            action()
        except adb_link.DeviceLost:
            raise
        except (OSError, ValueError, RuntimeError) as error:
            FAILED_STEPS.append(name)
            print("未完成：" + str(error))
        return action
    return decorate


@step("营销通知")
def _():
    selected = os.environ.get("AAC_HUAWEI_CHANNELS")
    if not selected:
        raise ValueError("先审核通知清单，再通过 AAC_HUAWEI_CHANNELS 指定；不使用默认或历史清单")
    result = execute(p.serial, load_items(Path(selected)), phone=p)
    if result.failed:
        raise RuntimeError("；".join(dict.fromkeys(result.failed)))
    print(f"调整 {result.changed} 项，原有总通知屏蔽 {result.blocked} 项")
