/*
 * Tideline translate engine wrapper.
 *
 * Direct LiteRT-LM usage (no piggyback on a Model/Task scaffolding). Model is
 * sideloaded at MODEL_PATH via `adb push`. Polished download UX is deferred to
 * a later phase — for the standalone Tideline app the dev cycle stays:
 * download once on Mac, push, run.
 */

package com.ryanqin.tideline.ui

import android.app.Application
import android.net.Uri
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.google.ai.edge.litertlm.Backend
import com.google.ai.edge.litertlm.Content
import com.google.ai.edge.litertlm.Contents
import com.google.ai.edge.litertlm.Conversation
import com.google.ai.edge.litertlm.ConversationConfig
import com.google.ai.edge.litertlm.Engine
import com.google.ai.edge.litertlm.EngineConfig
import com.google.ai.edge.litertlm.ExperimentalApi
import com.google.ai.edge.litertlm.Message
import com.google.ai.edge.litertlm.MessageCallback
import com.google.ai.edge.litertlm.SamplerConfig
import com.ryanqin.tideline.data.TidelineDatabase
import com.ryanqin.tideline.data.TranslationDao
import com.ryanqin.tideline.data.TranslationEntity
import com.ryanqin.tideline.intelligence.parseImageReply
import com.ryanqin.tideline.media.exifRotationDegrees
import com.ryanqin.tideline.media.prepareCaptureImage
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

private const val TAG = "TidelineTranslateVM"

// Sideload path. Push the model with:
//   adb push gemma-4-E2B-it.litertlm /data/local/tmp/
private const val MODEL_PATH = "/data/local/tmp/gemma-4-E2B-it.litertlm"

// Phase 5b audio probe: a known-good 16 kHz mono WAV pushed to the device, so we can
// verify the audio→translation path AND the expected format before building live mic
// capture. Push with: adb push tideline_probe.wav /data/local/tmp/
private const val AUDIO_PROBE_PATH = "/data/local/tmp/tideline_probe.wav"

// Mirrors tideline/core/src/tideline/bench/atoms/a1_word_translation.py and a2_sentence_translation.py.
// Same prompt is used by Tideline's Python core in production — keep them in sync.
private const val SYSTEM_PROMPT =
  "You are a precise translator. Respond with only the translation — " +
    "no preamble, no explanation, no quotation marks."

// Sampler defaults from upstream's model_allowlists/1_0_15.json :: Gemma-4-E2B-it.defaultConfig
private const val DEFAULT_TOP_K = 64
private const val DEFAULT_TOP_P = 0.95
private const val DEFAULT_TEMPERATURE = 1.0
private const val DEFAULT_MAX_TOKENS = 4000

enum class EngineState { IDLE, INITIALIZING, READY, INFERRING, ERROR }

data class TidelineUiState(
  val engineState: EngineState = EngineState.IDLE,
  val sourceText: String = "",
  // Principle 3 (DESIGN §3.3): Tideline always translates INTO your first
  // language — the shell's probe-era "Japanese" default predated that
  // decision. A real first-language setting (mirroring web's identity
  // picker) is later work; Chinese matches the product's current user.
  val targetLang: String = "Chinese",
  val translation: String = "",
  val errorMessage: String? = null,
)

@OptIn(ExperimentalApi::class)
class TidelineTranslateViewModel(application: Application) : AndroidViewModel(application) {

  private val _ui = MutableStateFlow(TidelineUiState())
  val ui = _ui.asStateFlow()

  private val dao: TranslationDao = TidelineDatabase.get(application).translationDao()

  // App-launch session UUID. MVP shortcut; real Tideline "outing" semantics
  // (GPS / time-window grouping) lands in Phase 5d.
  private val sessionId: String = UUID.randomUUID().toString()

  val history = dao.observeLatest().stateIn(
    scope = viewModelScope,
    started = SharingStarted.WhileSubscribed(stopTimeoutMillis = 5_000),
    initialValue = emptyList(),
  )

  private var engine: Engine? = null
  private var conversation: Conversation? = null

