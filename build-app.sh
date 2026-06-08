#!/usr/bin/env bash
# 打包完整可下载 App（Linux / WSL，解压即用，无需 pip install）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])" 2>/dev/null || echo "0.1.0")"
APP_NAME="TranslateHelper-${VERSION}-linux"
OUT="$ROOT/dist/$APP_NAME"

echo "==> 构建独立 App: $APP_NAME"

if ! python3 -c 'import tkinter' 2>/dev/null; then
  echo "错误: 需要 python3-tk，请执行: sudo apt install python3-tk"
  exit 1
fi

# shellcheck disable=SC1091
[ -f .venv/bin/activate ] && source .venv/bin/activate

python -m pip install -q pyinstaller
python -m PyInstaller --noconfirm --clean translate-helper.spec

rm -rf "$OUT"
mkdir -p "$OUT"

# PyInstaller 输出目录
cp -a "$ROOT/dist/TranslateHelper/"* "$OUT/"

# 配置与启动器（不打包含真实 Token 的 .env，仅 example）
cp "$ROOT/desktop/.env.example" "$OUT/.env.example"

cat > "$OUT/启动翻译助手.sh" <<'EOF'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp .env.example .env
  echo "首次运行：请编辑 $DIR/.env 填写 HF_TOKEN 后重新启动"
  echo "若已有项目 .env，可复制到本目录: cp ~/translation_helper/.env $DIR/.env"
  exit 1
fi
exec "$DIR/TranslateHelper"
EOF
chmod +x "$OUT/启动翻译助手.sh" "$OUT/TranslateHelper"

cat > "$OUT/使用说明.txt" <<'EOF'
Translate Helper 翻译助手（独立版）
================================

【启动】
  WSL / Linux：双击或在终端运行
    ./启动翻译助手.sh

【配置】（首次）
  编辑同目录 .env，填写 HF_TOKEN
  Token 获取: https://huggingface.co/settings/tokens

【使用】
  复制英/日/韩/越文本 → 自动翻译
  双击「译」小球 → 手动翻译
  右键小球 → 退出

【注意】
  请在 Windows Terminal 的 WSL 窗口运行，悬浮窗才会显示在桌面。
  需要联网。
EOF

ARCHIVE="$ROOT/dist/${APP_NAME}.tar.gz"
tar -czf "$ARCHIVE" -C "$ROOT/dist" "$APP_NAME"

echo ""
echo "完成: $ARCHIVE"
echo "大小: $(du -h "$ARCHIVE" | cut -f1)"
echo ""
echo "使用:"
echo "  tar -xzf ${APP_NAME}.tar.gz"
echo "  cd $APP_NAME"
echo "  ./启动翻译助手.sh"
