/*
 * Phase 5c — the review deck, on the phone.
 *
 * The shore's job in a quiet screen: due cards surface one at a time — the
 * meaning shown, the word masked, the captured material as the cue (the
 * photo with the word's spot covered, the recording playable). Reveal, hear
 * the standard pronunciation if wanted, then self-grade; the outcome walks
 * the same Leitner ladder as the web (data layer mirrors core).
 *
 * Restraint rules carry over (DESIGN §3.1/§10.3): no due counts, no streaks,
 * no notifications — the entry is a plain button that's always there.
 */

package com.ryanqin.tideline.ui

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.VolumeUp
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.ryanqin.tideline.data.CardEntity
import com.ryanqin.tideline.data.ThemeGroup
import com.ryanqin.tideline.data.TranslationEntity
import org.json.JSONArray
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** "[x0,y0,x1,y1]" normalized → floats, or null when absent/malformed. */
private fun parseRegion(raw: String?): FloatArray? {
  if (raw.isNullOrBlank()) return null
  return try {
    val arr = JSONArray(raw)
    if (arr.length() != 4) null
    else FloatArray(4) { arr.getDouble(it).toFloat() }
  } catch (_: Throwable) {
    null
  }
}

@Composable
fun ReviewScreen(viewModel: TidelineTranslateViewModel, onClose: () -> Unit) {
  var deck by remember { mutableStateOf<List<ReviewItem>?>(null) }
  var index by remember { mutableIntStateOf(0) }

  LaunchedEffect(Unit) { deck = viewModel.reviewDeck() }

  Scaffold { innerPadding ->
    Column(
      modifier = Modifier
        .fillMaxSize()
        .padding(innerPadding)
        .padding(horizontal = 24.dp, vertical = 8.dp),
    ) {
      IconButton(onClick = onClose) {
        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
      }
      val items = deck
      when {
        items == null -> {}
        index >= items.size -> RestingShore(onClose)
        else -> when (val item = items[index]) {
          is ReviewItem.Word -> ReviewCard(
            card = item.card,
            viewModel = viewModel,
            onGraded = { remembered ->
              viewModel.reviewCard(item.card.id, remembered)
              index += 1
            },
            onSink = {
              viewModel.sinkCard(item.card.id)
              index += 1
            },
          )
          is ReviewItem.Scene -> SceneCard(
            group = item.group,
            viewModel = viewModel,
            onGraded = { remembered ->
              viewModel.reviewTheme(item.group.sessionId, remembered)
              index += 1
            },
          )
        }
      }
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
    modifier = Modifier
      .fillMaxSize()
      .verticalScroll(rememberScrollState()),
    verticalArrangement = Arrangement.spacedBy(16.dp),
  ) {
    // The meaning is the question.
    Text(
      text = card.translated,
      style = MaterialTheme.typography.headlineMedium,
      fontWeight = FontWeight.SemiBold,
    )

    // The lived material is the cue: the photo with the word's own spot
    // covered until reveal; the recording playable from the start (听写).
    photoMoment?.sourceImage?.let { bytes ->
      val bitmap = remember(card.id) { BitmapFactory.decodeByteArray(bytes, 0, bytes.size) }
      if (bitmap != null) {
        CapturePhoto(bitmap, parseRegion(photoMoment.sourceRegion), masked = !revealed)
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
      Row(verticalAlignment = Alignment.CenterVertically) {
        Text(
          text = card.original,
          style = MaterialTheme.typography.headlineSmall,
          color = MaterialTheme.colorScheme.primary,
          modifier = Modifier.weight(1f, fill = false),
        )
        // The standard pronunciation, AFTER recall — the dictation order.
        IconButton(onClick = { viewModel.speak(card.original, photoMoment?.sourceLang ?: audioMoments.firstOrNull()?.sourceLang) }) {
          Icon(Icons.AutoMirrored.Filled.VolumeUp, contentDescription = "Standard pronunciation",
            tint = MaterialTheme.colorScheme.primary)
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

/** A whole occasion recalled as one: the scene gist (captured with it) is the
 * question, the photo is the cue, each meaning a masked word to reach for.
 * One self-grade for the night walks the shared Leitner ladder. */
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
    modifier = Modifier
      .fillMaxSize()
      .verticalScroll(rememberScrollState()),
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

    // The scene photo is the cue, whole and unmasked — look, then reach.
    photo?.let { bitmap ->
      Box(modifier = Modifier.fillMaxWidth().aspectRatio(bitmap.width.toFloat() / bitmap.height)) {
        Image(
          bitmap = bitmap.asImageBitmap(),
          contentDescription = null,
          modifier = Modifier.fillMaxSize(),
          contentScale = ContentScale.Fit,
        )
      }
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

/** The meaning shown, the word a warm patch until tapped — then the standard
 * pronunciation (dictation order); the recording, when there is one, is a cue
 * playable from the start. */
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
      Text(line.translated, style = MaterialTheme.typography.titleMedium)
      Box(
        modifier = Modifier
          .clip(RoundedCornerShape(6.dp))
          .background(
            if (revealed) Color.Transparent
            else MaterialTheme.colorScheme.surfaceVariant,
          )
          .clickable(enabled = !revealed, onClick = onReveal)
          .padding(horizontal = 6.dp, vertical = 2.dp),
      ) {
        // Transparent until revealed: the patch keeps the word's own size.
        Text(
          text = line.originals.joinToString(" / "),
          style = MaterialTheme.typography.bodyLarge,
          color = if (revealed) MaterialTheme.colorScheme.primary else Color.Transparent,
        )
      }
    }
    line.audioId?.let { id ->
      IconButton(onClick = { viewModel.playRecordingFor(id) }) {
        Icon(Icons.Default.PlayArrow, contentDescription = "播放当时的原声")
      }
    }
    if (revealed) {
      IconButton(onClick = { viewModel.speak(line.originals.first(), line.lang) }) {
        Icon(
          Icons.AutoMirrored.Filled.VolumeUp,
          contentDescription = "Standard pronunciation",
          tint = MaterialTheme.colorScheme.primary,
        )
      }
    }
  }
}

/** The capture, uncropped (the normalized region must map 1:1), with a warm
 * patch over the word's own pixels until the reveal. */
@Composable
private fun CapturePhoto(bitmap: Bitmap, region: FloatArray?, masked: Boolean) {
  BoxWithConstraints(modifier = Modifier.fillMaxWidth()) {
    val aspect = bitmap.width.toFloat() / bitmap.height.toFloat()
    val w = maxWidth
    val h = maxWidth / aspect
    Box(modifier = Modifier.fillMaxWidth().aspectRatio(aspect)) {
      Image(
        bitmap = bitmap.asImageBitmap(),
        contentDescription = null,
        modifier = Modifier.fillMaxSize(),
        contentScale = ContentScale.Fit,
      )
      if (masked && region != null) {
        Box(
          modifier = Modifier
            .offset(x = w * region[0], y = h * region[1])
            .size(width = w * (region[2] - region[0]), height = h * (region[3] - region[1]))
            .background(
              MaterialTheme.colorScheme.surfaceVariant,
              RoundedCornerShape(6.dp),
            ),
        )
      }
    }
  }
}
