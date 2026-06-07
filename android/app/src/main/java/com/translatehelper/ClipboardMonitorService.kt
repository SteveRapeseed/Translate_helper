package com.translatehelper

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.ClipDescription
import android.content.ClipboardManager
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat

class ClipboardMonitorService : Service(), ClipboardManager.OnPrimaryClipChangedListener {
    private lateinit var clipboardManager: ClipboardManager
    private var lastSeenText = ""

    override fun onCreate() {
        super.onCreate()
        TranslateCoordinator.init(this)
        clipboardManager = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
        createNotificationChannel()
        startForeground(NOTIFICATION_ID, buildNotification())
        clipboardManager.addPrimaryClipChangedListener(this)
    }

    override fun onDestroy() {
        clipboardManager.removePrimaryClipChangedListener(this)
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onPrimaryClipChanged() {
        val clip = clipboardManager.primaryClip ?: return
        if (!clipboardManager.hasPrimaryClip()) {
            return
        }
        if (clip.description.hasMimeType(ClipDescription.MIMETYPE_TEXT_PLAIN)) {
            val text = clip.getItemAt(0).coerceToText(this)?.toString()?.trim().orEmpty()
            if (text.length < 2 || text == lastSeenText) {
                return
            }
            lastSeenText = text
            TranslateCoordinator.translateText(this, text, sourceHint = "剪贴板")
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Translate Helper Clipboard",
                NotificationManager.IMPORTANCE_LOW,
            )
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    private fun buildNotification(): Notification {
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.clipboard_notification_title))
            .setContentText(getString(R.string.clipboard_notification_text))
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
    }

    companion object {
        private const val CHANNEL_ID = "clipboard_channel"
        private const val NOTIFICATION_ID = 1002
    }
}
