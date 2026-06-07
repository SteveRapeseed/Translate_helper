package com.translatehelper

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View

class RegionSelectionView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {
    var onRegionSelected: ((Rect) -> Unit)? = null

    private val borderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#60A5FA")
        style = Paint.Style.STROKE
        strokeWidth = 4f
    }
    private val fillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#332563EB")
        style = Paint.Style.FILL
    }

    private var startX = 0f
    private var startY = 0f
    private var endX = 0f
    private var endY = 0f
    private var dragging = false

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                dragging = true
                startX = event.x
                startY = event.y
                endX = event.x
                endY = event.y
                invalidate()
            }
            MotionEvent.ACTION_MOVE -> {
                if (dragging) {
                    endX = event.x
                    endY = event.y
                    invalidate()
                }
            }
            MotionEvent.ACTION_UP -> {
                if (dragging) {
                    dragging = false
                    endX = event.x
                    endY = event.y
                    invalidate()
                    val rect = currentRect()
                    if (rect.width() >= 40 && rect.height() >= 40) {
                        onRegionSelected?.invoke(rect)
                    }
                }
            }
        }
        return true
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val rect = currentRect()
        if (rect.width() > 0 && rect.height() > 0) {
            canvas.drawRect(rect, fillPaint)
            canvas.drawRect(rect, borderPaint)
        }
    }

    private fun currentRect(): Rect {
        val left = minOf(startX, endX).toInt()
        val top = minOf(startY, endY).toInt()
        val right = maxOf(startX, endX).toInt()
        val bottom = maxOf(startY, endY).toInt()
        return Rect(left, top, right, bottom)
    }
}
