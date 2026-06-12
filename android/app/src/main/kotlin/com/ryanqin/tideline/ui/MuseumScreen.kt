/*
 * The museum, on the phone — browse what washed up, through the web's three
 * lenses (cards / languages / themes). Browsing is not a quiz (DESIGN §10.3):
 * nothing here is masked or graded; the shore (ReviewScreen) is where you
 * reach for meanings. Tap a shelf tile and a sheet rises with the words and
 * their lived moments (§3.2 — "六次相遇", never a bare count), each word
 * sinkable (the opt-out curation).
 */

package com.ryanqin.tideline.ui

import android.graphics.BitmapFactory
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.VolumeUp
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.ryanqin.tideline.data.CardGroup
import com.ryanqin.tideline.data.LangBucket
import com.ryanqin.tideline.data.MuseumCard
import com.ryanqin.tideline.data.MuseumData
import com.ryanqin.tideline.data.ThemeGroup
import com.ryanqin.tideline.data.TranslationEntity
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private val DAY_FMT = SimpleDateFormat("M月d日", Locale.getDefault())

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MuseumScreen(viewModel: TidelineTranslateViewModel, onClose: () -> Unit) {
  var data by remember { mutableStateOf<MuseumData?>(null) }
  var lens by remember { mutableIntStateOf(0) }
  var openGroup by remember { mutableStateOf<CardGroup?>(null) }
  var openScene by remember { mutableStateOf<ThemeGroup?>(null) }
  var reloadKey by remember { mutableIntStateOf(0) }

  LaunchedEffect(reloadKey) { data = viewModel.museum() }

  Scaffold { innerPadding ->
    Column(
      modifier = Modifier
        .fillMaxSize()
        .padding(innerPadding)
        .padding(horizontal = 20.dp, vertical = 8.dp),
    ) {
      Row(verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = onClose) {
          Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
        }
        Text(
          "陈列馆",
          style = MaterialTheme.typography.headlineSmall,
          fontWeight = FontWeight.SemiBold,
        )
      }
      val d = data ?: return@Column
      TabRow(selectedTabIndex = lens, containerColor = MaterialTheme.colorScheme.background) {
        listOf("卡片", "语言", "主题").forEachIndexed { i, label ->
          Tab(selected = lens == i, onClick = { lens = i }, text = { Text(label) })
        }
      }
      Spacer(Modifier.height(12.dp))
      when (lens) {
        0 -> CardsLens(d.cardGroups) { openGroup = it }
        1 -> LanguagesLens(d.langBuckets) { cardId ->
          openGroup = d.cardGroups.find { g -> g.cards.any { it.card.id == cardId } }
        }
        else -> ThemesLens(d.scenes) { openScene = it }
      }
    }
  }

  openGroup?.let { group ->
    ModalBottomSheet(
      onDismissRequest = { openGroup = null },
      containerColor = MaterialTheme.colorScheme.surface,
    ) {
      CardGroupSheet(group, viewModel, onSunk = { openGroup = null; reloadKey += 1 })
    }
  }
  openScene?.let { scene ->
    ModalBottomSheet(
      onDismissRequest = { openScene = null },
      containerColor = MaterialTheme.colorScheme.surface,
    ) {
      SceneBrowseSheet(scene, viewModel)
    }
  }
}

/** Quiet empty state — the museum before anything has matured. */
@Composable
private fun EmptyShelf(text: String) {
  Column(
    modifier = Modifier.fillMaxWidth().padding(vertical = 48.dp),
    horizontalAlignment = Alignment.CenterHorizontally,
  ) {
    Text(text, style = MaterialTheme.typography.bodyMedium,
      color = MaterialTheme.colorScheme.onSurfaceVariant)
  }
}

// --- cards lens -------------------------------------------------------------

