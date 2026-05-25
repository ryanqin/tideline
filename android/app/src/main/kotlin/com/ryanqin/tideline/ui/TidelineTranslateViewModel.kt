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
  val targetLang: String = "Japanese",
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
   * Image translation — Phase 5a probe.
   *
   * Reads the picked image's bytes off the main thread, then sends them next to
   * a translate instruction through the SAME multimodal Content path the text
   * flow uses. The open question this exercises: does the sideloaded E2B bundle
   * actually carry a vision tower? Capabilities can't report it (only
   * hasSpeculativeDecodingSupport exists), so a real run is the only oracle.
   *
   * MVP shortcut (deliberate, to be closed before 5a is "done"): the picked
   * image itself is NOT persisted — the drawer row stores original="[image …]"
   * and contextSnippet=null. Real episodic anchoring (keep a path/thumbnail back
   * to the photographed moment) is a follow-up, tracked against principle #2.
   */
  fun translateImage(uri: Uri) {
    val state = _ui.value
    if (state.engineState != EngineState.READY) return
    val lang = state.targetLang

    _ui.value = state.copy(
      engineState = EngineState.INFERRING,
      translation = "",
      errorMessage = null,
    )

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
      // Gemma 3n's multimodal format expects the image BEFORE the text question —
      // image-then-text grounds the instruction on the visual tokens. (First pass
      // had text-then-image and the model collapsed to a single "。".)
      val prompt = "Read all the text in this image and translate it to $lang."
      dispatchInference(
        contents = Contents.of(listOf(Content.ImageBytes(bytes), Content.Text(prompt))),
        originalLabel = "[image ${bytes.size} B]",
        source = "image",
        lang = lang,
      )
    }
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
            val translated = acc.toString().trim()
            _ui.value = _ui.value.copy(engineState = EngineState.READY, translation = translated)
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
            if (translated.isNotEmpty()) {
              viewModelScope.launch(Dispatchers.IO) {
                try {
                  dao.insert(
                    TranslationEntity(
                      original = originalLabel,
                      targetLang = lang,
                      translated = translated,
                      source = source,
                      contextSnippet = null,
                      sessionId = sessionId,
                    )
                  )
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