  fun initEngine() {
    if (_ui.value.engineState != EngineState.IDLE) return
    _ui.value = _ui.value.copy(engineState = EngineState.INITIALIZING, errorMessage = null)

    viewModelScope.launch(Dispatchers.IO) {
      try {
        Log.d(TAG, "Initializing engine from $MODEL_PATH")
        // When loading model from /data/local/tmp (read-only-ish sideload location),
        // LiteRT-LM needs an app-owned writable scratch path for compile cache.
        val cacheDir = getApplication<Application>().getExternalFilesDir(null)?.absolutePath
        // Multimodal: the vision AND audio encoders are SEPARATE subgraphs, each with
        // its own backend. Leaving visionBackend / audioBackend / maxNumImages unset
        // (the original Phase 5a crash) meant an incoming image had no vision pipeline
        // to flow through → native null-deref in liblitertlm on the engine thread
        // (SIGSEGV, not a catchable error). The bundle carries both encoders
        // (tf_lite_vision_encoder / tf_lite_audio_encoder_hw), so this is pure config.
        // Keep the LLM on GPU (fast text TTFT); run the vision and audio encoders on
        // CPU (the ops the GPU delegate choked on); reserve one image slot.
        val cfg = EngineConfig(
          modelPath = MODEL_PATH,
          backend = Backend.GPU(),
          visionBackend = Backend.CPU(),
          audioBackend = Backend.CPU(),
          maxNumTokens = DEFAULT_MAX_TOKENS,
          maxNumImages = 1,
          cacheDir = cacheDir,
        )
        val e = Engine(cfg)
        e.initialize()
        val sys: Contents = Contents.of(listOf(Content.Text(SYSTEM_PROMPT)))
        val c = e.createConversation(
          ConversationConfig(
            samplerConfig = SamplerConfig(
              topK = DEFAULT_TOP_K,
              topP = DEFAULT_TOP_P,
              temperature = DEFAULT_TEMPERATURE,
            ),
            systemInstruction = sys,
          )
        )
        engine = e
        conversation = c
        Log.d(TAG, "Engine ready")
        _ui.value = _ui.value.copy(engineState = EngineState.READY)
      } catch (t: Throwable) {
        Log.e(TAG, "Engine init failed", t)
        _ui.value = _ui.value.copy(
          engineState = EngineState.ERROR,
          errorMessage = "Init failed: ${t.message}",
        )
      }
    }
  }

  fun onSourceTextChange(text: String) {
    _ui.value = _ui.value.copy(sourceText = text)
  }

  fun translate() {
    val state = _ui.value
    if (state.engineState != EngineState.READY) return
    val src = state.sourceText.trim()
    if (src.isEmpty()) return

    _ui.value = state.copy(
      engineState = EngineState.INFERRING,
      translation = "",
      errorMessage = null,
    )

    val userText = "Translate the following to ${state.targetLang}: $src"
    dispatchInference(
      contents = Contents.of(listOf(Content.Text(userText))),
      originalLabel = src,
      source = "text",
      lang = state.targetLang,
    )
  }

  /*
   * Image translation — Phase 5a.
   *
   * Two entrances, one body: the system photo picker (probe-era path, kept)
   * and the in-app viewfinder (live capture). Both prepare the image the same
   * way off the main thread — rotated upright (EXIF for picked photos, the
   * ImageProxy rotation for captures), longest edge capped, re-encoded — then
   * send it through the SAME multimodal Content path the text flow uses.
   *
   * Episodic anchoring: the drawer row stores original="[image …]" and
   * contextSnippet = the VLM's scene gist (parsed from the SCENE: line). The
   * prepared photo itself persists as source_image — recall material, never
   * discarded once the VLM has read it (mirrors Python core §3.2).
   */
  fun translateImage(uri: Uri) {
    if (!beginImageInference()) return
    viewModelScope.launch(Dispatchers.IO) {
      val bytes = try {
        getApplication<Application>().contentResolver.openInputStream(uri)?.use { it.readBytes() }
      } catch (t: Throwable) {
        Log.e(TAG, "Reading picked image failed", t)
        null
      }
      if (bytes == null || bytes.isEmpty()) {
        _ui.value = _ui.value.copy(
          engineState = EngineState.ERROR,
          errorMessage = "Couldn't read the selected image",
        )
        return@launch
      }
      runImageInference(bytes, exifRotationDegrees(bytes))
    }
  }

