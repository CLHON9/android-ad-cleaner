"""upload_baidu.sh 的辅助：读写 index.html 里的发布信息（REL）。
  baidu_rows.py <版本> <安装说明输出路径>   打印「id<TAB>网盘文件夹<TAB>文件名」，并按下载页文字写安装说明
  baidu_rows.py --write                     从标准输入读「id<TAB>链接<TAB>提取码」（id=all 是全部版本的总链接），写回 index.html
"""
import re
import sys

PAGE = "index.html"
ITEM = re.compile(r'\{ id: "([\w-]+)", folder: "([^"]+)", baidu: \{[^}]*\}, title: "([^"]+)", sub: "([^"]+)", '
                  r'file: "([^"]+)"[^\n]*\n\s*note: "([^"]+)"')


def rows(ver, guide):
    html = open(PAGE, encoding="utf-8").read()
    items = [i for i in ITEM.findall(html) if ver in i[4]]
    lines = [f"安卓去广告 v{ver}", "", "选哪个文件："]
    lines += [f"· {title}（{sub}）：{folder}/{file}。{note}" for _, folder, title, sub, file, note in items]
    lines += ["", "不知道 Mac 是哪种芯片：左上角苹果图标 → 关于本机，「芯片」写 Apple M 开头的选 Apple 芯片。",
              "SHA256SUMS.txt 是 4 个文件的 SHA256 校验值。",
              "用法、常见问题、反馈：https://github.com/rddmwmddr/android-ad-cleaner"]
    with open(guide, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    for item in items:
        print("\t".join((item[0], item[1], item[4])))


def write(stream):
    html = open(PAGE, encoding="utf-8").read()
    for line in stream:
        key, url, code = line.rstrip("\n").split("\t")
        value = 'baidu: { url: "%s", code: "%s" }' % (url, code)
        if key == "all":
            html, n = re.subn(r"(\n  )baidu: \{[^}]*\}(,)", lambda m: m.group(1) + value + m.group(2), html, count=1)
        else:
            html, n = re.subn(r'(\{ id: "%s", folder: "[^"]+", )baidu: \{[^}]*\}' % re.escape(key),
                              lambda m: m.group(1) + value, html)
        if n != 1:
            sys.exit(f"index.html 里没找到 {key}")
        print(f"{key:10} {url}  提取码 {code}")
    with open(PAGE, "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    if sys.argv[1:] == ["--write"]:
        write(sys.stdin)
    else:
        rows(sys.argv[1], sys.argv[2])