@Composable
private fun CardsLens(groups: List<CardGroup>, onOpen: (CardGroup) -> Unit) {
  if (groups.isEmpty()) { EmptyShelf("还没有词卡 — 翻译累积后会自己浮现。"); return }
  LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
    items(groups, key = { it.translated + (it.sourceLang ?: "") }) { g ->
      Surface(
        onClick = { onOpen(g) },
        shape = RoundedCornerShape(14.dp),
        color = MaterialTheme.colorScheme.surface,
        modifier = Modifier.fillMaxWidth(),
      ) {
        Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) {
          Text(
            g.cards.joinToString(" / ") { it.card.original },
            style = MaterialTheme.typography.titleMedium,
          )
          Text(
            g.translated + (g.sourceLang?.let { "  ·  $it" } ?: ""),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
          )
        }
      }
    }
  }
}

// --- languages lens ---------------------------------------------------------

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun LanguagesLens(buckets: List<LangBucket>, onOpenCard: (Long) -> Unit) {
  if (buckets.isEmpty()) { EmptyShelf("还没有遇到外语 — 去翻译点什么。"); return }
  LazyColumn(verticalArrangement = Arrangement.spacedBy(18.dp)) {
    items(buckets, key = { it.lang ?: "?" }) { bucket ->
      Column {
        Text(
          bucket.lang ?: "还认不出的语言",
          style = MaterialTheme.typography.titleMedium,
          fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.height(8.dp))
        FlowRow(
          horizontalArrangement = Arrangement.spacedBy(8.dp),
          verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
          bucket.words.forEach { w ->
            val matured = w.cardId != null
            Surface(
              shape = RoundedCornerShape(999.dp),
              color = if (matured) MaterialTheme.colorScheme.surface
                else MaterialTheme.colorScheme.surfaceVariant,
              modifier = if (matured)
                Modifier.clickable { onOpenCard(w.cardId!!) }
              else Modifier,
            ) {
              Row(
                Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically,
              ) {
                Text(w.original, style = MaterialTheme.typography.bodyMedium)
                if (w.count > 1) {
                  Text(
                    "  ·${w.count}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                  )
                }
              }
            }
          }
        }
      }
    }
  }
}

// --- themes lens ------------------------------------------------------------

@Composable
private fun ThemesLens(scenes: List<ThemeGroup>, onOpen: (ThemeGroup) -> Unit) {
  if (scenes.isEmpty()) { EmptyShelf("还没有成形的场合 — 一次出门多翻几个词,它们会聚在一起。"); return }
  LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
    items(scenes, key = { it.sessionId + (it.sourceLang ?: "") }) { s ->
      val gist = s.members.firstNotNullOfOrNull { it.contextSnippet?.takeIf(String::isNotBlank) }
      Surface(
        onClick = { onOpen(s) },
        shape = RoundedCornerShape(14.dp),
        color = MaterialTheme.colorScheme.surface,
        modifier = Modifier.fillMaxWidth(),
      ) {
        Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) {
          Text(
            gist ?: "${DAY_FMT.format(Date(s.latestAt))}的场合",
            style = MaterialTheme.typography.titleMedium,
          )
          Text(
            s.members.map { it.original }.distinct().joinToString(" · "),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            maxLines = 2,
          )
        }
      }
    }
  }
}

// --- sheets -----------------------------------------------------------------

/** A meaning's shelf: every word that carried it, each with its lived
 * moments and its own sink (the grouping is how the museum browses; each is
 * still an independent card). */
@Composable
private fun CardGroupSheet(
  group: CardGroup,
  viewModel: TidelineTranslateViewModel,
  onSunk: () -> Unit,
) {
  Column(Modifier.padding(horizontal = 24.dp).padding(bottom = 32.dp)) {
    Text(
      group.translated + (group.sourceLang?.let { "  ·  $it" } ?: ""),
      style = MaterialTheme.typography.headlineSmall,
      fontWeight = FontWeight.SemiBold,
    )
    Spacer(Modifier.height(8.dp))
    group.cards.forEach { mc ->
      WordBlock(mc, viewModel, onSunk)
    }
  }
}

