/*
 * The captured photo, whole and uncropped — the scene exactly as it was met.
 * Shared by the review deck and the museum (one rendering, two rooms). The
 * word is the shown question in REVIEW everywhere now (review-direction flip),
 * so review shows the photo plain. In BROWSE the museum can cover the one word
 * a photo actually held and let you tap to reveal it — see the place, reach for
 * the word — mirroring the web's browse-mode photo mask (sheet.js photoFigure).
 * The OCR geometry lives in translations.source_region.
 */

package com.ryanqin.tideline.ui

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.dp

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

/** A normalized [x0,y0,x1,y1] OCR box as stored in source_region, or null if
 * absent/malformed — mirror of the web's _parse_region fail-soft. */
internal fun parseRegion(raw: String?): List<Float>? {
  if (raw.isNullOrBlank()) return null
  return runCatching {
    raw.trim().removePrefix("[").removeSuffix("]")
      .split(",").map { it.trim().toFloat() }
      .takeIf { it.size == 4 }
  }.getOrNull()
}

/** The captured photo with the one word it held covered (museum browse): a warm
 * sand patch over the OCR box, tap to reveal — the look-at-the-place-and-reach
 * game cards play. Falls back to the plain photo when the word's spot is
 * unknown. The photo must stay uncropped (ContentScale.Fit at the bitmap's own
 * aspect ratio) so the normalized box maps 1:1 onto displayed pixels. */
@Composable
internal fun MaskableCapturePhoto(bitmap: Bitmap, region: List<Float>?) {
  if (region == null || region.size != 4) {
    CapturePhoto(bitmap)
    return
  }
  val x0 = region[0].coerceIn(0f, 1f)
  val y0 = region[1].coerceIn(0f, 1f)
  val x1 = region[2].coerceIn(0f, 1f)
  val y1 = region[3].coerceIn(0f, 1f)
  BoxWithConstraints(Modifier.fillMaxWidth().aspectRatio(bitmap.width.toFloat() / bitmap.height)) {
    Image(
      bitmap = bitmap.asImageBitmap(),
      contentDescription = null,
      modifier = Modifier.fillMaxSize(),
      contentScale = ContentScale.Fit,
    )
    // maxWidth/maxHeight must be read here in the BoxWithConstraints scope —
    // a nested Box can't see them. The Box fills the photo's display rect
    // (Fit + matching aspect), so the box maps directly onto pixels.
    var revealed by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(4.dp)
    Box(
      Modifier
        .offset(x = maxWidth * x0, y = maxHeight * y0)
        .size(width = maxWidth * (x1 - x0), height = maxHeight * (y1 - y0))
        .clip(shape)
        .background(if (revealed) Color.Transparent else MaterialTheme.colorScheme.surfaceVariant)
        .border(
          1.dp,
          if (revealed) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline,
          shape,
        )
        .clickable(
          interactionSource = remember { MutableInteractionSource() },
          indication = null,
        ) { revealed = !revealed },
    )
  }
}
