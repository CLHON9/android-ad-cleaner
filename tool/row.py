#!/usr/bin/env python3
"""「开关所属的那一行」的唯一定义。

行的两副面孔，取决于布局：
  结构（line / own）—— 从起点往上，到可点 / 可勾选的控件，或到滚动列表的直接子项为止；
      容器里不止一个开关时，收窄到最内层含开关的那个（卡片里排着几个渠道）。
  几何（title_of）—— 平铺列表里标题和开关是兄弟节点，结构给不出容器，标题只能按竖直距离挑：
      容器矮取最上方的文字，容器高取离开关最近的文字。

两个投影共享 bounds() 与 switches_in()，但不互相调用：标题规则一旦去问结构行，
「开关在卡片内小行、卡片本身可点」这类布局会改判，那是另一类行为变化。

术语：行 = 开关所属的那一条；卡片 = 一个容器里排着好几行的控件；内联布局 = 渠道行自带开关。
"""
import re

BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
LISTS = re.compile(r"ListView|RecyclerView|ScrollView", re.I)
SWITCH_ROW_DEPTH = 6
PATH_DEPTH = 8
STATE_WORDS = ("开", "关", "已开启", "已关闭", "开启", "关闭", "ON", "OFF",
               "开启，开关", "关闭，开关", "已开启，开关", "已关闭，开关", "开启，按钮", "关闭，按钮")


def bounds(node):
    m = BOUNDS.match(node.get("bounds", ""))
    return tuple(map(int, m.groups())) if m else (0, 0, 0, 0)


def line(node, parents, max_depth=None):
    """文字所在的行。ListView 的行常常不可点（点击由列表处理），到列表的直接子项为止。
    max_depth 是往上检查的节点数上限（含起点）；None 表示一直找到根节点。"""
    seen = 0
    while node is not None and (max_depth is None or seen < max_depth):
        if node.get("clickable") == "true" or node.get("checkable") == "true":
            return node
        parent = parents.get(node)
        if parent is not None and (parent.get("scrollable") == "true"
                                   or LISTS.search(parent.get("class") or "")):
            return node
        node = parent
        seen += 1
    return None


def switches_in(node, on_screen):
    """node 子树里的开关。RadioButton 是互斥选项、不是开关，拨它等于替用户改选另一项；
    node 自己不算——问的是「一行里有几个开关」。"""
    return [x for x in node.iter()
            if x is not node and x.get("checkable") == "true"
            and "RadioButton" not in (x.get("class") or "") and on_screen(x)]


def own(node, parents, on_screen, max_depth=None):
    """node 所在的行和行里的开关。行里不止一个开关时（几个渠道排在同一张卡片里），
    从 node 往上找第一个含开关的控件；它只含一个开关才算这一行。
    行里仍然不止一个开关时照样返回，由调用方决定是放弃还是按别的方式挑。"""
    container = line(node, parents, max_depth)
    if container is None:
        return None, []
    boxes = switches_in(container, on_screen) or (
        [container] if container.get("checkable") == "true" else [])
    inner = node
    while len(boxes) > 1 and inner is not None and inner is not container:
        found = switches_in(inner, on_screen)
        if found:
            return inner, found
        inner = parents.get(inner)
    return container, boxes


def title_of(switch, parents, on_screen, screen_h, max_depth=SWITCH_ROW_DEPTH):
    """开关所在那一行的标题：往上找到第一个带文字的祖先。容器矮（就是一行）时分不清标题和说明，
    取最上面那段；容器高（是一整张列表）时取竖直方向离开关最近的文字。
    行里没有别的文字时，退回开关自己的无障碍标签。"""
    _, t, _, b = bounds(switch)
    cy = (t + b) // 2
    label = (switch.get("text") or switch.get("content-desc") or "").strip().split("\n", 1)[0]
    label = label if label not in STATE_WORDS else ""
    title, node = "", switch
    for _ in range(max_depth):
        # 有自己的可访问标签时，不从包含多个开关的公共列表借用相邻行标题。
        # 这里数的是控件类名里的 Switch（含各家 HwSwitch），问的是「这是不是一张公共列表」；
        # 与 switches_in 判「这是不是一个能拨的开关」是两个问题，不要合并。
        if label and node is not switch and sum(
                1 for x in node.iter("node") if "Switch" in (x.get("class") or "")
                and "Switcher" not in (x.get("class") or "") and on_screen(x)) > 1:
            title = label
            break
        cand = []
        for x in node.iter("node"):
            tx = (x.get("text") or x.get("content-desc") or "").strip().split("\n", 1)[0]
            if x is switch or not tx or tx in STATE_WORDS:
                continue
            xl, xt, xr, xb = bounds(x)
            if xb <= xt or not on_screen(x):
                continue
            cand.append((xt, xl, xb, tx))
        if cand:
            pl, pt, pr, pb = bounds(node)
            if pb - pt <= max(screen_h * 0.18, (b - t) * 3):
                title = min(cand)[3]
            else:
                near = sorted((0 if xt <= cy <= xb else min(abs(xt - cy), abs(xb - cy)), xt, tx)
                              for xt, xl, xb, tx in cand)
                if near[0][0] <= max(60, b - t):
                    title = near[0][2]
            break
        node = parents.get(node)
        if node is None:
            break
    return title or label


def path(node, parents, depth=PATH_DEPTH):
    """从 node 往上的控件链数据：(类名, 'cs' 标志, 子树里的开关数)。到滚动容器为止，不含页面文字。"""
    out = []
    while node is not None and len(out) < depth:
        flags = ("c" if node.get("clickable") == "true" else "") + (
            "s" if node.get("scrollable") == "true" else "")
        out.append((node.get("class") or "node", flags,
                    sum(x.get("checkable") == "true" for x in node.iter())))
        if node.get("scrollable") == "true" or LISTS.search(node.get("class") or ""):
            break
        node = parents.get(node)
    return out
