#!/usr/bin/env bash
# 打包可分发压缩包（不含 .venv / .env / 构建缓存）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])" 2>/dev/null || echo "0.1.0")"
NAME="translate-helper-${VERSION}"
DIST="$ROOT/dist"
STAGE="$DIST/$NAME"

rm -rf "$STAGE"
mkdir -p "$STAGE"

copy() {
  local src="$1"
  local dst="$2"
  mkdir -p "$(dirname "$dst")"
  cp -a "$src" "$dst"
}

copy README.md "$STAGE/README.md"
copy 下载使用.md "$STAGE/下载使用.md"
copy pyproject.toml "$STAGE/pyproject.toml"
copy install.sh "$STAGE/install.sh"
copy run.sh "$STAGE/run.sh"
copy install.bat "$STAGE/install.bat"
copy run.bat "$STAGE/run.bat"
copy translate_helper "$STAGE/translate_helper"
copy shared "$STAGE/shared"
copy desktop "$STAGE/desktop"

chmod +x "$STAGE/install.sh" "$STAGE/run.sh"

mkdir -p "$DIST"
ARCHIVE="$DIST/${NAME}.tar.gz"
tar -czf "$ARCHIVE" -C "$DIST" "$NAME"

echo ""
echo "已生成: $ARCHIVE"
echo "大小: $(du -h "$ARCHIVE" | cut -f1)"
echo ""
echo "使用方式:"
echo "  tar -xzf ${NAME}.tar.gz"
echo "  cd $NAME"
echo "  bash install.sh"
echo "  ./run.sh"
