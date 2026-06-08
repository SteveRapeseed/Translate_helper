# Translate Helper

英 / 日 / 韩 / 越 → 简体中文。

**当前阶段：优先完善电脑端（剪贴板复制翻译）**  
手机端工程已预留于 `android/`，后续再开发。

## 项目结构

```text
translation_helper/
├── shared/          # 共用翻译逻辑
├── desktop/         # 【当前主力】电脑端：复制 → 自动翻译
├── android/         # 【后续】手机端（悬浮球 / 读屏，暂未主攻）
└── .env             # 电脑端配置（也可用 desktop/.env）
```

## 电脑端（现在就用这个）

### 独立 App（推荐，解压即用）

```bash
# 构建（或直接使用 dist/TranslateHelper-0.1.0-linux.tar.gz）
bash build-app.sh

# 使用
tar -xzf dist/TranslateHelper-0.1.0-linux.tar.gz
cd TranslateHelper-0.1.0-linux
cp .env.example .env && nano .env   # 填 HF_TOKEN
./启动翻译助手.sh
```

Windows 独立版：在 Windows 上运行 `build-app.bat`，然后双击 `启动翻译助手.bat`。

完整说明见 [`下载使用.md`](下载使用.md)

### 源码安装

```bash
bash install.sh && ./run.sh
```

## 手机端（后续）

Android 工程在 [`android/`](android/)，等电脑端稳定后再继续。

详见 [`android/README.md`](android/README.md)

## 共用核心

| 能力 | Python (`shared/`) | Kotlin (`android/`) |
| --- | --- | --- |
| 语言识别 | `detect_source_language` | `detectSourceLanguage` |
| Prompt | `build_system_prompt` | `buildSystemPrompt` |
| 翻译 API | HuggingFace Router | HuggingFace Router |

修改翻译规则时，请同步 [`shared/translation_core.py`](shared/translation_core.py) 与 [`android/.../TranslationCore.kt`](android/app/src/main/java/com/translatehelper/TranslationCore.kt)，并参考 [`shared/CORE_SPEC.md`](shared/CORE_SPEC.md)。

## 支持语言

| 源语言 | 代码 | 目标 |
| --- | --- | --- |
| 英语 | en | zh-CN |
| 日语 | ja | zh-CN |
| 韩语 | ko | zh-CN |
| 越南语 | vi | zh-CN |
