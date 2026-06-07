package com.translatehelper

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityNodeInfo

class ScreenReaderAccessibilityService : AccessibilityService() {
    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
    }

    override fun onDestroy() {
        instance = null
        super.onDestroy()
    }

    override fun onAccessibilityEvent(event: android.view.accessibility.AccessibilityEvent?) {
        // Passive service; text is pulled on demand when bubble is tapped.
    }

    override fun onInterrupt() = Unit

    fun extractVisibleText(maxChars: Int = 1200): String {
        val root = rootInActiveWindow ?: return ""
        val chunks = mutableListOf<String>()
        collectText(root, chunks, maxChars)
        root.recycle()
        return normalizeCollectedText(chunks)
    }

    private fun collectText(node: AccessibilityNodeInfo?, chunks: MutableList<String>, maxChars: Int) {
        if (node == null) {
            return
        }
        val currentLength = chunks.sumOf { it.length }
        if (currentLength >= maxChars) {
            return
        }

        node.text?.toString()?.trim()?.takeIf { it.isNotEmpty() }?.let { chunks.add(it) }
        node.contentDescription?.toString()?.trim()?.takeIf { it.isNotEmpty() }?.let { chunks.add(it) }

        for (i in 0 until node.childCount) {
            val child = node.getChild(i)
            collectText(child, chunks, maxChars)
            child?.recycle()
        }
    }

    private fun normalizeCollectedText(chunks: List<String>): String {
        if (chunks.isEmpty()) {
            return ""
        }
        val seen = linkedSetOf<String>()
        val ordered = mutableListOf<String>()
        chunks.forEach { raw ->
            val cleaned = raw.replace(Regex("\\s+"), " ").trim()
            if (cleaned.length >= 2 && seen.add(cleaned)) {
                ordered.add(cleaned)
            }
        }
        return ordered.joinToString("\n").take(1200).trim()
    }

    companion object {
        @Volatile
        var instance: ScreenReaderAccessibilityService? = null

        fun isEnabled(): Boolean = instance != null
    }
}
