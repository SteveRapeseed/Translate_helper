package com.translatehelper

data class LanguageProfile(
    val code: String,
    val englishName: String,
    val chineseName: String,
)

data class TranslationResult(
    val sourceText: String,
    val translatedText: String,
    val sourceLang: String,
    val targetLang: String,
    val status: String,
    val fromCache: Boolean = false,
    val skipped: Boolean = false,
)

object TranslationCore {
    val supportedSourceLanguages = linkedMapOf(
        "en" to LanguageProfile("en", "English", "英语"),
        "ja" to LanguageProfile("ja", "Japanese", "日语"),
        "ko" to LanguageProfile("ko", "Korean", "韩语"),
        "vi" to LanguageProfile("vi", "Vietnamese", "越南语"),
    )

    val targetLanguage = LanguageProfile("zh-CN", "Chinese", "简体中文")
    val defaultSourceLangs = listOf("en", "ja", "ko", "vi")

    private val jaKanaRegex = Regex("[\\u3040-\\u309f\\u30a0-\\u30ff]")
    private val koHangulRegex = Regex("[\\uac00-\\ud7af]")
    private val viDiacriticRegex = Regex(
        "[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]",
        RegexOption.IGNORE_CASE,
    )
    private val cjkRegex = Regex("[\\u4e00-\\u9fff]")
    private val latinRegex = Regex("[A-Za-z]")

    fun parseSourceLangs(raw: String?): List<String> {
        if (raw.isNullOrBlank()) {
            return defaultSourceLangs
        }
        val codes = mutableListOf<String>()
        raw.split(",").forEach { part ->
            val code = part.trim().lowercase()
            if (code.isNotEmpty() && supportedSourceLanguages.containsKey(code) && !codes.contains(code)) {
                codes.add(code)
            }
        }
        return if (codes.isEmpty()) defaultSourceLangs else codes
    }

    fun languageLabel(code: String, chinese: Boolean = true): String {
        if (code == targetLanguage.code) {
            return if (chinese) targetLanguage.chineseName else targetLanguage.englishName
        }
        val profile = supportedSourceLanguages[code] ?: return code
        return if (chinese) profile.chineseName else profile.englishName
    }

    fun formatRouteLabel(sourceLang: String, targetLang: String = targetLanguage.code): String {
        return "${languageLabel(sourceLang)} → ${languageLabel(targetLang)}"
    }

    fun detectSourceLanguage(text: String, allowed: List<String> = defaultSourceLangs): String {
        val sample = text.trim()
        if (sample.isEmpty()) {
            return "unknown"
        }
        if (koHangulRegex.containsMatchIn(sample) && "ko" in allowed) {
            return "ko"
        }
        if (jaKanaRegex.containsMatchIn(sample) && "ja" in allowed) {
            return "ja"
        }
        if (viDiacriticRegex.containsMatchIn(sample) && "vi" in allowed) {
            return "vi"
        }

        val cjkCount = cjkRegex.findAll(sample).count()
        val latinCount = latinRegex.findAll(sample).count()
        if (cjkCount > 0 && latinCount == 0 &&
            !jaKanaRegex.containsMatchIn(sample) &&
            !koHangulRegex.containsMatchIn(sample)
        ) {
            return targetLanguage.code
        }
        if (latinCount > 0) {
            if ("vi" in allowed && viDiacriticRegex.containsMatchIn(sample)) {
                return "vi"
            }
            if ("en" in allowed) {
                return "en"
            }
        }
        return "unknown"
    }

    fun shouldSkipTranslation(
        text: String,
        detectedLang: String,
        targetLang: String = targetLanguage.code,
    ): Pair<Boolean, String> {
        if (detectedLang == targetLang) {
            return true to "已是中文，无需翻译"
        }
        if (text.isBlank()) {
            return true to "文本为空"
        }
        return false to ""
    }

    fun buildSystemPrompt(
        sourceLang: String,
        targetLang: String = targetLanguage.code,
        allowedSources: List<String> = defaultSourceLangs,
    ): String {
        val allowedNames = allowedSources.joinToString("、") { languageLabel(it) }
        val targetName = languageLabel(targetLang)
        val sourceHint = when (sourceLang) {
            "unknown" -> "自动识别源语言，优先支持：$allowedNames。若文本已是中文则原样返回。"
            targetLanguage.code -> "源语言是中文，直接返回原文，不要翻译。"
            else -> "源语言是${languageLabel(sourceLang)}（$sourceLang）。"
        }
        return """
            你是专业翻译引擎。
            $sourceHint
            将用户文本翻译为$targetName（$targetLang）。
            要求：
            1. 只输出译文，不要解释、不要前缀。
            2. 保留原文中的专有名词、数字、URL、代码片段。
            3. 译文使用自然流畅的简体中文。
        """.trimIndent()
    }

    fun buildTranslationResult(
        sourceText: String,
        translatedText: String,
        sourceLang: String,
        targetLang: String = targetLanguage.code,
        fromCache: Boolean = false,
        skipped: Boolean = false,
    ): TranslationResult {
        val route = formatRouteLabel(sourceLang, targetLang)
        val status = when {
            skipped -> "已是中文"
            fromCache -> "$route（缓存）"
            else -> route
        }
        return TranslationResult(
            sourceText = sourceText,
            translatedText = translatedText,
            sourceLang = sourceLang,
            targetLang = targetLang,
            status = status,
            fromCache = fromCache,
            skipped = skipped,
        )
    }
}
