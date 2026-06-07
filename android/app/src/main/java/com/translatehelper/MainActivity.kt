package com.translatehelper

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import com.translatehelper.databinding.ActivityMainBinding

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private lateinit var preferences: AppPreferences

    private val mediaProjectionLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            if (result.resultCode != RESULT_OK || result.data == null) {
                setStatus("未授予屏幕捕获权限，OCR 兜底不可用")
                return@registerForActivityResult
            }
            val manager = getSystemService(MEDIA_PROJECTION_SERVICE) as android.media.projection.MediaProjectionManager
            ScreenCaptureStore.mediaProjection = manager.getMediaProjection(result.resultCode, result.data!!)
            setStatus("屏幕捕获已授权，可启动悬浮球")
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        preferences = AppPreferences(this)
        TranslateCoordinator.init(this)

        binding.tokenInput.setText(preferences.hfToken)
        binding.switchClipboard.isChecked = preferences.clipboardMonitorEnabled

        binding.btnOpenOverlay.setOnClickListener { openOverlaySettings() }
        binding.btnOpenAccessibility.setOnClickListener { openAccessibilitySettings() }
        binding.btnStartBubble.setOnClickListener { startBubbleFlow() }
        binding.btnStopBubble.setOnClickListener { stopBubbleFlow() }
        binding.switchClipboard.setOnCheckedChangeListener { _, checked ->
            preferences.clipboardMonitorEnabled = checked
            if (checked) {
                startService(Intent(this, ClipboardMonitorService::class.java))
                setStatus("剪贴板自动翻译已开启")
            } else {
                stopService(Intent(this, ClipboardMonitorService::class.java))
                setStatus("剪贴板自动翻译已关闭")
            }
        }

        if (preferences.clipboardMonitorEnabled) {
            startService(Intent(this, ClipboardMonitorService::class.java))
        }
    }

    private fun startBubbleFlow() {
        preferences.hfToken = binding.tokenInput.text?.toString().orEmpty()
        if (preferences.hfToken.isBlank()) {
            Toast.makeText(this, "请先配置 HF Token", Toast.LENGTH_SHORT).show()
            return
        }
        if (!Settings.canDrawOverlays(this)) {
            Toast.makeText(this, "请先开启悬浮窗权限", Toast.LENGTH_SHORT).show()
            openOverlaySettings()
            return
        }
        if (ScreenCaptureStore.mediaProjection == null) {
            val manager = getSystemService(MEDIA_PROJECTION_SERVICE) as android.media.projection.MediaProjectionManager
            mediaProjectionLauncher.launch(manager.createScreenCaptureIntent())
        }
        startForegroundServiceCompat(Intent(this, FloatingBubbleService::class.java))
        setStatus("悬浮球已启动：单击翻译，无障碍优先，失败则区域 OCR")
    }

    private fun stopBubbleFlow() {
        stopService(Intent(this, FloatingBubbleService::class.java))
        setStatus("悬浮球已停止")
    }

    private fun openOverlaySettings() {
        val intent = Intent(
            Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
            Uri.parse("package:$packageName"),
        )
        startActivity(intent)
    }

    private fun openAccessibilitySettings() {
        startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
    }

    private fun setStatus(text: String) {
        binding.statusText.text = text
    }

    private fun startForegroundServiceCompat(intent: Intent) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
    }
}
