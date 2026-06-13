/*
 * Phase 5c — the shore, on the phone.
 *
 * Not a deck: a beach. What's due washes up as creatures on the sand — a
 * word card is a piece of sea glass, a whole occasion a crab — a calm few
 * at a time, each wearing its name. Pick one up and a sheet rises with the
 * recall; self-grade and it leaves the shore, the next one washes in; when
 * the sand is clear, the tide is out. (The web shore's gesture, mirrored:
 * reviewing is beachcombing, not flashcards.)
 *
 * The review direction IS the translation direction (§3.3): the foreign
 * word — the form you'll meet again in the world — is the question, shown
 * whole with its captured material; the MEANING is what you reach for,
 * masked until reveal. The outcome walks the same Leitner ladder as the web.
 *
 * Restraint rules carry over (DESIGN §3.1/§10.3): no due counts, no streaks,
 * no notifications — the entry is a plain button that's always there.
 */

package com.ryanqin.tideline.ui

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.VolumeUp
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.ryanqin.tideline.data.CardEntity
import com.ryanqin.tideline.data.ThemeGroup
import com.ryanqin.tideline.data.TranslationEntity
import com.ryanqin.tideline.ui.theme.Amber
import com.ryanqin.tideline.ui.theme.AmberSoft
import com.ryanqin.tideline.ui.theme.Coral
import com.ryanqin.tideline.ui.theme.CoralSoft
import com.ryanqin.tideline.ui.theme.SandSink
import com.ryanqin.tideline.ui.theme.SunWhite
import com.ryanqin.tideline.ui.theme.Taupe
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

// A calm few wash up at a time — never a wall (DESIGN §10.5). Grading one
// lets the next wash in.
internal const val ASHORE = 5

/** What washes ashore this tide. Scenes come first — a scene REPRESENTS its
 * whole occasion, so a word card whose word belongs to an ashore scene FOLDS
 * into it (one occasion shouldn't fill the beach with itself); words not
 * covered by any ashore scene fill the remaining spots. A folded word isn't
 * starved: its content rides with the scene, and once the scene is graded
 * and rests, the word washes up on a later tide. No scenes due = all words,
 * as before. */
