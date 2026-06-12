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
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
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
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
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
private const val ASHORE = 5

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReviewScreen(viewModel: TidelineTranslateViewModel, onClose: () -> Unit) {
  var deck by remember { mutableStateOf<List<ReviewItem>?>(null) }
  var open by remember { mutableStateOf<ReviewItem?>(null) }

  LaunchedEffect(Unit) { deck = viewModel.reviewDeck() }

  // The system back walks off the shore, back to the desk — never out of
  // the app (the shore is a state, not an activity).
  androidx.activity.compose.BackHandler(onBack = onClose)

  val dismiss = { item: ReviewItem ->
    deck = deck?.minus(item)
    open = null
  }

  ShoreBackdrop {
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
        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
      }
      val items = deck
      when {
        items == null -> {}
        items.isEmpty() -> RestingShore(onClose)
        else -> {
          // Both kinds share the sand: words get a guaranteed share, scenes
          // fill the rest (the web shore's mix, simplified). Each grade
          // re-deals, so the next thing washes in.
          val words = items.filterIsInstance<ReviewItem.Word>()
          val scenes = items.filterIsInstance<ReviewItem.Scene>()
          val ashoreWords = words.take(if (scenes.isEmpty()) ASHORE else 3)
          val ashore = ashoreWords + scenes.take(ASHORE - ashoreWords.size)
          Beach(ashore, onPick = { open = it })
        }
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

/** The sand with what washed up on it: each due item a creature at its own
 * stable spot (hashed, so the beach doesn't reshuffle underfoot), wearing
 * its name. Two loose columns, a little scatter — driftage, not a grid. */
@Composable
private fun Beach(items: List<ReviewItem>, onPick: (ReviewItem) -> Unit) {
  BoxWithConstraints(modifier = Modifier.fillMaxSize()) {
    val w = maxWidth
    val h = maxHeight
    items.forEachIndexed { i, item ->
      val hash = itemKey(item).hashCode()
      val col = i % 2
      val row = i / 2
      val xFrac = (if (col == 0) 0.10f else 0.52f) + ((hash ushr 4) % 100) / 100f * 0.08f
      val yFrac = 0.16f + row * 0.20f + ((hash ushr 12) % 100) / 100f * 0.05f
      Creature(
        item = item,
        hash = hash,
        modifier = Modifier.offset(x = w * xFrac, y = h * yFrac),
        onPick = onPick,
      )
    }
  }
}

@Composable
private fun Creature(
  item: ReviewItem,
  hash: Int,
  modifier: Modifier,
  onPick: (ReviewItem) -> Unit,
) {
  // The web shore tilts each creature a few degrees — driftage, not a grid.
  val rot = ((hash ushr 16) % 25 - 12).toFloat()
  Column(
    modifier = modifier
      .width(150.dp)
      .clickable { onPick(item) }
      .padding(6.dp),
    horizontalAlignment = Alignment.CenterHorizontally,
  ) {
    val glyphMod = Modifier.size(62.dp).rotate(rot)
    when (item) {
      is ReviewItem.Word -> CreatureGlyph(GlyphKind.Card, item.card.original, glyphMod)
      is ReviewItem.Scene -> CreatureGlyph(GlyphKind.Scene, item.group.sessionId, glyphMod)
    }
    Spacer(Modifier.height(6.dp))
    Text(
      itemLabel(item),
      style = MaterialTheme.typography.bodySmall,
      color = MaterialTheme.colorScheme.onSurface,
      textAlign = TextAlign.Center,
      maxLines = 2,
    )
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
    Text("潮水退了", style = MaterialTheme.typography.headlineSmall)
    Spacer(Modifier.height(8.dp))
    Text(
      "现在没有等你的词。去走走,翻译点什么。",
      style = MaterialTheme.typography.bodyMedium,
      color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    Spacer(Modifier.height(20.dp))
    OutlinedButton(onClick = onClose) { Text("回去") }
  }
}

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

  val photoMoment = moments.firstOrNull { it.sourceImage != null }
  val audioMoments = moments.filter { it.sourceAudio != null }

  Column(
    modifier = Modifier.fillMaxWidth(),
    verticalArrangement = Arrangement.spacedBy(16.dp),
  ) {
    // The word as met is the question — the form you'll meet again in the
    // world. Its standard pronunciation is part of the question, on tap.
    Row(verticalAlignment = Alignment.CenterVertically) {
      Text(
        text = card.original,
        style = MaterialTheme.typography.headlineMedium,
        fontWeight = FontWeight.SemiBold,
        modifier = Modifier.weight(1f, fill = false),
      )
      IconButton(onClick = { viewModel.speak(card.original, photoMoment?.sourceLang ?: audioMoments.firstOrNull()?.sourceLang) }) {
        Icon(Icons.AutoMirrored.Filled.VolumeUp, contentDescription = "Standard pronunciation",
          tint = MaterialTheme.colorScheme.primary)
      }
    }

    // The lived material rounds out the question: the photo whole, as you
    // saw it; the recording playable, as you heard it.
    photoMoment?.sourceImage?.let { bytes ->
      val bitmap = remember(card.id) { BitmapFactory.decodeByteArray(bytes, 0, bytes.size) }
      if (bitmap != null) {
        CapturePhoto(bitmap)
      }
    }
    audioMoments.take(2).forEach { m ->
      OutlinedButton(onClick = { viewModel.playRecording(m.sourceAudio!!) }) {
        Icon(Icons.Default.PlayArrow, contentDescription = null, modifier = Modifier.size(18.dp))
        Spacer(Modifier.size(6.dp))
        Text("播放当时的原声")
      }
    }
    photoMoment?.contextSnippet?.let {
      Text(it, style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant)
    }

    if (!revealed) {
      Button(onClick = { revealed = true }, modifier = Modifier.fillMaxWidth()) {
        Text("想起来了再揭开")
      }
    } else {
      // The meaning is the reveal, wearing coral — the web's --spark reward.
      Text(
        text = card.translated,
        style = MaterialTheme.typography.headlineSmall,
        color = MaterialTheme.colorScheme.tertiary,
      )
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
      // The opt-out: a quiet way to say "this one isn't worth keeping" —
      // sunk cards never resurface (the user curates by subtraction).
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
      Box(
        modifier = Modifier
          .clip(RoundedCornerShape(6.dp))
          .background(
            if (revealed) Color.Transparent
            else MaterialTheme.colorScheme.surfaceVariant,
          )
          // A sand hairline so the patch reads as tappable on the sand ground.
          .then(
            if (revealed) Modifier
            else Modifier.border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(6.dp))
          )
          .clickable(enabled = !revealed, onClick = onReveal)
          .padding(horizontal = 6.dp, vertical = 2.dp),
      ) {
        // Transparent until revealed: the patch keeps the meaning's own size.
        // The revealed meaning wears coral — the web's --spark reveal reward.
        Text(
          text = line.translated,
          style = MaterialTheme.typography.bodyLarge,
          color = if (revealed) MaterialTheme.colorScheme.tertiary else Color.Transparent,
        )
      }
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
