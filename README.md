# Clipboard Translator

一个常驻桌面的剪贴板实时翻译小工具：

- 监听剪贴板文本变化
- 自动调用 HuggingFace 模型翻译
- 悬浮窗口始终置顶
- 可拖动位置、可手动触发翻译

## 快速开始

1. 进入项目目录并激活虚拟环境：

```bash
cd /home/lenovo/translation_helper
source .venv/bin/activate
```

2. 安装依赖：

```bash
python -m pip install -r requirements.txt
```

3. 配置 `.env`（至少设置 `HF_TOKEN`）：

```dotenv
HF_TOKEN="hf_xxx_your_token"
HF_BASE_URL="https://router.huggingface.co/v1"
HF_LLM_MODEL="moonshotai/Kimi-K2-Instruct-0905"
```

4. 运行：

```bash
python app.py
```

## 说明

- 程序运行时占用当前终端，这是正常现象（GUI 事件循环）。
- 关闭窗口的 `x` 按钮即可退出程序。
- 如果复制后没有立刻翻译，可以点窗口右上角 `Translate Now` 手动触发。
- 若系统缺少中文字体，程序会自动尝试加载/下载 CJK 字体并以图片方式渲染译文，避免方框字符。

## 常用配置（`.env`）

- `HF_TOKEN`：必填
- `HF_BASE_URL`：默认 `https://router.huggingface.co/v1`
- `HF_LLM_MODEL`：默认 `Qwen/Qwen2.5-7B-Instruct`
- `SOURCE_LANG`：默认 `auto`
- `TARGET_LANG`：默认 `zh-CN`
- `CLIPBOARD_POLL_MS`：默认 `500`
- `MIN_TEXT_LENGTH`：默认 `1`（支持中文单字触发翻译）
- `DEBOUNCE_MS`：默认 `350`
- `LOG_EVENTS`：默认 `true`
- `HF_USE_ENV_PROXY`：默认 `false`（通常建议保持 false）
- `HF_RETRY_COUNT`：默认 `3`（遇到 503/429/5xx 自动重试次数）
- `HF_RETRY_BACKOFF_SECONDS`：默认 `1.2`（重试退避基准秒数）
