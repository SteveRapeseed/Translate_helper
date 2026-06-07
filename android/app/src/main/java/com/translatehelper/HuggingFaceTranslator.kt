package com.translatehelper

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class HuggingFaceTranslator(
    private val token: String,
    private val baseUrl: String = BuildConfig.HF_BASE_URL,
    private val modelId: String = BuildConfig.HF_MODEL,
    private val allowedSources: List<String> = TranslationCore.defaultSourceLangs,
    private val targetLang: String = TranslationCore.targetLanguage.code,
) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(90, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    private val cache = LinkedHashMap<String, TranslationResult>(200, 0.75f, true)

    suspend fun translate(text: String): TranslationResult = withContext(Dispatchers.IO) {
        val normalized = text.trim()
        require(normalized.isNotEmpty()) { "文本为空" }
        require(token.isNotBlank()) { "HF_TOKEN 未配置" }

        cache[normalized]?.let { cached ->
            return@withContext cached.copy(fromCache = true, status = "${cached.status}（缓存）")
        }

        val detected = TranslationCore.detectSourceLanguage(normalized, allowedSources)
        val (skip, _) = TranslationCore.shouldSkipTranslation(normalized, detected, targetLang)
        if (skip) {
            return@withContext TranslationCore.buildTranslationResult(
                sourceText = normalized,
                translatedText = normalized,
                sourceLang = detected,
                targetLang = targetLang,
                skipped = true,
            )
        }

        val prompt = TranslationCore.buildSystemPrompt(
            sourceLang = detected,
            targetLang = targetLang,
            allowedSources = allowedSources,
        )
        val translated = callChatCompletions(prompt, normalized)
        val result = TranslationCore.buildTranslationResult(
            sourceText = normalized,
            translatedText = translated,
            sourceLang = detected,
            targetLang = targetLang,
        )
        cache[normalized] = result
        if (cache.size > 200) {
            val oldest = cache.keys.first()
            cache.remove(oldest)
        }
        result
    }

    private fun callChatCompletions(systemPrompt: String, userText: String): String {
        val endpoint = baseUrl.trimEnd('/') + "/chat/completions"
        val payload = JSONObject()
            .put("model", modelId)
            .put(
                "messages",
                org.json.JSONArray()
                    .put(JSONObject().put("role", "system").put("content", systemPrompt))
                    .put(JSONObject().put("role", "user").put("content", userText)),
            )
            .put("max_tokens", 256)
            .put("temperature", 0.1)

        val request = Request.Builder()
            .url(endpoint)
            .addHeader("Authorization", "Bearer $token")
            .addHeader("Content-Type", "application/json")
            .post(payload.toString().toRequestBody("application/json".toMediaType()))
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw IllegalStateException("HuggingFace API ${response.code}: ${body.take(180)}")
            }
            val json = JSONObject(body)
            val choices = json.optJSONArray("choices") ?: throw IllegalStateException("空响应")
            val message = choices.getJSONObject(0).optJSONObject("message")
            val content = message?.optString("content").orEmpty().trim()
            if (content.isBlank()) {
                throw IllegalStateException("模型返回空译文")
            }
            return normalizeOutput(content)
        }
    }

    private fun normalizeOutput(text: String): String {
        var cleaned = text.trim()
        cleaned = cleaned.replace(Regex("^(translation|translated text)\\s*[:：]\\s*", RegexOption.IGNORE_CASE), "")
        return cleaned.trim().trim('"', '\'')
    }
}
