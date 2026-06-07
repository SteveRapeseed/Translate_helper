# 共享核心规范（Desktop / Android）

两端分开实现 UI 与输入，以下逻辑必须保持一致。

## 语言识别顺序

1. 韩文 Hangul → `ko`
2. 日文假名 → `ja`
3. 越南语声调字符 → `vi`
4. 纯 CJK 无拉丁 → `zh-CN`
5. 含拉丁字母 → 越南声调则 `vi`，否则 `en`
6. 其他 → `unknown`

## 跳过翻译

- 检测为 `zh-CN` → 跳过，提示「已是中文」
- 空文本 → 跳过

## System Prompt 结构

1. 角色：专业翻译引擎
2. 源语言说明（自动 / 指定 / 中文原文）
3. 目标：`zh-CN` 简体中文
4. 只输出译文，保留 URL/数字/专有名词

## 实现对照

| 能力 | Python | Kotlin |
| --- | --- | --- |
| 语言表 | `SUPPORTED_SOURCE_LANGUAGES` | `TranslationCore.supportedSourceLanguages` |
| 识别 | `detect_source_language()` | `detectSourceLanguage()` |
| Prompt | `build_system_prompt()` | `buildSystemPrompt()` |
| 结果 | `TranslationResult` | `TranslationResult` |

## API

两端均可直连 HuggingFace Router：

- `POST {HF_BASE_URL}/chat/completions`
- Header: `Authorization: Bearer {HF_TOKEN}`
- Model: `HF_LLM_MODEL`
