"""Mac / Windows 共用的发布资源清单，不打包本地日志、备份或测试机型。"""
from pathlib import Path
import shutil
import sys


def bundle_data(root):
    root = Path(root).resolve()
    patterns = ("tool/*.py", "tool/*.dex", "recipes/*/recipe.py", "images/*.png",
                "gui/web/index.html", "gui/web/chime.wav", "gui/web/img/*.png")
    data = []
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            rel = path.relative_to(root)
            if any(part.startswith("zztest-") for part in rel.parts):
                continue
            if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents) if p != root):
                continue
            data.append((str(path), rel.parent.as_posix()))
    return data


def stage(root, destination):
    destination = Path(destination)
    for source, directory in bundle_data(root):
        target = destination / directory / Path(source).name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


if __name__ == "__main__":
    stage(Path(__file__).resolve().parents[1], sys.argv[1])
