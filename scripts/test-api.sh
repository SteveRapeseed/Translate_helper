#!/usr/bin/env bash
# 本地 API 连通测试（读取项目 .env，不输出 Token）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
[ -f .venv/bin/activate ] && source .venv/bin/activate

python3 - <<'PY'
import sys
from pathlib import Path

root = Path(".").resolve()
sys.path.insert(0, str(root / "shared"))

import importlib.util

spec = importlib.util.spec_from_file_location("app", root / "desktop" / "app.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

mod.load_env_file()
config = mod.AppConfig.from_env()
if not config.hf_token:
    print("失败: 未找到 HF_TOKEN（请检查 .env 或 ~/.config/translate-helper/.env）")
    raise SystemExit(1)

service = mod.TranslatorService(config)
result = service.translate("Hello, this is a connectivity test.")
text = (result.translated_text or "").strip()
if not text:
    print("失败: 翻译结果为空")
    raise SystemExit(1)

print("成功: API 联网正常")
print(f"路由: {mod.format_route_label(result.source_lang, result.target_lang)}")
print(f"译文: {text[:100]}")
PY
