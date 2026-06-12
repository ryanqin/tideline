/*
 * The captured photo, whole and uncropped — the scene exactly as it was met.
 * Shared by the review deck and the museum (one rendering, two rooms). The
 * photo-pixel word mask retired with the review-direction flip: the word is
 * the shown question everywhere now; the OCR geometry in source_region stays
 * for the web's browse-mode mask toggle.
 */

package com.ryanqin.tideline.ui

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale

@Composable
internal fun CapturePhoto(bitmap: Bitmap) {
  Box(modifier = Modifier.fillMaxWidth().aspectRatio(bitmap.width.toFloat() / bitmap.height)) {
    Image(
      bitmap = bitmap.asImageBitmap(),
      contentDescription = null,
      modifier = Modifier.fillMaxSize(),
      contentScale = ContentScale.Fit,
    )
  }
}
