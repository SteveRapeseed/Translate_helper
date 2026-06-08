"""应用入口：加载 desktop/app.py 并启动 GUI。"""

from __future__ import annotations

import importlib.util
import sys

from translate_helper.runtime_paths import desktop_app_path, shared_dir


def main() -> int:
    root = shared_dir().parent
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    shared = shared_dir()
    shared_str = str(shared)
    if shared_str not in sys.path:
        sys.path.insert(0, shared_str)

    app_path = desktop_app_path()
    if not app_path.exists():
        print(f"[translate-helper] 找不到应用: {app_path}", flush=True)
        return 1

    spec = importlib.util.spec_from_file_location("translate_helper_desktop_app", app_path)
    if spec is None or spec.loader is None:
        print(f"[translate-helper] 找不到应用: {app_path}", flush=True)
        return 1

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return int(module.main())


if __name__ == "__main__":
    raise SystemExit(main())
