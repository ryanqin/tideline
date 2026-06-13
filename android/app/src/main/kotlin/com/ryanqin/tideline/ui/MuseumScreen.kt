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
import androidx.compose.foundation.interaction.MutableInteractionSource
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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.VolumeUp
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
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.ryanqin.tideline.data.CardGroup
import com.ryanqin.tideline.data.LangBucket
import com.ryanqin.tideline.data.MuseumCard
import com.ryanqin.tideline.data.MuseumData
import com.ryanqin.tideline.data.ThemeGroup
import com.ryanqin.tideline.data.TranslationEntity
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MuseumScreen(viewModel: TidelineTranslateViewModel, onClose: () -> Unit) {
  var data by remember { mutableStateOf<MuseumData?>(null) }
  var lens by remember { mutableIntStateOf(0) }
  var openGroup by remember { mutableStateOf<CardGroup?>(null) }
  var openScene by remember { mutableStateOf<ThemeGroup?>(null) }
  var reloadKey by remember { mutableIntStateOf(0) }

  LaunchedEffect(reloadKey) { data = viewModel.museum() }

  // The system back walks down the dune, back to the desk — never out of
  // the app (the museum is a state, not an activity).
  androidx.activity.compose.BackHandler(onBack = onClose)

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
      Text(
        "冲上岸的一切,陈列在沙丘的货架上。按卡片、语言或主题来逛——点开一件,看它收着什么。",
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(start = 12.dp, end = 12.dp, bottom = 10.dp),
      )
      val d = data ?: return@Column
      TabRow(selectedTabIndex = lens, containerColor = MaterialTheme.colorScheme.background) {
        listOf("卡片", "语言", "主题").forEachIndexed { i, label ->
          Tab(selected = lens == i, onClick = { lens = i }, text = { Text(label) })
        }
      }
      Spacer(Modifier.height(16.dp))
      Column(Modifier.verticalScroll(rememberScrollState())) {
        when (lens) {
          0 -> CardsLens(d.cardGroups) { openGroup = it }
          1 -> LanguagesLens(d.langBuckets) { cardId ->
            openGroup = d.cardGroups.find { g -> g.cards.any { it.card.id == cardId } }
          }
          else -> ThemesLens(d.scenes) { openScene = it }
        }
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

// --- the shelves --------------------------------------------------------------

/** One shell on a shelf — the web's .shelf-shell, in Compose: the warm line
 * glyph with its first-language label beneath, no chrome (the shell IS the
 * line art on the sand). A dim shell is a word still maturing (no card yet). */
@Composable
private fun ShelfShell(
  kind: GlyphKind,
  seed: String,
  cap: String,
  dim: Boolean = false,
  onClick: (() -> Unit)? = null,
) {
  Column(
    modifier = Modifier
      .width(96.dp)
      .then(
        // No press chrome on a shelf shell — same rule as the shore.
        if (onClick != null) Modifier.clickable(
          interactionSource = remember { MutableInteractionSource() },
          indication = null,
          onClick = onClick,
        ) else Modifier
      )
      .padding(vertical = 6.dp, horizontal = 2.dp),
    horizontalAlignment = Alignment.CenterHorizontally,
  ) {
    CreatureGlyph(
      kind, seed,
      modifier = Modifier.size(62.dp),
      ink = if (dim) ShellInk.copy(alpha = 0.45f) else ShellInk,
    )
    Spacer(Modifier.height(6.dp))
    Text(
      cap,
      style = MaterialTheme.typography.bodySmall,
      color = MaterialTheme.colorScheme.onSurface.copy(alpha = if (dim) 0.6f else 1f),
      textAlign = TextAlign.Center,
      maxLines = 2,
    )
  }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ShelfRow(content: @Composable () -> Unit) {
  FlowRow(
    modifier = Modifier.fillMaxWidth(),
    horizontalArrangement = Arrangement.spacedBy(10.dp),
    verticalArrangement = Arrangement.spacedBy(14.dp),
  ) { content() }
}

// --- cards lens -------------------------------------------------------------

@Composable
private fun CardsLens(groups: List<CardGroup>, onOpen: (CardGroup) -> Unit) {
  if (groups.isEmpty()) {
    EmptyShelf("还没有卡片——一个词反复出现得够多,卡片会自己浮现;你留下值得学的,把其余的沉回去。")
    return
  }
  ShelfRow {
    groups.forEach { g ->
      ShelfShell(
        kind = GlyphKind.Card,
        seed = g.translated + (g.sourceLang ?: ""),
        cap = g.translated,
        onClick = { onOpen(g) },
      )
    }
  }
}

// --- languages lens ---------------------------------------------------------

@Composable
private fun LanguagesLens(buckets: List<LangBucket>, onOpenCard: (Long) -> Unit) {
  if (buckets.isEmpty()) {
    EmptyShelf("还没有沉淀——翻译开始重复后,会在这里按原文语言归拢。")
    return
  }
  Column(verticalArrangement = Arrangement.spacedBy(22.dp)) {
    buckets.forEach { bucket ->
      Column {
        Text(
          if (bucket.lang == null) "还认不出的语言" else Lingo.langName(bucket.lang),
          style = MaterialTheme.typography.titleMedium,
          fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.height(10.dp))
        ShelfRow {
          bucket.words.forEach { w ->
            ShelfShell(
              kind = GlyphKind.Card,
              seed = w.original,
              cap = w.original,
              dim = w.cardId == null,
              onClick = w.cardId?.let { id -> { onOpenCard(id) } },
            )
          }
        }
      }
    }
  }
}

// --- themes lens ------------------------------------------------------------

@Composable
private fun ThemesLens(scenes: List<ThemeGroup>, onOpen: (ThemeGroup) -> Unit) {
  if (scenes.isEmpty()) {
    EmptyShelf("还没有主题——相关的词攒多了,会在这里悄悄聚成一段可以回访的记忆。")
    return
  }
  ShelfRow {
    scenes.forEach { s ->
      val gist = s.members.firstNotNullOfOrNull { it.contextSnippet?.takeIf(String::isNotBlank) }
      ShelfShell(
        kind = GlyphKind.Scene,
        seed = s.sessionId,
        cap = gist ?: "${Lingo.humanTime(s.latestAt)}的场合",
        onClick = { onOpen(s) },
      )
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
    // The meaning, then which direction it came from (日→中) — the web's
    // cardGroupSheet langtag, instead of a bare English language name.
    Row(verticalAlignment = Alignment.Bottom) {
      Text(
        group.translated,
        style = MaterialTheme.typography.headlineSmall,
        fontWeight = FontWeight.SemiBold,
      )
      Spacer(Modifier.width(8.dp))
      Text(
        Lingo.langTag(group.sourceLang, group.cards.firstOrNull()?.card?.targetLang),
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(bottom = 4.dp),
      )
    }
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
    // The lived moments — the captures this word grew from (§3.2), each the
    // same row the shore and the web show: glyph, photo, "今天 · 看到的". The
    // stack of rows IS the "六次相遇", richer than a bare count.
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
      moments.forEach { m -> MomentRow(m, onPlayAudio = { viewModel.playRecording(it) }) }
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
      Lingo.humanTime(scene.latestAt) +
        (scene.sourceLang?.let { " · ${Lingo.langName(it)}" } ?: ""),
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
