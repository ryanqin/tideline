/*
 * The golden-hour sand palette, carried over hex-for-hex from the web's
 * :root block (core/src/tideline/web/static/styles.css) — one product, one
 * light. Wallpaper-derived Material You is deliberately NOT used: the shore
 * has its own weather.
 *
 * Headlines and titles take the serif voice (the web's --serif stack); body
 * text stays sans. The reveal reward is coral (--spark), wired as tertiary so
 * screens can reach it through the scheme instead of hardcoding.
 */

package com.ryanqin.tideline.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily

// Web variable → Compose color, names kept close to the CSS.
val Sand = Color(0xFFFAF4E9) // --bg: warm sand-cream ground
val SandDeep = Color(0xFFF4E9D6) // --bg-deep
val SunWhite = Color(0xFFFFFDF8) // --surface: sun-warmed white
val SandSink = Color(0xFFF8EFE0) // --surface-sink: masked tiles, wells
val Ink = Color(0xFF2D2822) // --ink: soft espresso, never pure black
val Taupe = Color(0xFF8A7C69) // --muted
val Faint = Color(0xFFB6A890) // --faint: timestamps
val Amber = Color(0xFFC2742F) // --accent: golden amber, the low sun
val AmberDeep = Color(0xFFA85F22) // --accent-deep
val AmberSoft = Color(0xFFF3E3CA) // --accent-soft
val Coral = Color(0xFFD9725A) // --spark: the reward of a reveal
val CoralSoft = Color(0xFFF8DDD1) // --spark-soft
val SandLine = Color(0xFFEBDFC8) // --border

private val TidelineColors = lightColorScheme(
  primary = Amber,
  onPrimary = SunWhite,
  primaryContainer = AmberSoft,
  onPrimaryContainer = AmberDeep,
  secondary = Taupe,
  onSecondary = SunWhite,
  secondaryContainer = SandSink,
  onSecondaryContainer = Ink,
  tertiary = Coral,
  onTertiary = SunWhite,
  tertiaryContainer = CoralSoft,
  onTertiaryContainer = Ink,
  background = Sand,
  onBackground = Ink,
  surface = SunWhite,
  onSurface = Ink,
  surfaceVariant = SandSink,
  onSurfaceVariant = Taupe,
  outline = SandLine,
  outlineVariant = SandLine,
  // Card containers stay in the sand family — without these M3 derives
  // neutral grays and the warmth breaks exactly where content lives.
  surfaceContainerLowest = SunWhite,
  surfaceContainerLow = SunWhite,
  surfaceContainer = SandSink,
  surfaceContainerHigh = SandSink,
  surfaceContainerHighest = SandDeep,
)

private val TidelineType = Typography().run {
  copy(
    displaySmall = displaySmall.copy(fontFamily = FontFamily.Serif),
    headlineLarge = headlineLarge.copy(fontFamily = FontFamily.Serif),
    headlineMedium = headlineMedium.copy(fontFamily = FontFamily.Serif),
    headlineSmall = headlineSmall.copy(fontFamily = FontFamily.Serif),
    titleLarge = titleLarge.copy(fontFamily = FontFamily.Serif),
    titleMedium = titleMedium.copy(fontFamily = FontFamily.Serif),
  )
}

@Composable
fun TidelineTheme(content: @Composable () -> Unit) {
  MaterialTheme(
    colorScheme = TidelineColors,
    typography = TidelineType,
    content = content,
  )
}
