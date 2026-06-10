#!/usr/bin/env bash
# 从 WSL 触发 Windows 原生 exe 打包（解决 WSL 内 pip SSL/代理问题）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WIN_BUILD="${WIN_BUILD_DIR:-/mnt/c/Users/lenovo/translate_helper_build}"

echo "==> 同步源码到 Windows: $WIN_BUILD"
mkdir -p "$WIN_BUILD"
rsync -a --delete \
  --exclude '.venv/' \
  --exclude '.venv-win/' \
  --exclude 'dist/' \
  --exclude 'build/' \
  --exclude '.env' \
  --exclude '__pycache__/' \
  --exclude 'win-wheels/' \
  "$ROOT/" "$WIN_BUILD/"

if [ ! -d "$ROOT/win-wheels" ] || [ -z "$(ls -A "$ROOT/win-wheels" 2>/dev/null)" ]; then
  echo "==> 首次运行：下载 Windows 离线 wheel"
  bash "$ROOT/scripts/download-win-wheels.sh"
fi
rsync -a "$ROOT/win-wheels/" "$WIN_BUILD/win-wheels/"

echo "==> 在 Windows 上执行 PyInstaller 打包"
cmd.exe /c "cd /d C:\\Users\\lenovo\\translate_helper_build && set BUILD_NO_PAUSE=1 && build-app.bat"

echo "==> 复制产物到 $ROOT/dist/"
mkdir -p "$ROOT/dist"
rsync -a "$WIN_BUILD/dist/TranslateHelper-0.1.0-win64/" "$ROOT/dist/TranslateHelper-0.1.0-win64/" 2>/dev/null || true

if [ -d "$WIN_BUILD/dist/TranslateHelper-0.1.0-win64" ]; then
  python3 - <<'PY'
import pathlib, zipfile
root = pathlib.Path("/home/lenovo/translation_helper/dist/TranslateHelper-0.1.0-win64")
out = pathlib.Path("/home/lenovo/translation_helper/dist/TranslateHelper-0.1.0-win64.zip")
if root.exists():
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in root.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(root.parent))
    print(f"ZIP: {out} ({out.stat().st_size // 1024 // 1024} MB)")
PY
fi

echo ""
echo "完成。Windows 版："
echo "  $WIN_BUILD/dist/TranslateHelper-0.1.0-win64/启动翻译助手.bat"
echo "  $ROOT/dist/TranslateHelper-0.1.0-win64.zip"
