/*
 * Tideline translate screen.
 *
 * Single Compose surface for: input → translate → result card → recent
 * history. Phase 5a adds image input via the system photo picker (no camera
 * permission); live CameraX capture and mic input come later.
 */

package com.ryanqin.tideline.ui

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material.icons.automirrored.filled.VolumeUp
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.viewmodel.compose.viewModel
import com.ryanqin.tideline.data.TranslationEntity
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun TidelineScreen(viewModel: TidelineTranslateViewModel = viewModel()) {
  val state by viewModel.ui.collectAsState()
  val history by viewModel.history.collectAsState()
  val context = LocalContext.current

  // Kick off engine load on first composition.
  LaunchedEffect(Unit) { viewModel.initEngine() }

  // Phase 5a image probe: system photo picker → bytes → multimodal translate.
  // No camera permission needed; the picker runs in its own process.
  val pickImage = rememberLauncherForActivityResult(
    ActivityResultContracts.PickVisualMedia()
  ) { uri -> if (uri != null) viewModel.translateImage(uri) }

  // Phase 5a live capture: in-app viewfinder over this screen. Permission is
  // asked lazily on the first tap; a grant opens the camera right away.
  var showCamera by remember { mutableStateOf(false) }
  val requestCamera = rememberLauncherForActivityResult(
    ActivityResultContracts.RequestPermission()
  ) { granted -> if (granted) showCamera = true }

  // Phase 5b live mic: permission asked lazily on the first tap; a grant
  // starts recording right away (same pattern as the camera).
  val requestMic = rememberLauncherForActivityResult(
    ActivityResultContracts.RequestPermission()
  ) { granted -> if (granted) viewModel.toggleRecording() }

  // Phase 5c: the shore and the museum. Plain doorways, always present —
  // never a count, never a badge (DESIGN §3.1/§10.3). The shore rises from
  // the foot of the desk (swipe up or tap the handle), the web's wade-in.
  var showReview by remember { mutableStateOf(false) }
  var showMuseum by remember { mutableStateOf(false) }
  if (showMuseum) {
    MuseumScreen(viewModel = viewModel, onClose = { showMuseum = false })
    return
  }

  if (showCamera) {
    CameraCaptureScreen(
      onCaptured = { bytes, rotation ->
        showCamera = false
        viewModel.translateCapturedImage(bytes, rotation)
      },
      onClose = { showCamera = false },
    )
    return
  }

  Box(modifier = Modifier.fillMaxSize()) {
  ShoreBackdrop {
  Scaffold(containerColor = Color.Transparent) { innerPadding ->
    Box(modifier = Modifier.fillMaxSize().padding(innerPadding)) {
    Column(
      modifier = Modifier
        .fillMaxSize()
        .padding(horizontal = 24.dp, vertical = 16.dp)
        .verticalScroll(rememberScrollState())
        .padding(bottom = 88.dp),
      verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
      // The desk is the hub (DESIGN §10.7): the shelves are one tap here,
      // the shore one tap on the handle below.
      Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Text(text = "Tideline", style = MaterialTheme.typography.displaySmall)
        Spacer(modifier = Modifier.weight(1f))
        TextButton(onClick = { showMuseum = true }) {
          Text("陈列馆 ›", color = MaterialTheme.colorScheme.primary)
        }
      }

      EngineStatusBar(state.engineState, state.errorMessage)

      // The web translator: the question as its own quiet line, then a
      // sun-warmed card with no chrome — never a framed form field.
      Text("想翻译什么?", style = MaterialTheme.typography.titleMedium)
      Surface(
        shape = RoundedCornerShape(16.dp),
        color = MaterialTheme.colorScheme.surface,
        shadowElevation = 1.dp,
        modifier = Modifier.fillMaxWidth(),
      ) {
        TextField(
          value = state.sourceText,
          onValueChange = viewModel::onSourceTextChange,
          modifier = Modifier.fillMaxWidth(),
          placeholder = { Text("输入文字,粘贴一行菜单,丢进一句话……") },
          minLines = 2,
          maxLines = 6,
          enabled = state.engineState != EngineState.INFERRING,
          trailingIcon = if (state.sourceText.isNotEmpty()) {
            {
              IconButton(onClick = { viewModel.onSourceTextChange("") }) {
                Icon(Icons.Default.Clear, contentDescription = "Clear")
              }
            }
          } else null,
          colors = TextFieldDefaults.colors(
            focusedContainerColor = Color.Transparent,
            unfocusedContainerColor = Color.Transparent,
            disabledContainerColor = Color.Transparent,
            focusedIndicatorColor = Color.Transparent,
            unfocusedIndicatorColor = Color.Transparent,
            disabledIndicatorColor = Color.Transparent,
          ),
        )
      }

      Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Text(
          "译成你的第一语言 · 中文",
          style = MaterialTheme.typography.bodySmall,
          color = MaterialTheme.colorScheme.onSurfaceVariant,
          modifier = Modifier.weight(1f),
        )
        Button(
          onClick = viewModel::translate,
          enabled = state.engineState == EngineState.READY && state.sourceText.isNotBlank(),
        ) {
          Text("翻译")
        }
      }

      // The phone's own ways of meeting words — soft tonal pills, never a
      // row of outlined chrome.
      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
      ) {
        FilledTonalButton(
          onClick = {
            val granted = ContextCompat.checkSelfPermission(
              context, Manifest.permission.CAMERA
            ) == PackageManager.PERMISSION_GRANTED
            if (granted) showCamera = true else requestCamera.launch(Manifest.permission.CAMERA)
          },
          modifier = Modifier.weight(1f),
          enabled = state.engineState == EngineState.READY,
        ) { Text("拍照") }
        FilledTonalButton(
          onClick = {
            pickImage.launch(
              PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)
            )
          },
          modifier = Modifier.weight(1f),
          enabled = state.engineState == EngineState.READY,
        ) { Text("相册") }
        FilledTonalButton(
          onClick = {
            val granted = ContextCompat.checkSelfPermission(
              context, Manifest.permission.RECORD_AUDIO
            ) == PackageManager.PERMISSION_GRANTED
            if (granted) viewModel.toggleRecording()
            else requestMic.launch(Manifest.permission.RECORD_AUDIO)
          },
          modifier = Modifier.weight(1f),
          enabled = state.engineState == EngineState.READY || state.recording,
        ) { Text(if (state.recording) "停止 ●" else "录音") }
      }

      if (state.translation.isNotEmpty() || state.engineState == EngineState.INFERRING) {
        TranslationCard(state.translation, streaming = state.engineState == EngineState.INFERRING)
      }

      Text(
        "你翻译的一切都只存在本地。等翻译攒得够多,涉水走进海岸,或去沙丘上的陈列馆,看那些悄悄成形的东西。",
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
      )

      if (history.isNotEmpty()) {
        Spacer(modifier = Modifier.height(8.dp))
        HorizontalDivider()
        Text(
          text = "你的最近翻译 (${history.size})",
          style = MaterialTheme.typography.titleSmall,
          fontWeight = FontWeight.SemiBold,
        )
        history.forEach { row ->
          HistoryRow(row, onSpeak = { viewModel.speak(row.original, row.sourceLang) })
        }
      }
    }
    // Wade into the shore — the web desk's swipe-up handle: a quiet chevron
    // resting on the tideline. The whole strip answers an upward drag, not
    // just the button (a wade is a gesture, not a click).
    Column(
      modifier = Modifier
        .align(Alignment.BottomCenter)
        .fillMaxWidth()
        .pointerInput(Unit) {
          var pulled = 0f
          detectVerticalDragGestures(
            onDragStart = { pulled = 0f },
            onVerticalDrag = { _, dy ->
              pulled += dy
              if (pulled < -48f && !showReview) showReview = true
            },
          )
        }
        .padding(bottom = 10.dp),
      horizontalAlignment = Alignment.CenterHorizontally,
    ) {
      IconButton(onClick = { showReview = true }) {
        Icon(
          Icons.Default.KeyboardArrowUp,
          contentDescription = "涉水进海岸",
          tint = MaterialTheme.colorScheme.primary,
          modifier = Modifier.size(32.dp),
        )
      }
      Text(
        "海岸",
        style = MaterialTheme.typography.labelSmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
      )
    }
    }
  }
  }
  // The shore rises from the bottom of the desk and slides back down — the
  // wade in, the walk back (web §10.2).
  AnimatedVisibility(
    visible = showReview,
    enter = slideInVertically(initialOffsetY = { it }),
    exit = slideOutVertically(targetOffsetY = { it }),
  ) {
    ReviewScreen(viewModel = viewModel, onClose = { showReview = false })
  }
  }
}

