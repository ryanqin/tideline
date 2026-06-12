/*
 * The shore's creatures — carried over PATH-FOR-PATH from the web's
 * shore.js GLYPHS (one product, one fauna). Each glyph is warm line art in a
 * 0..48 box: a faint same-colour fill lifts it off the sand without becoming
 * a block, rounded joins keep it soft and a little hand-drawn. A word card
 * draws a shell from the card pool by a stable hash of its own word (a real
 * shore's single shells are endlessly varied); a scene draws from the crab
 * family (crab = scene stays the type signal).
 *
 * The ink is the web shelf's warm brown (#84522c).
 */

package com.ryanqin.tideline.ui

import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.vector.PathParser
import kotlin.math.abs

val ShellInk = Color(0xFF84522C) // the web shelf's warm brown ink

/** One drawn piece of a glyph: an SVG path (or a circle), with the web's
 * fill-opacity / stroke-width / stroke-opacity. Dollar petals repeat with a
 * rotation, exactly like the SVG transform chain. */
private class Piece(
  d: String? = null,
  val circle: FloatArray? = null, // cx, cy, r
  val fillAlpha: Float = 0f,
  val strokeWidth: Float = 0f,
  val strokeAlpha: Float = 1f,
  val repeats: Int = 1,
  val pivot: Offset = Offset(24f, 26f),
) {
  val path: Path? = d?.let { PathParser().parsePathString(it).toPath() }
}

private val GLYPHS: Map<String, List<Piece>> by lazy {
  mapOf(
    // sea-glass: a soft frosted pebble with one inner gleam
    "glass" to listOf(
      Piece("M17 14Q31 10 37 20 41 32 28 36 14 38 12 26 11 17 17 14Z", fillAlpha = 0.22f, strokeWidth = 2f),
      Piece("M18 20.5Q23 17.5 27 20.5", strokeWidth = 1.3f, strokeAlpha = 0.65f),
    ),
    // a snail / nautilus: a round shell curling into an inner spiral
    "snail" to listOf(
      Piece("M24 12Q38 12 38 26 38 40 24 40 10 40 10 26 10 12 24 12Z", fillAlpha = 0.2f, strokeWidth = 2f),
      Piece("M25 33Q17 33 17 25.5 17 19 24 19 30 19 30 25 30 29.5 25 30", strokeWidth = 1.4f, strokeAlpha = 0.7f),
    ),
    // an auger / tower shell: a tall banded cone, point up
    "auger" to listOf(
      Piece("M24 8 33 39Q24 42 15 39Z", fillAlpha = 0.2f, strokeWidth = 2f),
      Piece("M22 16h4M20.5 23h7M19 30h10", strokeWidth = 1.3f, strokeAlpha = 0.6f),
    ),
    // a cowrie: a smooth egg with a curved seam down its back
    "cowrie" to listOf(
      Piece("M24 11Q37 12 37 26 37 40 24 40 11 40 11 26 11 12 24 11Z", fillAlpha = 0.2f, strokeWidth = 2f),
      Piece("M24 14Q26.5 26 24 37", strokeWidth = 1.4f, strokeAlpha = 0.65f),
    ),
    // a sand dollar: a disc with a five-petal flower
    "dollar" to listOf(
      Piece(circle = floatArrayOf(24f, 26f, 15f), fillAlpha = 0.2f, strokeWidth = 2f),
      Piece(
        "M24 26Q22 19 24 14Q26 19 24 26Z",
        fillAlpha = 0.16f, strokeWidth = 1.1f, strokeAlpha = 0.6f,
        repeats = 5, pivot = Offset(24f, 26f),
      ),
    ),
    // a round little crab: domed shell, dot eyes, raised claws, legs
    "crab" to listOf(
      Piece("M11 30c0-7.5 6-12 13-12s13 4.5 13 12c-2 3-24 3-26 0Z", fillAlpha = 0.2f, strokeWidth = 2f),
      Piece("M20 18.5v-3M28 18.5v-3", strokeWidth = 1.6f),
      Piece(circle = floatArrayOf(20f, 13.5f, 1.7f), fillAlpha = 1f),
      Piece(circle = floatArrayOf(28f, 13.5f, 1.7f), fillAlpha = 1f),
      Piece("M11.5 25c-4-1.5-6.5 0.5-6 4M36.5 25c4-1.5 6.5 0.5 6 4", strokeWidth = 1.6f),
      Piece("M13 31l-5 4.5M15.5 33l-4 5.5M35 31l5 4.5M32.5 33l4 5.5", strokeWidth = 1.3f, strokeAlpha = 0.8f),
    ),
    // crab2: claws raised in a little V above a rounder body
    "crab2" to listOf(
      Piece("M13.5 31.5c0-8 5-13 10.5-13s10.5 5 10.5 13c-2 2.6-19 2.6-21 0Z", fillAlpha = 0.2f, strokeWidth = 2f),
      Piece("M20.5 19.5v-3M27.5 19.5v-3", strokeWidth = 1.6f),
      Piece(circle = floatArrayOf(20.5f, 14f, 1.7f), fillAlpha = 1f),
      Piece(circle = floatArrayOf(27.5f, 14f, 1.7f), fillAlpha = 1f),
      Piece("M16 23.5c-3.5-2-5.5-5.5-4.5-9.5M32 23.5c3.5-2 5.5-5.5 4.5-9.5", strokeWidth = 1.6f),
      Piece("M14 32l-5 4M16 34l-4 5M34 32l5 4M32 34l4 5", strokeWidth = 1.3f, strokeAlpha = 0.8f),
    ),
    // crab3: a wide, flat spider-crab — long legs spread, small tucked claws
    "crab3" to listOf(
      Piece("M9 28.5c0-6 7-9.5 15-9.5s15 3.5 15 9.5c-2.5 2.4-27.5 2.4-30 0Z", fillAlpha = 0.2f, strokeWidth = 2f),
      Piece("M20.5 19.5v-2.6M27.5 19.5v-2.6", strokeWidth = 1.6f),
      Piece(circle = floatArrayOf(20.5f, 15f, 1.6f), fillAlpha = 1f),
      Piece(circle = floatArrayOf(27.5f, 15f, 1.6f), fillAlpha = 1f),
      Piece("M11 25.5c-3-1-4.5 0-4.5 2.5M37 25.5c3-1 4.5 0 4.5 2.5", strokeWidth = 1.5f),
      Piece("M12 29l-7 3.5M15 31l-6 5.5M18 32.5l-5 6.5M36 29l7 3.5M33 31l6 5.5M30 32.5l5 6.5", strokeWidth = 1.3f, strokeAlpha = 0.8f),
    ),
  )
}

