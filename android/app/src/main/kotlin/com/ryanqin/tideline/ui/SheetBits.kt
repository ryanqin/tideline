/*
 * Shared sheet bits — the web creature-sheet's pieces, carried to the phone so
 * the shore (ReviewScreen) and the museum (MuseumScreen) render moments and
 * masked meanings the SAME way (DESIGN §10.5: one visual language, no drift).
 * Mirrors sheet.js: momentRow (a lived capture — glyph, photo, context, the
 * human "今天 · 看到的") and the masked-meaning patch (the review direction IS
 * the translation direction §3.3: the word is shown, the meaning is the thing
 * you reach for, covered until tapped).
 */

package com.ryanqin.tideline.ui

import android.graphics.BitmapFactory
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.outlined.Edit
import androidx.compose.material.icons.outlined.GraphicEq
import androidx.compose.material.icons.outlined.Image
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.dp
import com.ryanqin.tideline.data.TranslationEntity

/** How a moment was caught, drawn small and quiet — a photo seen, a voice
 * heard, a phrase looked up (the web's SRC_GLYPH). */
private fun momentSrcIcon(source: String?): ImageVector = when (source) {
  "image" -> Icons.Outlined.Image
  "audio" -> Icons.Outlined.GraphicEq
  else -> Icons.Outlined.Edit
}

/** One lived moment in the stack behind a card (DESIGN §3.2), mirroring the
 * web's momentRow: a capture with material leads with it — the photo whole, as
 * seen — then its quiet "今天 · 看到的"; a silent one keeps only that line, so a
 * card of silent moments stays a tidy log. The recording behind a heard moment
 * is playable on tap. */
@Composable
internal fun MomentRow(moment: TranslationEntity, onPlayAudio: (ByteArray) -> Unit) {
  val photo = moment.sourceImage?.let { bytes ->
    remember(moment.id) { BitmapFactory.decodeByteArray(bytes, 0, bytes.size) }
  }
  val meta = listOf(Lingo.humanTime(moment.createdAt), Lingo.srcLabel(moment.source))
    .joinToString(" · ")

  Column(
    modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
    verticalArrangement = Arrangement.spacedBy(6.dp),
  ) {
    photo?.let { CapturePhoto(it) }
    moment.contextSnippet?.takeIf { it.isNotBlank() }?.let {
      Text(
        it,
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
      )
    }
    Row(
      verticalAlignment = Alignment.CenterVertically,
      horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
      Icon(
        momentSrcIcon(moment.source),
        contentDescription = null,
        modifier = Modifier.size(15.dp),
        tint = MaterialTheme.colorScheme.onSurfaceVariant,
      )
      Text(
        meta,
        style = MaterialTheme.typography.labelSmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
      )
      moment.sourceAudio?.let { bytes ->
        IconButton(onClick = { onPlayAudio(bytes) }, modifier = Modifier.size(28.dp)) {
          Icon(
            Icons.Filled.PlayArrow,
            contentDescription = "播放当时的原声",
            modifier = Modifier.size(18.dp),
            tint = MaterialTheme.colorScheme.primary,
          )
        }
      }
    }
  }
}

/** The masked meaning: a warm sand patch that keeps the meaning's own size
 * (transparent text) until tapped, then reveals it in coral — the web's
 * `.masked` span and its --spark reveal reward. The shown foreign word is the
 * question; this is the thing reached for (§3.3). */
@Composable
internal fun MaskedMeaning(
  text: String,
  revealed: Boolean,
  onReveal: () -> Unit,
  style: TextStyle = MaterialTheme.typography.bodyLarge,
) {
  Box(
    modifier = Modifier
      .clip(RoundedCornerShape(6.dp))
      .background(if (revealed) Color.Transparent else MaterialTheme.colorScheme.surfaceVariant)
      // A sand hairline so the patch reads as tappable on the surface.
      .then(
        if (revealed) Modifier
        else Modifier.border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(6.dp))
      )
      .clickable(enabled = !revealed, onClick = onReveal)
      .padding(horizontal = 6.dp, vertical = 2.dp),
  ) {
    Text(
      text = text,
      style = style,
      color = if (revealed) MaterialTheme.colorScheme.tertiary else Color.Transparent,
    )
  }
}