  /** In-app viewfinder shutter → raw JPEG + CameraX rotation. */
  fun translateCapturedImage(bytes: ByteArray, rotationDegrees: Int) {
    if (!beginImageInference()) return
    viewModelScope.launch(Dispatchers.IO) {
      runImageInference(bytes, rotationDegrees)
    }
  }

  /** Flip the UI into INFERRING for an image run; false when engine not ready. */
  private fun beginImageInference(): Boolean {
    val state = _ui.value
    if (state.engineState != EngineState.READY) return false
    _ui.value = state.copy(
      engineState = EngineState.INFERRING,
      translation = "",
      errorMessage = null,
    )
    return true
  }

  // Gemma 3n's multimodal format expects the image BEFORE the text question —
  // image-then-text grounds the instruction on the visual tokens. (First pass
  // had text-then-image and the model collapsed to a single "。".)
  //
  // Two-line ask in ONE inference (a second image pass would double the ~7s
  // on-device latency): the translation AND a short scene gist. The gist
  // becomes the episodic context_snippet — the "where/what was this moment"
  // signal that was always null before. Engineering stays load-bearing
  // (session_id / timestamp / modality); this gist is the point-of-light
  // warmth layer, and being VLM-produced it is honest to store (unlike the
  // narrated scene prose the product could never actually capture).
  private fun runImageInference(rawBytes: ByteArray, rotationDegrees: Int) {
    val lang = _ui.value.targetLang
    val prepared = prepareCaptureImage(rawBytes, rotationDegrees)
    if (prepared == null) {
      _ui.value = _ui.value.copy(
        engineState = EngineState.ERROR,
        errorMessage = "Couldn't decode the image",
      )
      return
    }
    // Third line TERMS = the emergence loop's feed: each original=translation
    // pair becomes its own drawer row (the shape promotion/clustering reads),
    // instead of one unpromotable "[image N B]" placeholder. TERMS comes LAST
    // so a partial/garbled tail degrades the vocabulary, never the
    // translation the user is waiting on.
    val prompt =
      "Look at this image and reply in exactly three lines:\n" +
        "TRANSLATION: all visible text translated to $lang (write NONE if there is no text)\n" +
        "SCENE: 5-8 words naming where/what this is — place, activity, or notable objects\n" +
        "TERMS: the 1-6 most useful words or short phrases from the image, " +
        "each as original=translation, separated by | (write NONE if there is no text)"
    dispatchInference(
      contents = Contents.of(listOf(Content.ImageBytes(prepared), Content.Text(prompt))),
      originalLabel = "[image ${prepared.size} B]",
      source = "image",
      lang = lang,
      sourceImage = prepared,
    )
  }

  /*
   * Audio translation — Phase 5b probe.
   *
   * Reads a known-good 16 kHz mono WAV pushed to the device. Content.AudioFile lets
   * the native engine open the /data/local/tmp path the same way it opens the model,
   * so no app-side file IO and no mic permission. Verifies two things at once before
   * any mic plumbing: (a) does the model do speech→translation end to end, and (b)
   * does this audio format work. Conformer audio encoder is in the bundle; audioBackend
   * is set to CPU in initEngine. Audio precedes text, mirroring the image path.
   */
  fun translateAudioProbe() {
    val state = _ui.value
    if (state.engineState != EngineState.READY) return
    val lang = state.targetLang

    _ui.value = state.copy(
      engineState = EngineState.INFERRING,
      translation = "",
      errorMessage = null,
    )

    val prompt = "Translate the speech in this audio to $lang."
    dispatchInference(
      contents = Contents.of(listOf(Content.AudioFile(AUDIO_PROBE_PATH), Content.Text(prompt))),
      originalLabel = "[audio probe]",
      source = "audio",
      lang = lang,
    )
  }

