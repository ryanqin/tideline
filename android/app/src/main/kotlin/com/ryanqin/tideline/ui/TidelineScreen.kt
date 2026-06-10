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
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
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

  Scaffold { innerPadding ->
    Column(
      modifier = Modifier
        .fillMaxSize()
        .padding(innerPadding)
        .padding(horizontal = 24.dp, vertical = 16.dp)
        .verticalScroll(rememberScrollState()),
      verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
      Text(text = "Tideline", style = MaterialTheme.typography.displaySmall)
      Text(
        text = "本地翻译 · 涌现学习",
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
      )

      Spacer(modifier = Modifier.height(4.dp))
      EngineStatusBar(state.engineState, state.errorMessage)

      OutlinedTextField(
        value = state.sourceText,
        onValueChange = viewModel::onSourceTextChange,
        modifier = Modifier.fillMaxWidth(),
        label = { Text("Source text") },
        placeholder = { Text("e.g. 寿司") },
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
      )

      Button(
        onClick = viewModel::translate,
        modifier = Modifier.fillMaxWidth(),
        enabled = state.engineState == EngineState.READY && state.sourceText.isNotBlank(),
      ) {
        Text("Translate to ${state.targetLang}")
      }

      OutlinedButton(
        onClick = {
          val granted = ContextCompat.checkSelfPermission(
            context, Manifest.permission.CAMERA
          ) == PackageManager.PERMISSION_GRANTED
          if (granted) showCamera = true else requestCamera.launch(Manifest.permission.CAMERA)
        },
        modifier = Modifier.fillMaxWidth(),
        enabled = state.engineState == EngineState.READY,
      ) {
        Text("拍照翻译 → ${state.targetLang}")
      }

      OutlinedButton(
        onClick = {
          pickImage.launch(
            PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)
          )
        },
        modifier = Modifier.fillMaxWidth(),
        enabled = state.engineState == EngineState.READY,
      ) {
        Text("从相册选图翻译 → ${state.targetLang}")
      }

      OutlinedButton(
        onClick = viewModel::translateAudioProbe,
        modifier = Modifier.fillMaxWidth(),
        enabled = state.engineState == EngineState.READY,
      ) {
        Text("翻译测试音频(probe) → ${state.targetLang}")
      }

      if (state.translation.isNotEmpty() || state.engineState == EngineState.INFERRING) {
        TranslationCard(state.translation, streaming = state.engineState == EngineState.INFERRING)
      }

      if (history.isNotEmpty()) {
        Spacer(modifier = Modifier.height(8.dp))
        HorizontalDivider()
        Text(
          text = "你的最近翻译 (${history.size})",
          style = MaterialTheme.typography.titleSmall,
          fontWeight = FontWeight.SemiBold,
        )
        history.forEach { row -> HistoryRow(row) }
      }
    }
  }
}

@Composable
private fun EngineStatusBar(engineState: EngineState, errorMessage: String?) {
  val (text, color) = when (engineState) {
    EngineState.IDLE -> "Engine idle" to MaterialTheme.colorScheme.onSurfaceVariant
    EngineState.INITIALIZING -> "Loading Gemma E2B from /data/local/tmp/…" to
      MaterialTheme.colorScheme.primary
    EngineState.READY -> "Engine ready" to Color(0xFF2E7D32)
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
private fun HistoryRow(row: TranslationEntity) {
  Card(
    modifier = Modifier.fillMaxWidth(),
    colors = CardDefaults.cardColors(
      containerColor = MaterialTheme.colorScheme.surfaceContainerLow,
    ),
  ) {
    Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
      Text(
        text = row.original,
        style = MaterialTheme.typography.bodyMedium,
        fontWeight = FontWeight.Medium,
      )
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
          text = TIME_FMT.format(Date(row.createdAt)),
          style = MaterialTheme.typography.labelSmall,
          color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
      }
    }
  }
}

private val TIME_FMT = SimpleDateFormat("MM-dd HH:mm", Locale.getDefault())
