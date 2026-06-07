# Desktop - 电脑端剪贴板翻译

**当前主力版本**：复制外语 → 悬浮窗自动显示中文译文。

WSL / Linux / Windows 下的剪贴板实时翻译小工具。

## 功能

- 剪贴板监听（英/日/韩/越 → 简体中文）
- 悬浮窗置顶、可拖动
- 图片字体渲染中文（避免方框字）

## 快速开始

```bash
cd /home/lenovo/translation_helper
python3 -m venv .venv
source .venv/bin/activate
pip install -r desktop/requirements.txt
```

配置环境变量（任选其一）：

- `desktop/.env`
- 项目根目录 `.env`

```dotenv
HF_TOKEN="hf_xxx"
HF_BASE_URL="https://router.huggingface.co/v1"
HF_LLM_MODEL="moonshotai/Kimi-K2-Instruct-0905"
SUPPORTED_SOURCE_LANGS="en,ja,ko,vi"
TARGET_LANG="zh-CN"
```

运行：

```bash
python desktop/app.py
```

## 目录

```text
desktop/
  app.py              # Tkinter UI + 剪贴板
  requirements.txt
  .font-cache/        # 运行时字体缓存（自动生成）
```

共享逻辑在 [`../shared/`](../shared/)，不在此目录重复实现。

## 与手机端区别

| 项目 | 电脑端 | 手机端 |
| --- | --- | --- |
| 输入 | 剪贴板 | 无障碍读屏 / OCR / 剪贴板 |
| UI | Tkinter 悬浮窗 | Android 悬浮球 |
| 工程 | `desktop/` | `android/` |
