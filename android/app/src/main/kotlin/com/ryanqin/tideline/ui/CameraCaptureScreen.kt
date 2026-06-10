/*
 * Phase 5a — in-app viewfinder.
 *
 * Full-screen CameraX preview with a single shutter: point at a menu / sign,
 * snap, and the JPEG goes straight into the multimodal translate path. The
 * capture is handed back RAW (bytes + the ImageProxy's rotation) so the
 * heavy decode/rotate/downscale work runs off the main thread in the
 * ViewModel, not in this UI callback.
 */

package com.ryanqin.tideline.ui

import android.util.Log
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner

private const val TAG = "CameraCapture"

@Composable
fun CameraCaptureScreen(
  onCaptured: (bytes: ByteArray, rotationDegrees: Int) -> Unit,
  onClose: () -> Unit,
) {
  val context = LocalContext.current
  val lifecycleOwner = LocalLifecycleOwner.current
  val imageCapture = remember {
    ImageCapture.Builder()
      .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
      .build()
  }
  var provider by remember { mutableStateOf<ProcessCameraProvider?>(null) }
  var shutterBusy by remember { mutableStateOf(false) }

  Box(modifier = Modifier.fillMaxSize()) {
    AndroidView(
      modifier = Modifier.fillMaxSize(),
      factory = { ctx ->
        PreviewView(ctx).also { view ->
          val future = ProcessCameraProvider.getInstance(ctx)
          future.addListener(
            {
              try {
                val p = future.get()
                val preview = Preview.Builder().build().also {
                  it.surfaceProvider = view.surfaceProvider
                }
                p.unbindAll()
                p.bindToLifecycle(
                  lifecycleOwner,
                  CameraSelector.DEFAULT_BACK_CAMERA,
                  preview,
                  imageCapture,
                )
                provider = p
              } catch (t: Throwable) {
                Log.e(TAG, "Camera bind failed", t)
                onClose()
              }
            },
            ContextCompat.getMainExecutor(ctx),
          )
        }
      },
    )

    IconButton(
      onClick = onClose,
      modifier = Modifier
        .align(Alignment.TopStart)
        .padding(12.dp),
      colors = IconButtonDefaults.iconButtonColors(
        containerColor = Color.Black.copy(alpha = 0.35f),
        contentColor = Color.White,
      ),
    ) {
      Icon(Icons.Default.Close, contentDescription = "Close camera")
    }

    FilledIconButton(
      onClick = {
        if (shutterBusy) return@FilledIconButton
        shutterBusy = true
        imageCapture.takePicture(
          ContextCompat.getMainExecutor(context),
          object : ImageCapture.OnImageCapturedCallback() {
            override fun onCaptureSuccess(image: ImageProxy) {
              val (bytes, rotation) = image.use { proxy ->
                val buf = proxy.planes[0].buffer
                ByteArray(buf.remaining()).also { buf.get(it) } to
                  proxy.imageInfo.rotationDegrees
              }
              onCaptured(bytes, rotation)
            }

            override fun onError(exception: ImageCaptureException) {
              Log.e(TAG, "Capture failed", exception)
              shutterBusy = false
            }
          },
        )
      },
      modifier = Modifier
        .align(Alignment.BottomCenter)
        .padding(bottom = 36.dp)
        .size(72.dp),
      enabled = !shutterBusy,
    ) {
      Icon(
        Icons.Default.PhotoCamera,
        contentDescription = "Capture and translate",
        modifier = Modifier.size(32.dp),
      )
    }
  }

  DisposableEffect(Unit) {
    onDispose {
      try {
        provider?.unbindAll()
      } catch (_: Throwable) {}
    }
  }
}
