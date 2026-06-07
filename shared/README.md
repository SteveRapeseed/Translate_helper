# Shared Translation Core

桌面端与手机端 **分开开发**，但共用同一套翻译规则。

## 内容

| 文件 | 说明 |
| --- | --- |
| `translation_core.py` | Python 参考实现（桌面端直接 import） |
| `CORE_SPEC.md` | 行为约定，供 Android Kotlin 对齐 |

## 支持语言

- 源语言：`en` / `ja` / `ko` / `vi`
- 目标语言：`zh-CN`

## 各端如何使用

| 端 | 目录 | 核心引用 |
| --- | --- | --- |
| 电脑端 | [`../desktop/`](../desktop/) | `from translation_core import ...` |
| 手机端 | [`../android/`](../android/) | `TranslationCore.kt`（Kotlin 移植） |

## 修改规则

1. **先改** `translation_core.py`（或同步更新 Kotlin）
2. 保持语言识别、Prompt、跳过逻辑一致
3. 各端 UI / 输入方式独立，不混入 `shared/`
