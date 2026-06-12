/*
 * Phase 5c — the review deck, on the phone.
 *
 * The shore's job in a quiet screen: due items surface one at a time. The
 * review direction IS the translation direction (§3.3): the foreign word —
 * the form you'll meet again in the world — is the question, shown whole
 * with its captured material (the photo as you saw it, the recording as you
 * heard it, the standard pronunciation on tap); the MEANING is what you
 * reach for, masked until reveal. Then self-grade; the outcome walks the
 * same Leitner ladder as the web (data layer mirrors core).
 *
 * Restraint rules carry over (DESIGN §3.1/§10.3): no due counts, no streaks,
 * no notifications — the entry is a plain button that's always there.
 */

package com.ryanqin.tideline.ui

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
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
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun ReviewScreen(viewModel: TidelineTranslateViewModel, onClose: () -> Unit) {
  var deck by remember { mutableStateOf<List<ReviewItem>?>(null) }
  var index by remember { mutableIntStateOf(0) }

  LaunchedEffect(Unit) { deck = viewModel.reviewDeck() }

  ShoreBackdrop {
  Scaffold(containerColor = Color.Transparent) { innerPadding ->
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
    modifier = Modifier
      .fillMaxSize()
      .verticalScroll(rememberScrollState()),
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
