package com.translatehelper

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.util.DisplayMetrics
import android.view.WindowManager
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import kotlinx.coroutines.tasks.await

object ScreenCaptureStore {
    var mediaProjection: MediaProjection? = null
}

class RegionOcrActivity : AppCompatActivity() {
    private lateinit var selectionView: RegionSelectionView

    override fun onCreate(savedInstanceState: android.os.Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_region_ocr)
        selectionView = findViewById(R.id.regionSelectionView)

        if (ScreenCaptureStore.mediaProjection == null) {
            requestScreenCapture.launch(
                (getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager).createScreenCaptureIntent(),
            )
            return
        }

        selectionView.onRegionSelected = { rect ->
            runCatching {
                val text = captureAndOcr(rect)
                TranslateCoordinator.onOcrTextReady(text)
            }.onFailure {
                TranslateCoordinator.onTranslateFailed(it.message ?: "OCR 失败")
            }
            finish()
        }
    }

    private val requestScreenCapture =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            if (result.resultCode != Activity.RESULT_OK || result.data == null) {
                TranslateCoordinator.onTranslateFailed("未授予屏幕捕获权限")
                finish()
                return@registerForActivityResult
            }
            val manager = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            ScreenCaptureStore.mediaProjection = manager.getMediaProjection(result.resultCode, result.data!!)
            selectionView.onRegionSelected = { rect ->
                runCatching {
                    val text = captureAndOcr(rect)
                    TranslateCoordinator.onOcrTextReady(text)
                }.onFailure {
                    TranslateCoordinator.onTranslateFailed(it.message ?: "OCR 失败")
                }
                finish()
            }
        }

    private suspend fun captureAndOcr(rect: android.graphics.Rect): String {
        val projection = ScreenCaptureStore.mediaProjection
            ?: throw IllegalStateException("屏幕捕获未就绪")

        val metrics = DisplayMetrics()
        val windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        windowManager.defaultDisplay.getRealMetrics(metrics)
        val width = metrics.widthPixels
        val height = metrics.heightPixels
        val density = metrics.densityDpi

        val reader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)
        val display = projection.createVirtualDisplay(
            "translate-helper-ocr",
            width,
            height,
            density,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            reader.surface,
            null,
            null,
        )

        val bitmap = waitForBitmap(reader, width, height)
        display.release()
        reader.close()

        val safeRect = android.graphics.Rect(
            rect.left.coerceAtLeast(0),
            rect.top.coerceAtLeast(0),
            rect.right.coerceAtMost(width),
            rect.bottom.coerceAtMost(height),
        )
        if (safeRect.width() < 20 || safeRect.height() < 20) {
            throw IllegalStateException("选区太小")
        }

        val cropped = Bitmap.createBitmap(
            bitmap,
            safeRect.left,
            safeRect.top,
            safeRect.width(),
            safeRect.height(),
        )
        val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        val result = recognizer.process(InputImage.fromBitmap(cropped, 0)).await()
        val text = result.text.trim()
        if (text.isBlank()) {
            throw IllegalStateException("OCR 未识别到文字")
        }
        return text
    }

    private suspend fun waitForBitmap(reader: ImageReader, width: Int, height: Int): Bitmap {
        repeat(8) {
            kotlinx.coroutines.delay(120)
            val image = reader.acquireLatestImage()
            if (image != null) {
                val plane = image.planes[0]
                val buffer = plane.buffer
                val pixelStride = plane.pixelStride
                val rowStride = plane.rowStride
                val rowPadding = rowStride - pixelStride * width
                val bitmap = Bitmap.createBitmap(
                    width + rowPadding / pixelStride,
                    height,
                    Bitmap.Config.ARGB_8888,
                )
                bitmap.copyPixelsFromBuffer(buffer)
                image.close()
                return Bitmap.createBitmap(bitmap, 0, 0, width, height)
            }
        }
        throw IllegalStateException("截屏超时")
    }
}
