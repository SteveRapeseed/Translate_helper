# Android MVP - Translate Helper

手机端独立工程，与 [`../desktop/`](../desktop/) 分开开发。  
翻译规则对齐 [`../shared/`](../shared/) 中的 `translation_core.py` / `CORE_SPEC.md`。

## 功能

| 功能 | 说明 |
| --- | --- |
| 悬浮球 | 单击触发翻译，可拖动 |
| 无障碍读屏 | 读取当前界面文字（聊天、普通 App） |
| 区域 OCR 兜底 | 读屏失败时框选区域，**只截一次**再 OCR |
| 剪贴板翻译 | 可选：复制后自动翻译 |
| 翻译核心 | `TranslationCore.kt`（与桌面端 `translation_core.py` 对齐） |

## 开发环境

- Android Studio Hedgehog 或更高
- JDK 17
- Android SDK 34
- 真机 Android 8.0+（API 26）

## 配置 HuggingFace Token

在 `android/local.properties` 中添加（此文件不会提交到 Git）：

```properties
sdk.dir=/path/to/Android/Sdk
HF_TOKEN=hf_xxx
HF_BASE_URL=https://router.huggingface.co/v1
HF_LLM_MODEL=moonshotai/Kimi-K2-Instruct-0905
```

也可在 App 首页输入 Token（保存到 SharedPreferences）。

## 构建与安装

1. 用 Android Studio 打开 `android/` 目录
2. 等待 Gradle 同步
3. 连接手机并开启 USB 调试
4. Run `app`

## 首次使用步骤

1. 打开 App，填写 HF Token
2. **开启悬浮窗权限**
3. **开启无障碍「Translate Helper 读屏」**
4. 启动悬浮球时 **允许屏幕捕获**（仅用于 OCR 兜底，不会后台轮询）
5. （可选）打开「剪贴板自动翻译」

## 使用方式

- **单击悬浮球「译」**：先尝试无障碍读屏 → 失败则进入框选 OCR
- **复制外语**：若开启剪贴板监听，会自动翻译

## 架构

```text
FloatingBubbleService
    └─ TranslateCoordinator.onBubbleClicked()
           ├─ ScreenReaderAccessibilityService.extractVisibleText()
           ├─ RegionOcrActivity (一次性区域截图 + ML Kit OCR)
           └─ HuggingFaceTranslator → TranslationOverlayManager
```

## 已知限制（MVP）

- 游戏、视频、图片内文字：无障碍通常无效，需 OCR 框选
- OCR 默认使用 ML Kit Latin 识别器，英/越较好；日/韩优先依赖无障碍
- 后续可接入 `text-recognition-japanese/korean/chinese` 模块增强 OCR

## 与桌面端关系

- 桌面端：[`../desktop/`](../desktop/) + 剪贴板
- 手机端：[`android/`](.) + 悬浮球
- 共用规范：[`../shared/CORE_SPEC.md`](../shared/CORE_SPEC.md)
- Kotlin 实现：[`TranslationCore.kt`](app/src/main/java/com/translatehelper/TranslationCore.kt)
