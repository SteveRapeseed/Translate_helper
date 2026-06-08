"""运行时路径：兼容源码、pip 安装与 PyInstaller 打包。"""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent


def install_root() -> Path:
    """可执行文件所在目录（配置 .env 放这里）。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return bundle_root()


def desktop_dir() -> Path:
    if is_frozen():
        return bundle_root() / "desktop"
    return bundle_root() / "desktop"


def shared_dir() -> Path:
    return bundle_root() / "shared"


def desktop_app_path() -> Path:
    return desktop_dir() / "app.py"
