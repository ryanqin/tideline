/*
 * The shore, as a backdrop — the phone's quiet echo of the web's intertidal
 * world (DESIGN §10): golden-hour light pooling down the screen, and at the
 * foot a tideline — amber where the water just was, wet sand below, the last
 * tide's coral trace above. Same drawing language as the launcher icon; the
 * desk and the review deck stand on this sand. The museum stays indoors.
 *
 * Deliberately static: no clock, no tides, no weather — those belong to the
 * web's desk ambience. A capture tool keeps its shore still.
 */

package com.ryanqin.tideline.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import com.ryanqin.tideline.ui.theme.Amber
import com.ryanqin.tideline.ui.theme.Coral
import com.ryanqin.tideline.ui.theme.Sand
import com.ryanqin.tideline.ui.theme.SandDeep
import com.ryanqin.tideline.ui.theme.SunWhite

/** One tide curve across the width at height y — the icon's line, full-bleed. */
private fun tide(w: Float, y: Float, amp: Float) = Path().apply {
  moveTo(-w * 0.02f, y)
  cubicTo(w * 0.16f, y - amp, w * 0.34f, y + amp, w * 0.52f, y)
  cubicTo(w * 0.70f, y - amp, w * 0.86f, y + amp, w * 1.02f, y)
}

@Composable
fun ShoreBackdrop(content: @Composable () -> Unit) {
  Box(Modifier.fillMaxSize()) {
    Canvas(Modifier.fillMaxSize()) {
      drawRect(
        Brush.verticalGradient(
          0f to SunWhite, 0.55f to Sand, 1f to SandDeep,
          startY = 0f, endY = size.height,
        )
      )
      val w = size.width
      val lineY = size.height * 0.88f
      // wet sand below the line, where the water just was
      drawPath(
        tide(w, lineY, 16f).apply {
          lineTo(w * 1.02f, size.height); lineTo(-w * 0.02f, size.height); close()
        },
        color = SandDeep,
      )
      // the last tide's fainter trace
      drawPath(
        tide(w, size.height * 0.83f, 12f),
        color = Coral.copy(alpha = 0.30f),
        style = Stroke(width = 4f, cap = StrokeCap.Round),
      )
      // the tideline itself
      drawPath(
        tide(w, lineY, 16f),
        color = Amber.copy(alpha = 0.55f),
        style = Stroke(width = 8f, cap = StrokeCap.Round),
      )
    }
    content()
  }
}

/** A small standalone tideline mark — the resting shore's quiet signature. */
@Composable
fun TidelineMark(modifier: Modifier = Modifier) {
  Canvas(modifier) {
    val w = size.width
    val y = size.height * 0.55f
    drawPath(
      tide(w, y - size.height * 0.3f, size.height * 0.18f),
      color = Coral.copy(alpha = 0.35f),
      style = Stroke(width = 3f, cap = StrokeCap.Round),
    )
    drawPath(
      tide(w, y, size.height * 0.22f),
      color = Amber.copy(alpha = 0.6f),
      style = Stroke(width = 5f, cap = StrokeCap.Round),
    )
    // a grain of the reward colour where the water turned
    drawCircle(Coral.copy(alpha = 0.5f), radius = 4f, center = Offset(w * 0.52f, y))
  }
}