internal fun ashoreMix(items: List<ReviewItem>, limit: Int = ASHORE): List<ReviewItem> {
  // The same occasion captured on several sittings takes ONE spot per
  // tide. "Same" is containment, not equality: a 4-word shot of the package
  // is the 5-word shot minus a guarded term, so a scene whose words are a
  // subset of an ashore scene's (same language) folds into the fuller one.
  // Each keeps its own review state; only the beach refuses the rerun.
  val scenes = mutableListOf<ReviewItem.Scene>()
  for (s in items.filterIsInstance<ReviewItem.Scene>()) {
    if (scenes.size == 2) break
    val ws = s.group.members.map { it.original }.toSet()
    val rerun = scenes.any { k ->
      k.group.sourceLang == s.group.sourceLang &&
        k.group.members.map { it.original }.toSet().let { kw ->
          kw.containsAll(ws) || ws.containsAll(kw)
        }
    }
    if (!rerun) scenes.add(s)
  }
  val covered = scenes
    .flatMap { s -> s.group.members.map { it.original to it.targetLang } }
    .toSet()
  val words = items.filterIsInstance<ReviewItem.Word>()
    .filter { (it.card.original to it.card.targetLang) !in covered }
  return scenes + words.take((limit - scenes.size).coerceAtLeast(0))
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReviewScreen(viewModel: TidelineTranslateViewModel, onClose: () -> Unit) {
  var deck by remember { mutableStateOf<List<ReviewItem>?>(null) }
  var open by remember { mutableStateOf<ReviewItem?>(null) }

  // Every shell you haven't opened yet glows; opening one puts its glint
  // out (the web shore's session-scoped OPENED set).
  var opened by remember { mutableStateOf(setOf<String>()) }

  LaunchedEffect(Unit) { deck = viewModel.reviewDeck() }

  // The system back walks off the shore, back to the desk — never out of
  // the app (the shore is a state, not an activity).
  androidx.activity.compose.BackHandler(onBack = onClose)

  val dismiss = { item: ReviewItem ->
    deck = deck?.minus(item)
    open = null
  }

  ShoreScene {
  Scaffold(containerColor = Color.Transparent) { innerPadding ->
    Box(
      modifier = Modifier
        .fillMaxSize()
        .padding(innerPadding)
        // Walk back: a downward drag on the sand lowers the shore — the
        // mirror of the desk's wade-up (web closes the same way).
        .pointerInput(Unit) {
          var pulled = 0f
          detectVerticalDragGestures(
            onDragStart = { pulled = 0f },
            onVerticalDrag = { _, dy -> pulled += dy },
            onDragEnd = { if (pulled > 120f) onClose() },
          )
        },
    ) {
      IconButton(onClick = onClose, modifier = Modifier.padding(12.dp)) {
        Icon(
          Icons.AutoMirrored.Filled.ArrowBack,
          contentDescription = "Back",
          tint = ShoreInk,
        )
      }
      val items = deck
      when {
        items == null -> {}
        items.isEmpty() -> RestingShore(onClose)
        else -> Beach(ashoreMix(items), opened, onPick = {
          opened = opened + itemKey(it)
          open = it
        })
      }
    }
  }
  }

  open?.let { item ->
    ModalBottomSheet(
      onDismissRequest = { open = null },
      containerColor = MaterialTheme.colorScheme.surface,
    ) {
      Column(
        modifier = Modifier
          .verticalScroll(rememberScrollState())
          .padding(horizontal = 24.dp)
          .padding(bottom = 32.dp),
      ) {
        when (item) {
          is ReviewItem.Word -> ReviewCard(
            card = item.card,
            viewModel = viewModel,
            onGraded = { remembered ->
              viewModel.reviewCard(item.card.id, remembered)
              dismiss(item)
            },
            onSink = {
              viewModel.sinkCard(item.card.id)
              dismiss(item)
            },
          )
          is ReviewItem.Scene -> SceneCard(
            group = item.group,
            viewModel = viewModel,
            onGraded = { remembered ->
              viewModel.reviewTheme(item.group.sessionId, remembered)
              dismiss(item)
            },
          )
        }
      }
    }
  }
}

// --- the beach ---------------------------------------------------------------

private fun itemKey(item: ReviewItem): String = when (item) {
  is ReviewItem.Word -> "w${item.card.id}"
  is ReviewItem.Scene -> "s${item.group.sessionId}"
}

private fun itemLabel(item: ReviewItem): String = when (item) {
  is ReviewItem.Word -> item.card.original
  is ReviewItem.Scene ->
    item.group.members.firstNotNullOfOrNull { it.contextSnippet?.takeIf(String::isNotBlank) }
      ?: SimpleDateFormat("M月d日", Locale.getDefault()).format(Date(item.group.latestAt)) + "的场合"
}

/** The web shore's stable scatter hash — [0,1) per (key, salt). */
private fun hashFrac(key: String, salt: Int): Float {
  val h = (key + "·" + salt).hashCode()
  return ((h ushr 8) % 1000) / 1000f
}

/* Hand-laid anchor spots in the near-sand band — staggered like driftage,
 * never a row (even columns turned into a lineup on a narrow portrait
 * screen). Each item adds its own small hash jitter and tilt on top, and
 * SIZE follows NEARNESS (lower on the sand = closer = bigger), so the
 * perspective stays honest whatever washes up. */
// The lowest spot keeps clear of the system navigation strip: the anchor is
// the glyph's CENTER, and the two-line name hangs below it.
private val SHORE_SPOTS = listOf(
  0.27f to 0.710f,
  0.71f to 0.746f,
  0.21f to 0.796f,
  0.64f to 0.822f,
  0.40f to 0.856f,
)

@Composable
private fun Beach(items: List<ReviewItem>, opened: Set<String>, onPick: (ReviewItem) -> Unit) {
  BoxWithConstraints(modifier = Modifier.fillMaxSize()) {
    val w = maxWidth
    val h = maxHeight
    val minSide = if (w < h) w else h
    items.forEachIndexed { i, item ->
      val id = itemKey(item)
      val spot = SHORE_SPOTS[i % SHORE_SPOTS.size]
      val xF = (spot.first + (hashFrac(id, 1) - 0.5f) * 0.07f).coerceIn(0.12f, 0.88f)
      val yF = (spot.second + (hashFrac(id, 2) - 0.5f) * 0.025f).coerceIn(0.70f, 0.865f)
      val nearness = (yF - 0.70f) / 0.165f
      val glyphSize = minSide * (0.11f + nearness * 0.15f)
      Creature(
        item = item,
        rot = (hashFrac(id, 3) - 0.5f) * 26f,
        glyphSize = glyphSize,
        capMax = 132.dp,
        glow = id !in opened,
        modifier = Modifier.offset(
          x = w * xF - glyphSize / 2,
          y = h * yF - glyphSize / 2,
        ),
        onPick = onPick,
      )
    }
  }
}

@Composable
private fun Creature(
  item: ReviewItem,
  rot: Float,
  glyphSize: androidx.compose.ui.unit.Dp,
  capMax: androidx.compose.ui.unit.Dp,
  glow: Boolean,
  modifier: Modifier,
  onPick: (ReviewItem) -> Unit,
) {
  Column(
    modifier = modifier
      // No press chrome on a shell — the web shore has no tap highlight;
      // picking something up is its own feedback (the sheet rises).
      .clickable(
        interactionSource = remember { MutableInteractionSource() },
        indication = null,
      ) { onPick(item) }
      .padding(4.dp),
    horizontalAlignment = Alignment.CenterHorizontally,
  ) {
    Box {
      val glyphMod = Modifier.size(glyphSize).rotate(rot)
      when (item) {
        is ReviewItem.Word -> CreatureGlyph(GlyphKind.Card, item.card.original, glyphMod, ink = ShoreInk)
        is ReviewItem.Scene -> CreatureGlyph(GlyphKind.Scene, item.group.sessionId, glyphMod, ink = ShoreInk)
      }
      if (glow) {
        val spark = if (glyphSize * 0.28f < 15.dp) glyphSize * 0.28f else 15.dp
        ShellSpark(
          Modifier
            .align(Alignment.TopEnd)
            .offset(x = -(glyphSize * 0.13f), y = glyphSize * 0.17f)
            .size(spark),
        )
      }
    }
    Spacer(Modifier.height(4.dp))
    Text(
      itemLabel(item),
      style = MaterialTheme.typography.bodySmall,
      color = ShoreInk,
      textAlign = TextAlign.Center,
      maxLines = 2,
      overflow = TextOverflow.Ellipsis,
      modifier = Modifier.width(capMax),
    )
  }
}

// The web's four-point glint, path-for-path.
private val SPARK_PATH by lazy {
  androidx.compose.ui.graphics.vector.PathParser()
    .parsePathString("M12 0 Q13 11 24 12 Q13 13 12 24 Q11 13 0 12 Q11 11 12 0 Z")
    .toPath()
}

/** Two quick blinks, then a short rest, on repeat (一闪一闪) — the web's
 * shell-spark keyframes. The glint marks "you haven't opened me yet"; it
 * goes dark the moment you do. Never a paler fill, a badge, or a count. */
@Composable
private fun ShellSpark(modifier: Modifier) {
  val t = rememberInfiniteTransition(label = "shell-spark")
  val phase by t.animateFloat(
    initialValue = 0f, targetValue = 1f,
    animationSpec = infiniteRepeatable(tween(2000, easing = LinearEasing)),
    label = "phase",
  )
  val seg = { a: Float, b: Float, f: Float -> a + (b - a) * f }
  val (alpha, scale, rot) = when {
    phase < 0.15f -> (phase / 0.15f).let { Triple(seg(0f, 1f, it), seg(0.3f, 1f, it), seg(0f, 10f, it)) }
    phase < 0.30f -> ((phase - 0.15f) / 0.15f).let { Triple(seg(1f, 0.2f, it), seg(1f, 0.65f, it), seg(10f, 16f, it)) }
    phase < 0.45f -> ((phase - 0.30f) / 0.15f).let { Triple(seg(0.2f, 1f, it), seg(0.65f, 1.05f, it), seg(16f, 24f, it)) }
    phase < 0.62f -> ((phase - 0.45f) / 0.17f).let { Triple(seg(1f, 0f, it), seg(1.05f, 0.4f, it), seg(24f, 30f, it)) }
    else -> Triple(0f, 0.3f, 0f)
  }
  Canvas(
    modifier.graphicsLayer {
      this.alpha = alpha
      scaleX = scale
      scaleY = scale
      rotationZ = rot
    },
  ) {
    val s = size.minDimension / 24f
    scale(s, pivot = Offset.Zero) {
      // a soft warm halo, then the glint itself
      drawPath(SPARK_PATH, Color(0xFFFFD68C).copy(alpha = 0.6f), style = Stroke(width = 3f))
      drawPath(SPARK_PATH, Color(0xFFFFF1CF))
    }
  }
}

/** Nothing due — the tide is out. No counts, no streaks, just calm. */
@Composable
private fun RestingShore(onClose: () -> Unit) {
  Column(
    modifier = Modifier.fillMaxSize(),
    verticalArrangement = Arrangement.Center,
    horizontalAlignment = Alignment.CenterHorizontally,
  ) {
    TidelineMark(Modifier.fillMaxWidth(0.45f).height(28.dp))
    Spacer(Modifier.height(16.dp))
    Text("潮水退了", style = MaterialTheme.typography.headlineSmall, color = ShoreInk)
    Spacer(Modifier.height(8.dp))
    Text(
      "现在没有等你的词。去走走,翻译点什么。",
      style = MaterialTheme.typography.bodyMedium,
      color = ShoreInk.copy(alpha = 0.75f),
    )
    Spacer(Modifier.height(20.dp))
    OutlinedButton(onClick = onClose) { Text("回去", color = ShoreInk) }
  }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ReviewCard(
  card: CardEntity,
  viewModel: TidelineTranslateViewModel,
  onGraded: (Boolean) -> Unit,
  onSink: () -> Unit,
) {
  var moments by remember(card.id) { mutableStateOf<List<TranslationEntity>>(emptyList()) }
  var revealed by remember(card.id) { mutableStateOf(false) }
  LaunchedEffect(card.id) { moments = viewModel.cardMoments(card.id) }

  // The card mirrors core's schema (no language column); its source language
  // lives on the moments it grew from.
  val sourceLang = moments.firstNotNullOfOrNull { it.sourceLang }

  Column(
    modifier = Modifier.fillMaxWidth(),
    verticalArrangement = Arrangement.spacedBy(16.dp),
  ) {
    // The card head, one line like the web: the word as met → its meaning
    // (masked — the thing to reach for) (日→中) 🔊. The standard pronunciation
    // belongs to the SHOWN word, so it can't leak the masked meaning.
    FlowRow(
      horizontalArrangement = Arrangement.spacedBy(8.dp),
      itemVerticalAlignment = Alignment.CenterVertically,
    ) {
      Text(
        "${card.original} →",
        style = MaterialTheme.typography.headlineSmall,
        fontWeight = FontWeight.SemiBold,
      )
      MaskedMeaning(
        text = card.translated,
        revealed = revealed,
        onReveal = { revealed = true },
        style = MaterialTheme.typography.headlineSmall,
      )
      Text(
        Lingo.langTag(sourceLang, card.targetLang),
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
      )
      IconButton(onClick = { viewModel.speak(card.original, sourceLang) }) {
        Icon(Icons.AutoMirrored.Filled.VolumeUp, contentDescription = "Standard pronunciation",
          tint = MaterialTheme.colorScheme.primary)
      }
    }

    // The lived moments — the captures this word grew from (§3.2), each the
    // same row the museum and the web show.
    if (moments.isNotEmpty()) {
      Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        moments.forEach { m -> MomentRow(m, onPlayAudio = { viewModel.playRecording(it) }) }
      }
    }

    // Grade is always here (the web's review-grade is never gated behind a
    // reveal): reach for the meaning, reveal to check, then say honestly
    // whether it came — that outcome walks the Leitner ladder (§10.3).
    Row(
      modifier = Modifier.fillMaxWidth(),
      horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
      OutlinedButton(onClick = { onGraded(false) }, modifier = Modifier.weight(1f)) {
        Text("没想起来")
      }
      Button(onClick = { onGraded(true) }, modifier = Modifier.weight(1f)) {
        Text("想起来了")
      }
    }
    // The opt-out: a quiet way to say "this one isn't worth keeping" — sunk
    // cards never resurface (the user curates by subtraction).
    TextButton(
      onClick = onSink,
      modifier = Modifier.align(Alignment.CenterHorizontally),
    ) {
      Text(
        "这个词不用记 — 沉底",
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
      )
    }
    Spacer(Modifier.height(24.dp))
  }
}

/** One concept inside a scene: synonyms folded onto one line (the scene is
 * single-language, so same rendering = same concept — the web museum's
 * grouping, mirrored). */
private data class SceneLine(
  val translated: String,
  val originals: List<String>,
  val audioId: Long?,
  val lang: String?,
)

/** A whole occasion recalled as one: the scene gist (captured with it) and
 * the photo set the stage, each foreign word shown as met — its meaning the
 * masked thing to reach for. One self-grade for the night walks the shared
 * Leitner ladder. */
@Composable
private fun SceneCard(
  group: ThemeGroup,
  viewModel: TidelineTranslateViewModel,
  onGraded: (Boolean) -> Unit,
) {
  var photo by remember(group.sessionId) { mutableStateOf<Bitmap?>(null) }
  var revealed by remember(group.sessionId) { mutableStateOf(setOf<String>()) }

  val photoMember = group.members.firstOrNull { it.hasImage }
  LaunchedEffect(group.sessionId) {
    photo = photoMember?.let { m ->
      viewModel.photoFor(m.id)?.let { BitmapFactory.decodeByteArray(it, 0, it.size) }
    }
  }

  // The episodic title is the scene gist the model reported at capture time;
  // a session without one falls back to its date. B6 naming waits for the
  // night-watch model — the gist is the engineering that's already there.
  val gist = group.members.firstNotNullOfOrNull { it.contextSnippet?.takeIf(String::isNotBlank) }
  val day = remember(group.sessionId) {
    SimpleDateFormat("M月d日", Locale.getDefault()).format(Date(group.latestAt))
  }
  val lines = remember(group.sessionId) {
    group.members.groupBy { it.translated }.map { (translated, ms) ->
      SceneLine(
        translated = translated,
        originals = ms.map { it.original }.distinct(),
        audioId = ms.firstOrNull { it.hasAudio }?.id,
        lang = ms.firstNotNullOfOrNull { it.sourceLang },
      )
    }
  }

  Column(
    modifier = Modifier.fillMaxWidth(),
    verticalArrangement = Arrangement.spacedBy(16.dp),
  ) {
    // The occasion is the question.
    Text(
      text = gist ?: "那一次的场合",
      style = MaterialTheme.typography.headlineSmall,
      fontWeight = FontWeight.SemiBold,
    )
    Text(
      text = "$day · 那时遇到的词,还想得起来吗",
      style = MaterialTheme.typography.bodySmall,
      color = MaterialTheme.colorScheme.onSurfaceVariant,
    )

    // The scene photo, whole — the occasion as you saw it.
    photo?.let { CapturePhoto(it) }

    // "Reveal all / mask again" flips the whole night at once (the web's
    // theme reveal-all) — for when you'd rather browse than be quizzed.
    val allKeys = remember(lines) { lines.map { it.translated }.toSet() }
    val anyHidden = revealed.size < allKeys.size
    TextButton(
      onClick = { revealed = if (anyHidden) allKeys else emptySet() },
      modifier = Modifier.align(Alignment.End),
    ) {
      Text(
        if (anyHidden) "全部揭开" else "重新遮住",
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
      )
    }

    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
      lines.forEach { line ->
        SceneLineRow(
          line = line,
          revealed = line.translated in revealed,
          onReveal = { revealed = revealed + line.translated },
          viewModel = viewModel,
        )
      }
    }

    Row(
      modifier = Modifier.fillMaxWidth(),
      horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
      OutlinedButton(onClick = { onGraded(false) }, modifier = Modifier.weight(1f)) {
        Text("没想起来")
      }
      Button(onClick = { onGraded(true) }, modifier = Modifier.weight(1f)) {
        Text("想起来了")
      }
    }
    Spacer(Modifier.height(24.dp))
  }
}