  /*
   * Shared inference dispatch for every input modality. Caller has already set
   * engineState = INFERRING. Streams tokens into ui.translation, logs the BENCH
   * triple (start / first_token / done), and persists the finished row tagged
   * with `source`. Keeping one body means text and image stay strictly in sync.
   */
  private fun dispatchInference(
    contents: Contents,
    originalLabel: String,
    source: String,
    lang: String,
    sourceImage: ByteArray? = null,
  ) {
    val conv = conversation ?: run {
      _ui.value = _ui.value.copy(
        engineState = EngineState.ERROR,
        errorMessage = "Engine not ready",
      )
      return
    }

    val tStart = System.currentTimeMillis()
    var tFirst = 0L
    var firstSeen = false
    // litertlm streams INCREMENTAL deltas, not cumulative text — each onMessage is
    // the next chunk. Accumulate them; the original code REPLACED, so it kept only
    // the final token (a lone "。") even while real text streamed past on screen.
    // Text-path never caught this because short outputs arrive in one chunk.
    val acc = StringBuilder()
    Log.i(TAG, "BENCH start t=$tStart src=\"$originalLabel\" source=$source lang=$lang")
    try {
      conv.sendMessageAsync(
        contents,
        object : MessageCallback {
          override fun onMessage(message: Message) {
            if (!firstSeen) {
              tFirst = System.currentTimeMillis()
              firstSeen = true
              Log.i(TAG, "BENCH first_token ttft_ms=${tFirst - tStart}")
            }
            acc.append(message.toString())
            _ui.value = _ui.value.copy(translation = acc.toString())
          }

          override fun onDone() {
            val raw = acc.toString().trim()
            // Image prompt returns marked TRANSLATION / SCENE / TERMS lines;
            // text/audio replies carry no markers and pass through unchanged
            // (gist null, no terms).
            val reply = parseImageReply(raw)
            val translated = reply.translated
            _ui.value = _ui.value.copy(engineState = EngineState.READY, translation = translated)
            Log.i(TAG, "BENCH scene_gist=\"${reply.sceneGist}\" terms=${reply.terms.size}")
            val tDone = System.currentTimeMillis()
            val total = tDone - tStart
            val genMs = if (firstSeen) tDone - tFirst else 0L
            val outChars = translated.length
            val tokPerSec = if (genMs > 0) outChars * 1000.0 / genMs else 0.0
            Log.i(
              TAG,
              "BENCH done total_ms=$total gen_ms=$genMs out_chars=$outChars " +
                "approx_tok_per_s=${"%.2f".format(tokPerSec)} out=\"$translated\""
            )
            // The words are the sediment: with parsed TERMS each pair lands as
            // its own row — original = the foreign word actually met — every
            // row carrying the scene gist AND the photo (the per-word recall
            // material the museum's moment stacks render). Without terms, fall
            // back to the single summary row so nothing regresses.
            val rows = if (reply.terms.isNotEmpty()) {
              reply.terms.map { term ->
                TranslationEntity(
                  original = term.original,
                  targetLang = lang,
                  translated = term.translated,
                  source = source,
                  contextSnippet = reply.sceneGist,
                  sessionId = sessionId,
                  sourceImage = sourceImage,
                )
              }
            } else if (translated.isNotEmpty()) {
              listOf(
                TranslationEntity(
                  original = originalLabel,
                  targetLang = lang,
                  translated = translated,
                  source = source,
                  contextSnippet = reply.sceneGist,
                  sessionId = sessionId,
                  sourceImage = sourceImage,
                )
              )
            } else emptyList()
            if (rows.isNotEmpty()) {
              viewModelScope.launch(Dispatchers.IO) {
                try {
                  rows.forEach { dao.insert(it) }
                } catch (t: Throwable) {
                  Log.e(TAG, "Persist translation failed", t)
                }
              }
            }
          }

          override fun onError(throwable: Throwable) {
            Log.e(TAG, "Inference error", throwable)
            _ui.value = _ui.value.copy(
              engineState = EngineState.ERROR,
              errorMessage = "Inference failed: ${throwable.message}",
            )
          }
        },
        emptyMap(),
      )
    } catch (t: Throwable) {
      Log.e(TAG, "sendMessageAsync threw", t)
      _ui.value = _ui.value.copy(
        engineState = EngineState.ERROR,
        errorMessage = "Send failed: ${t.message}",
      )
    }
  }

  override fun onCleared() {
    try {
      conversation?.close()
    } catch (_: Throwable) {}
    conversation = null
    engine = null
    super.onCleared()
  }
}