// What a card / a scene can wash up as — the web's variety pools.
private val CARD_POOL = listOf("glass", "snail", "auger", "cowrie", "dollar")
private val CRAB_POOL = listOf("crab", "crab2", "crab3")

enum class GlyphKind { Card, Scene }

private fun glyphKey(kind: GlyphKind, seed: String): String {
  val pool = if (kind == GlyphKind.Card) CARD_POOL else CRAB_POOL
  return pool[abs(seed.hashCode()) % pool.size]
}

private fun DrawScope.drawPiece(piece: Piece, ink: Color) {
  repeat(piece.repeats) { i ->
    rotate(degrees = 360f / piece.repeats * i, pivot = piece.pivot) {
      if (piece.circle != null) {
        val c = Offset(piece.circle[0], piece.circle[1])
        val r = piece.circle[2]
        if (piece.fillAlpha > 0f) drawCircle(ink.copy(alpha = piece.fillAlpha), r, c)
        if (piece.strokeWidth > 0f) drawCircle(
          ink.copy(alpha = piece.strokeAlpha), r, c,
          style = Stroke(width = piece.strokeWidth),
        )
      }
      piece.path?.let { p ->
        if (piece.fillAlpha > 0f) drawPath(p, ink.copy(alpha = piece.fillAlpha))
        if (piece.strokeWidth > 0f) drawPath(
          p, ink.copy(alpha = piece.strokeAlpha),
          style = Stroke(
            width = piece.strokeWidth,
            cap = StrokeCap.Round, join = StrokeJoin.Round,
            pathEffect = PathEffect.cornerPathEffect(0.5f),
          ),
        )
      }
    }
  }
}

/** A creature, drawn at whatever size the modifier gives it (the 48-box
 * scales up). Same shape on the beach and on the shelves. */
@Composable
fun CreatureGlyph(
  kind: GlyphKind,
  seed: String,
  modifier: Modifier = Modifier,
  ink: Color = ShellInk,
) {
  val key = glyphKey(kind, seed)
  Canvas(modifier) {
    val s = size.minDimension / 48f
    scale(s, pivot = Offset.Zero) {
      GLYPHS.getValue(key).forEach { drawPiece(it, ink) }
    }
  }
}