@Composable
private fun EngineStatusBar(engineState: EngineState, errorMessage: String?) {
  // READY is the resting state — it stays quiet (muted, like the web's
  // restraint rule); only the transient states glow amber.
  val (text, color) = when (engineState) {
    EngineState.IDLE -> "Engine idle" to MaterialTheme.colorScheme.onSurfaceVariant
    EngineState.INITIALIZING -> "Loading Gemma E2B from /data/local/tmp/…" to
      MaterialTheme.colorScheme.primary
    EngineState.READY -> "Engine ready" to MaterialTheme.colorScheme.onSurfaceVariant
    EngineState.INFERRING -> "Translating…" to MaterialTheme.colorScheme.primary
    EngineState.ERROR -> (errorMessage ?: "Engine error") to MaterialTheme.colorScheme.error
  }
  Column(modifier = Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(4.dp)) {
    Text(text = text, style = MaterialTheme.typography.bodySmall, color = color)
    if (engineState == EngineState.INITIALIZING || engineState == EngineState.INFERRING) {
      LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
    }
  }
}

@Composable
private fun TranslationCard(text: String, streaming: Boolean) {
  Card(
    modifier = Modifier.fillMaxWidth(),
    colors = CardDefaults.cardColors(
      containerColor = MaterialTheme.colorScheme.surfaceContainerHigh,
    ),
  ) {
    Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
      Text(
        text = if (streaming) "Translating" else "Translation",
        style = MaterialTheme.typography.labelSmall,
        fontWeight = FontWeight.SemiBold,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
      )
      Text(
        text = text.ifEmpty { "…" },
        style = MaterialTheme.typography.bodyLarge,
      )
    }
  }
}

