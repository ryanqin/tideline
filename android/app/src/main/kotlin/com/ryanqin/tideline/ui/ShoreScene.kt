/*
 * The full shore — the web's sceneSVG (shore.js), carried to Compose layer
 * by layer and held at 18:00, the golden hour the whole product palette was
 * shipped from. Portrait fit of the same geometry:
 *
 *   sky (3-stop warm gradient) ............ 0 → 46% — never blue or grey
 *   the sun, a soft warm bloom ............ low on the right horizon
 *   ground (one warm shade wash) .......... 46% → bottom
 *   17 contour lines ...................... the sea and the sand drawn by
 *       line density alone: dense + deep at the horizon, open + pale at
 *       your feet (y = skyBot + d²·rest — the web's perspective)
 *   two sea-sheen lines ................... faint warm light on the water
 *   the living tideline ................... the brightest line, where water
 *       meets sand, with its wash below and the last tide's mark above
 *
 * Deliberately still (no breathing loop — a capture tool keeps its shore
 * calm); the web's sand-grain turbulence has no cheap Compose equivalent and
 * is left to the wash.
 */

package com.ryanqin.tideline.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import kotlin.math.PI
import kotlin.math.sin

// The 18:00 keyframe from shore.js's SKY table, and the tints sceneGeom
// derives from it. Warm-only (§10): time of day is depth of warmth.
private val SkyTop = Color(200, 132, 108)
private val SkyMid = Color(232, 160, 112)
private val SkyHor = Color(248, 196, 128)
private val Sand18 = Color(224, 176, 132)
private val Glow = Color(255, 198, 130)
private val WarmHi = Color(255, 224, 186) // lerp(glow, warm-white, .5)
private val FarLine = Color(155, 119, 91) // deep, at the horizon
private val NearLine = Color(240, 189, 129) // pale, at your feet
private val GroundTop = Color(190, 148, 112)
private val GroundBot = Color(238, 188, 130)

/** The creatures' ink on this light — lerp(hor, deep brown, .72), shared by
 * every shell and its name (an unopened shell is never a paler shape). */
val ShoreInk = Color(126, 89, 60)

private const val HOUR = 18f
const val SHORE_SKY_BOT = 0.46f // horizon, as a fraction of height
const val SHORE_SURF_Y = 0.68f // where water meets sand (mid tide)

/** One wave of the web's wavePath: sine-sampled quadratic chain. */
private fun wavePath(w: Float, y: Float, amp: Float, len: Float, phase: Float): Path {
  val p = Path()
  p.moveTo(0f, y)
  var x = 0f
  while (x <= w) {
    val yy = y + sin((x / len) * 2f * PI.toFloat() + phase) * amp
    p.quadraticTo(x + len / 4f, yy + amp, x + len / 2f, y)
    x += len / 2f
  }
  return p
}

@Composable
fun ShoreScene(content: @Composable BoxScope.() -> Unit) {
  Box(Modifier.fillMaxSize()) {
    Canvas(Modifier.fillMaxSize()) {
      val w = size.width
      val h = size.height
      val skyBot = h * SHORE_SKY_BOT
      val surfY = h * SHORE_SURF_Y

      // sky
      drawRect(
        Brush.verticalGradient(0f to SkyTop, 0.6f to SkyMid, 1f to SkyHor, startY = 0f, endY = skyBot),
        size = Size(w, skyBot),
      )
      // the sun: a soft warm bloom low on the right — light through haze,
      // never a hard disc
      val bloomR = (minOf(w, h) * 0.3f).coerceIn(110.dp.toPx(), 360.dp.toPx())
      val bodyC = Offset(w * 0.86f, skyBot * 0.88f)
      drawCircle(
        Brush.radialGradient(
          0f to Glow.copy(alpha = 0.55f),
          0.45f to Glow.copy(alpha = 0.165f),
          1f to Glow.copy(alpha = 0f),
          center = bodyC, radius = bloomR,
        ),
        radius = bloomR, center = bodyC,
      )
      // ground: one warm shade wash; all depth comes from the lines
      drawRect(
        Brush.verticalGradient(0f to GroundTop, 1f to GroundBot, startY = skyBot, endY = h),
        topLeft = Offset(0f, skyBot), size = Size(w, h - skyBot),
      )
      // the contour field: 17 lines, dense + deep far, open + pale near
      val n = 17
      for (i in 1..n) {
        val d = i / (n + 1f)
        val y = skyBot + d * d * (h - skyBot)
        val amp = h * (0.003f + d * 0.01f)
        val len = w * (0.55f - d * 0.2f)
        val a = 0.4f - d * 0.27f
        val c = lerp(FarLine, NearLine, d).copy(alpha = a)
        drawPath(
          wavePath(w, y, amp, len, HOUR * 0.5f + i * 1.7f),
          color = c,
          style = Stroke(width = (1.5f - d * 0.6f).dp.toPx(), cap = StrokeCap.Round),
        )
      }
      // two sea-sheen lines, woven into the field
      drawPath(
        wavePath(w, skyBot + (surfY - skyBot) * 0.34f, h * 0.004f, w * 0.5f, HOUR * 0.6f),
        color = WarmHi.copy(alpha = 0.18f), style = Stroke(1.5.dp.toPx()),
      )
      drawPath(
        wavePath(w, skyBot + (surfY - skyBot) * 0.66f, h * 0.005f, w * 0.42f, HOUR),
        color = WarmHi.copy(alpha = 0.22f), style = Stroke(1.5.dp.toPx()),
      )
      // the living tideline: its wash below, the bright line, the last
      // tide's mark above
      val surfFill = wavePath(w, surfY, h * 0.012f, w * 0.34f, HOUR * 1.3f).apply {
        lineTo(w, surfY + h * 0.045f)
        lineTo(0f, surfY + h * 0.045f)
        close()
      }
      drawPath(surfFill, color = WarmHi.copy(alpha = 0.2f))
      drawPath(
        wavePath(w, surfY, h * 0.012f, w * 0.34f, HOUR * 1.3f),
        color = WarmHi.copy(alpha = 0.75f), style = Stroke(2.25.dp.toPx(), cap = StrokeCap.Round),
      )
      drawPath(
        wavePath(w, surfY - h * 0.07f, h * 0.01f, w * 0.4f, HOUR * 0.9f),
        color = Sand18.copy(alpha = 0.5f), style = Stroke(1.5.dp.toPx(), cap = StrokeCap.Round),
      )
    }
    content()
  }
}

private fun lerp(a: Color, b: Color, t: Float): Color = Color(
  red = a.red + (b.red - a.red) * t,
  green = a.green + (b.green - a.green) * t,
  blue = a.blue + (b.blue - a.blue) * t,
)
