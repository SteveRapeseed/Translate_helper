#!/usr/bin/env bash
# 一键安装 Translate Helper（WSL / Linux）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "==> Translate Helper 安装"
echo "    目录: $ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "错误: 未找到 python3，请先安装 Python 3.10+"
  exit 1
fi

PYTHON_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "    Python: $PYTHON_VERSION"

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "错误: 需要 Python 3.10 或更高版本"
  exit 1
fi

if ! python3 - <<'PY' 2>/dev/null
import tkinter
PY
then
  echo "警告: 当前 Python 没有 tkinter，GUI 可能无法启动。"
  echo "       Ubuntu/Debian 可执行: sudo apt install python3-tk"
fi

if [ ! -d ".venv" ]; then
  echo "==> 创建虚拟环境 .venv"
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> 安装依赖与 translate-helper 命令"
python -m pip install -U pip wheel
python -m pip install -e .

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/translate-helper"
if ! mkdir -p "$CONFIG_DIR" 2>/dev/null; then
  CONFIG_DIR="$ROOT/.config/translate-helper"
  mkdir -p "$CONFIG_DIR"
  echo "==> 使用项目内配置目录: $CONFIG_DIR"
fi

if [ ! -f "$CONFIG_DIR/.env" ]; then
  if [ -f "$ROOT/.env" ]; then
    cp "$ROOT/.env" "$CONFIG_DIR/.env"
    echo "==> 已从项目 .env 复制配置（Token 仅保存在本地，不会打包发布）"
  else
    cp "$ROOT/desktop/.env.example" "$CONFIG_DIR/.env"
    echo "==> 已创建配置文件: $CONFIG_DIR/.env"
    echo "    请编辑该文件，填写 HF_TOKEN"
  fi
elif [ ! -f "$ROOT/.env" ]; then
  echo "==> 使用已有配置: $CONFIG_DIR/.env"
fi

chmod +x "$ROOT/run.sh"

echo ""
echo "安装完成！"
echo ""
echo "  启动方式 1（推荐）:"
echo "    $ROOT/run.sh"
echo ""
echo "  启动方式 2:"
echo "    cd $ROOT && source .venv/bin/activate && translate-helper"
echo ""
echo "  配置编辑:"
echo "    nano $CONFIG_DIR/.env"
echo ""
echo "  请在 Windows Terminal 的 WSL 窗口中运行，以确保悬浮窗显示在桌面。"