/** The foreign word shown as met (its pronunciation and recording on tap —
 * they're part of the question), the MEANING a warm patch until tapped. */
@Composable
private fun SceneLineRow(
  line: SceneLine,
  revealed: Boolean,
  onReveal: () -> Unit,
  viewModel: TidelineTranslateViewModel,
) {
  Row(
    modifier = Modifier.fillMaxWidth(),
    verticalAlignment = Alignment.CenterVertically,
  ) {
    Column(modifier = Modifier.weight(1f)) {
      Text(line.originals.joinToString(" / "), style = MaterialTheme.typography.titleMedium)
      // The foreign word is shown; its meaning waits behind the patch (shared
      // with the word card — one masking, two surfaces).
      MaskedMeaning(text = line.translated, revealed = revealed, onReveal = onReveal)
    }
    line.audioId?.let { id ->
      IconButton(onClick = { viewModel.playRecordingFor(id) }) {
        Icon(Icons.Default.PlayArrow, contentDescription = "播放当时的原声")
      }
    }
    IconButton(onClick = { viewModel.speak(line.originals.first(), line.lang) }) {
      Icon(
        Icons.AutoMirrored.Filled.VolumeUp,
        contentDescription = "Standard pronunciation",
        tint = MaterialTheme.colorScheme.primary,
      )
    }
  }
}

// CapturePhoto (the whole, unmasked capture) lives in CapturePhoto.kt now —
// shared with the museum.
