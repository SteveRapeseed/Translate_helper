# Desktop - 电脑端剪贴板翻译

复制外语文本即可自动翻译，无需其他操作。

## 交互说明（智能模式）

| 状态 | 行为 |
| --- | --- |
| 平时 | 屏幕角落只有一个小悬浮球「译」 |
| 复制外语 | 自动翻译并展开面板 |
| 15 秒后 | 面板自动缩回小球（可在 `.env` 调整 `PANEL_AUTO_HIDE_MS`） |
| 钉住 | 点击「钉住」后保持展开 |
| 关闭 | 点击「关闭」立即缩回小球 |
| 快捷键 | `Ctrl+Shift+T` 手动翻译剪贴板 |
| 双击小球 | 手动翻译剪贴板 |
| 右键小球 | 退出程序 |

WSL / Linux / Windows 下的剪贴板实时翻译小工具。

## 功能

- 剪贴板监听（英/日/韩/越 → 简体中文）
- 悬浮窗置顶、可拖动
- 图片字体渲染中文（避免方框字）

## 快速开始

### 方式 A：一键安装（推荐）

```bash
cd ~/translation_helper
bash install.sh
./run.sh
```

### 方式 B：手动

```bash
cd /home/lenovo/translation_helper
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
translate-helper
```

配置环境变量（按优先级）：

- `~/.config/translate-helper/.env`（安装后默认）
- `desktop/.env`
- 项目根目录 `.env`

```dotenv
HF_TOKEN="hf_xxx"
HF_BASE_URL="https://router.huggingface.co/v1"
HF_LLM_MODEL="moonshotai/Kimi-K2-Instruct-0905"
SUPPORTED_SOURCE_LANGS="en,ja,ko,vi"
TARGET_LANG="zh-CN"
```

> **WSL 用户**：请在 Windows Terminal 的 WSL 窗口运行，Cursor 内置终端启动的窗口可能不显示在桌面。

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
