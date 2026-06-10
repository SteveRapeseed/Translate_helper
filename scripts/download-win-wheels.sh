#!/usr/bin/env bash
# 在 WSL/Linux 下载 Windows (win_amd64) 离线 wheel，供 build-app.bat 使用
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/win-wheels"
mkdir -p "$OUT"

echo "==> 下载 Windows 离线 wheel 到 $OUT"

python3 -m pip download -d "$OUT" \
  --platform win_amd64 \
  --python-version 310 \
  --only-binary=:all: \
  pyinstaller pillow requests certifi charset-normalizer idna urllib3 \
  altgraph packaging pefile pywin32-ctypes pyinstaller-hooks-contrib \
  setuptools wheel

echo "完成: $(ls -1 "$OUT" | wc -l) 个文件"
