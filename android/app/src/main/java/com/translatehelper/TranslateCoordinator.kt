package com.translatehelper

import android.content.Context
import android.content.Intent
import android.graphics.PixelFormat
import android.os.Build
import android.view.Gravity
import android.view.LayoutInflater
import android.view.WindowManager
import android.widget.TextView
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

object TranslateCoordinator {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var overlayManager: TranslationOverlayManager? = null
    private var preferences: AppPreferences? = null

    fun init(context: Context) {
        val appContext = context.applicationContext
        if (overlayManager == null) {
            overlayManager = TranslationOverlayManager(appContext)
        }
        if (preferences == null) {
            preferences = AppPreferences(appContext)
        }
    }

    fun onBubbleClicked(context: Context) {
        init(context)
        overlayManager?.showLoading("正在读取屏幕文字…")

        val accessibilityText = ScreenReaderAccessibilityService.instance
            ?.extractVisibleText()
            .orEmpty()
            .trim()

        if (accessibilityText.length >= 2) {
            translateText(context, accessibilityText, sourceHint = "无障碍读屏")
            return
        }

        overlayManager?.showLoading("读屏失败，请框选区域 OCR…")
        val intent = Intent(context, RegionOcrActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
    }

    fun onOcrTextReady(text: String) {
        val context = overlayManager?.context ?: return
        translateText(context, text, sourceHint = "区域 OCR")
    }

    fun onTranslateFailed(message: String) {
        overlayManager?.showError(message)
    }

    fun translateText(context: Context, text: String, sourceHint: String = "") {
        init(context)
        val prefs = preferences ?: AppPreferences(context)
        overlayManager?.showLoading(
            if (sourceHint.isBlank()) "翻译中…" else "$sourceHint · 翻译中…",
            preview = text.take(120),
        )
        scope.launch {
            runCatching {
                prefs.translator().translate(text)
            }.onSuccess { result ->
                overlayManager?.showResult(result)
            }.onFailure { error ->
                overlayManager?.showError(error.message ?: "翻译失败")
            }
        }
    }
}

class TranslationOverlayManager(val context: Context) {
    private val windowManager = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
    private var overlayView: android.view.View? = null

    fun showLoading(status: String, preview: String = "") {
        ensureOverlay()
        overlayView?.findViewById<TextView>(R.id.overlayStatus)?.text = status
        overlayView?.findViewById<TextView>(R.id.overlaySource)?.text = preview
        overlayView?.findViewById<TextView>(R.id.overlayTranslated)?.text = ""
    }

    fun showResult(result: TranslationResult) {
        ensureOverlay()
        overlayView?.findViewById<TextView>(R.id.overlayStatus)?.text = result.status
        overlayView?.findViewById<TextView>(R.id.overlaySource)?.text = result.sourceText.take(180)
        overlayView?.findViewById<TextView>(R.id.overlayTranslated)?.text =
            if (result.skipped) "（已是中文，无需翻译）" else result.translatedText
    }

    fun showError(message: String) {
        ensureOverlay()
        overlayView?.findViewById<TextView>(R.id.overlayStatus)?.text = "翻译失败"
        overlayView?.findViewById<TextView>(R.id.overlayTranslated)?.text = message
    }

    private fun ensureOverlay() {
        if (overlayView != null) {
            return
        }
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            } else {
                @Suppress("DEPRECATION")
                WindowManager.LayoutParams.TYPE_PHONE
            },
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.CENTER_HORIZONTAL
            y = 180
        }
        overlayView = LayoutInflater.from(context).inflate(R.layout.overlay_translation, null)
        windowManager.addView(overlayView, params)
    }
}
