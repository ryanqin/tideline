/*
 * Capture image preparation — one path for both input routes.
 *
 * A captured photo serves two consumers with the same bytes: the vision
 * encoder (which downscales internally anyway, so a 12 MP original buys
 * nothing but a slower ImageBytes hop) and the `source_image` drawer column
 * (recall material, where a multi-MB blob per row would bloat the DB the
 * history list reads from). Downscaling once to a bounded edge and
 * re-encoding keeps both honest.
 *
 * Rotation matters for both: CameraX reports the sensor-to-display rotation
 * on the ImageProxy, gallery photos carry EXIF orientation that
 * BitmapFactory silently ignores — skip either and stored recall photos
 * render sideways.
 */

package com.ryanqin.tideline.media

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import androidx.exifinterface.media.ExifInterface
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream

// Longest edge of the prepared image. 1024 keeps menu text legible for recall
// while staying well above the vision encoder's own input resolution.
private const val MAX_EDGE = 1024

private const val JPEG_QUALITY = 85

/** EXIF orientation of an encoded image, as clockwise degrees (0 when absent). */
fun exifRotationDegrees(bytes: ByteArray): Int =
  try {
    ExifInterface(ByteArrayInputStream(bytes)).rotationDegrees
  } catch (_: Throwable) {
    0
  }

/**
 * Decode → rotate upright → cap the longest edge at [MAX_EDGE] → re-encode
 * as JPEG. Returns null when the bytes don't decode as an image.
 */
fun prepareCaptureImage(bytes: ByteArray, rotationDegrees: Int): ByteArray? {
  // Bounds-only pass to pick a power-of-two subsample, so a 12 MP capture
  // never fully inflates in memory just to be shrunk again.
  val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
  BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
  if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null
  var sample = 1
  while (maxOf(bounds.outWidth, bounds.outHeight) / (sample * 2) >= MAX_EDGE) sample *= 2

  val opts = BitmapFactory.Options().apply { inSampleSize = sample }
  val decoded = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, opts) ?: return null

  val scale = MAX_EDGE.toFloat() / maxOf(decoded.width, decoded.height)
  val matrix = Matrix().apply {
    if (scale < 1f) postScale(scale, scale)
    if (rotationDegrees != 0) postRotate(rotationDegrees.toFloat())
  }
  val upright =
    if (matrix.isIdentity) decoded
    else Bitmap.createBitmap(decoded, 0, 0, decoded.width, decoded.height, matrix, true)

  val out = ByteArrayOutputStream()
  upright.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, out)
  if (upright !== decoded) upright.recycle()
  decoded.recycle()
  return out.toByteArray()
}