@Composable
private fun WordBlock(
  mc: MuseumCard,
  viewModel: TidelineTranslateViewModel,
  onSunk: () -> Unit,
) {
  var moments by remember(mc.card.id) { mutableStateOf<List<TranslationEntity>>(emptyList()) }
  LaunchedEffect(mc.card.id) { moments = viewModel.cardMoments(mc.card.id) }

  Column(Modifier.padding(vertical = 10.dp)) {
    Row(verticalAlignment = Alignment.CenterVertically) {
      Text(
        mc.card.original,
        style = MaterialTheme.typography.titleLarge,
        modifier = Modifier.weight(1f, fill = false),
      )
      IconButton(onClick = { viewModel.speak(mc.card.original, mc.sourceLang) }) {
        Icon(Icons.AutoMirrored.Filled.VolumeUp, contentDescription = "Standard pronunciation",
          tint = MaterialTheme.colorScheme.primary)
      }
      Spacer(Modifier.weight(1f))
      TextButton(onClick = { viewModel.sinkCard(mc.card.id); onSunk() }) {
        Text("沉底", style = MaterialTheme.typography.bodySmall,
          color = MaterialTheme.colorScheme.onSurfaceVariant)
      }
    }
    // The lived moments — the captures this word grew from (§3.2).
    val photoMoment = moments.firstOrNull { it.sourceImage != null }
    photoMoment?.sourceImage?.let { bytes ->
      val bitmap = remember(mc.card.id) { BitmapFactory.decodeByteArray(bytes, 0, bytes.size) }
      if (bitmap != null) CapturePhoto(bitmap)
    }
    photoMoment?.contextSnippet?.let {
      Spacer(Modifier.height(6.dp))
      Text(it, style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    moments.filter { it.sourceAudio != null }.take(1).forEach { m ->
      TextButton(onClick = { viewModel.playRecordingFor(m.id) }) {
        Icon(Icons.Default.PlayArrow, contentDescription = null,
          modifier = Modifier.padding(end = 4.dp))
        Text("播放当时的原声", style = MaterialTheme.typography.bodySmall)
      }
    }
    if (moments.isNotEmpty()) {
      Text(
        "${moments.size} 次相遇 · 最近 ${DAY_FMT.format(Date(moments.last().createdAt))}",
        style = MaterialTheme.typography.labelSmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
      )
    }
  }
}

/** An occasion, browsed: the photo and every word with its meaning in the
 * open — recall lives on the shore, not here. */
@Composable
private fun SceneBrowseSheet(scene: ThemeGroup, viewModel: TidelineTranslateViewModel) {
  var photo by remember(scene.sessionId) { mutableStateOf<android.graphics.Bitmap?>(null) }
  val photoMember = scene.members.firstOrNull { it.hasImage }
  LaunchedEffect(scene.sessionId) {
    photo = photoMember?.let { m ->
      viewModel.photoFor(m.id)?.let { BitmapFactory.decodeByteArray(it, 0, it.size) }
    }
  }
  val gist = scene.members.firstNotNullOfOrNull { it.contextSnippet?.takeIf(String::isNotBlank) }

  Column(Modifier.padding(horizontal = 24.dp).padding(bottom = 32.dp)) {
    Text(
      gist ?: "那一次的场合",
      style = MaterialTheme.typography.headlineSmall,
      fontWeight = FontWeight.SemiBold,
    )
    Text(
      DAY_FMT.format(Date(scene.latestAt)) + (scene.sourceLang?.let { " · $it" } ?: ""),
      style = MaterialTheme.typography.bodySmall,
      color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    Spacer(Modifier.height(10.dp))
    photo?.let { CapturePhoto(it) }
    Spacer(Modifier.height(6.dp))
    scene.members.groupBy { it.translated }.forEach { (translated, ms) ->
      Row(
        Modifier.fillMaxWidth().padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Column(Modifier.weight(1f)) {
          Text(ms.map { it.original }.distinct().joinToString(" / "),
            style = MaterialTheme.typography.titleMedium)
          Text(translated, style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        IconButton(onClick = { viewModel.speak(ms.first().original, ms.first().sourceLang) }) {
          Icon(Icons.AutoMirrored.Filled.VolumeUp, contentDescription = "Standard pronunciation",
            tint = MaterialTheme.colorScheme.primary)
        }
      }
    }
  }
}