@Composable
private fun HistoryRow(row: TranslationEntity, onSpeak: () -> Unit) {
  Card(
    modifier = Modifier.fillMaxWidth(),
    colors = CardDefaults.cardColors(
      containerColor = MaterialTheme.colorScheme.surfaceContainerLow,
    ),
  ) {
    Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
      ) {
        Text(
          text = row.original,
          style = MaterialTheme.typography.bodyMedium,
          fontWeight = FontWeight.Medium,
          modifier = Modifier.weight(1f, fill = false),
        )
        IconButton(onClick = onSpeak, modifier = Modifier.size(24.dp)) {
          Icon(
            Icons.AutoMirrored.Filled.VolumeUp,
            contentDescription = "Standard pronunciation",
            tint = MaterialTheme.colorScheme.primary,
          )
        }
      }
      Text(
        text = "→ ${row.translated}",
        style = MaterialTheme.typography.bodyMedium,
      )
      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
      ) {
        Text(
          text = row.targetLang,
          style = MaterialTheme.typography.labelSmall,
          color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
          text = Lingo.humanTime(row.createdAt),
          style = MaterialTheme.typography.labelSmall,
          color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
      }
    }
  }
}

private val TIME_FMT = SimpleDateFormat("MM-dd HH:mm", Locale.getDefault())
