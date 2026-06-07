package com.translatehelper

import android.content.Context
import android.content.SharedPreferences

class AppPreferences(context: Context) {
    private val prefs: SharedPreferences =
        context.applicationContext.getSharedPreferences("translate_helper", Context.MODE_PRIVATE)

    var hfToken: String
        get() = prefs.getString(KEY_HF_TOKEN, BuildConfig.HF_TOKEN).orEmpty()
        set(value) = prefs.edit().putString(KEY_HF_TOKEN, value.trim()).apply()

    var clipboardMonitorEnabled: Boolean
        get() = prefs.getBoolean(KEY_CLIPBOARD_MONITOR, false)
        set(value) = prefs.edit().putBoolean(KEY_CLIPBOARD_MONITOR, value).apply()

    fun translator(): HuggingFaceTranslator {
        return HuggingFaceTranslator(token = hfToken)
    }

    companion object {
        private const val KEY_HF_TOKEN = "hf_token"
        private const val KEY_CLIPBOARD_MONITOR = "clipboard_monitor"
    }
}
