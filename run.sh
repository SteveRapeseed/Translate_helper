#!/usr/bin/env bash
# 启动 Translate Helper
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [ ! -d ".venv" ]; then
  echo "尚未安装，正在执行 install.sh ..."
  bash "$ROOT/install.sh"
fi

# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
exec translate-helper
