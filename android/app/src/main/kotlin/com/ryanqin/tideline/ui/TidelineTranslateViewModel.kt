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
import android.speech.tts.TextToSpeech
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
import android.graphics.BitmapFactory
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import com.ryanqin.tideline.data.CardEntity
import com.ryanqin.tideline.data.ThemeGroup
import com.ryanqin.tideline.data.ThemeReviewEntity
import com.ryanqin.tideline.data.TidelineDatabase
import com.ryanqin.tideline.data.TranslationDao
import com.ryanqin.tideline.data.TranslationEntity
import com.ryanqin.tideline.data.dueThemes
import com.ryanqin.tideline.data.emergenceSweep
import com.ryanqin.tideline.data.liveSessionId
import com.ryanqin.tideline.data.reschedule
import com.ryanqin.tideline.data.themeGroups
import com.ryanqin.tideline.intelligence.ImageReply
import com.ryanqin.tideline.intelligence.detectScriptLanguage
import com.ryanqin.tideline.intelligence.parseAudioReply
import com.ryanqin.tideline.intelligence.parseImageReply
import com.ryanqin.tideline.media.exifRotationDegrees
import com.ryanqin.tideline.media.WavRecorder
import com.ryanqin.tideline.media.matchTermBoxes
import com.ryanqin.tideline.media.ocrWords
import com.ryanqin.tideline.media.prepareCaptureImage
import org.json.JSONArray
import org.json.JSONObject
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

// A fallback summary row longer than this is a degeneration loop, not a
// translation — don't let it sediment.
private const val MAX_PERSIST_CHARS = 800

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
  // Live mic capture in progress (Phase 5b) — drives the record button label.
  val recording: Boolean = false,
)

/** One thing the tide carried ashore: a word card, or a whole scene. */
sealed interface ReviewItem {
  data class Word(val card: CardEntity) : ReviewItem
  data class Scene(val group: ThemeGroup, val strength: Int) : ReviewItem
}

@OptIn(ExperimentalApi::class)
class TidelineTranslateViewModel(application: Application) : AndroidViewModel(application) {

  private val _ui = MutableStateFlow(TidelineUiState())
  val ui = _ui.asStateFlow()

  private val db = TidelineDatabase.get(application)
  private val dao: TranslationDao = db.translationDao()
  private val emergence = db.emergenceDao()

  /** The night-watch is deterministic SQL — cheap enough to run at startup
   * and after every capture (the live-sweep shape the web grew in core). */
  private fun sweepSoon() {
    viewModelScope.launch(Dispatchers.IO) {
      try {
        emergenceSweep(db.openHelper.writableDatabase)
      } catch (t: Throwable) {
        Log.e(TAG, "Emergence sweep failed", t)
      }
    }
  }

  init {
    sweepSoon()
  }

  // --- review deck (the shore's job, on the phone) -------------------------

  /** Everything due now: word cards first (the concrete drill), then whole
   * scenes (the occasion recalled as one) — the same two review units the web
   * shore surfaces, each weakest-first within its kind. */
  suspend fun reviewDeck(): List<ReviewItem> {
    val now = System.currentTimeMillis()
    val words = emergence.dueCards(now).map { ReviewItem.Word(it) }
    val states = emergence.themeReviewStates().associateBy { it.sessionId }
    val scenes = dueThemes(themeGroups(emergence.themeRows()), states, now)
      .map { ReviewItem.Scene(it.group, it.strength) }
    return words + scenes
  }

  suspend fun cardMoments(cardId: Long): List<TranslationEntity> =
    emergence.cardMoments(cardId)

  /** A scene member's photo, fetched only when its card is on screen — the
   * theme rows themselves travel without blobs. */
  suspend fun photoFor(id: Long): ByteArray? = dao.imageFor(id)

  fun playRecordingFor(id: Long) {
    viewModelScope.launch(Dispatchers.IO) {
      try {
        dao.audioFor(id)?.let { playRecording(it) }
      } catch (t: Throwable) {
        Log.e(TAG, "Replay fetch failed", t)
      }
    }
  }

  fun reviewTheme(sessionId: String, remembered: Boolean) {
    viewModelScope.launch(Dispatchers.IO) {
      try {
        val now = System.currentTimeMillis()
        val state = emergence.themeReview(sessionId)
        val (next, dueAt) = reschedule(state?.strength ?: 0, remembered, now)
        emergence.upsertThemeReview(
          ThemeReviewEntity(
            sessionId = sessionId,
            strength = next,
            dueAt = dueAt,
            lastReviewedAt = now,
            reviews = (state?.reviews ?: 0) + 1,
          )
        )
      } catch (t: Throwable) {
        Log.e(TAG, "Theme review failed", t)
      }
    }
  }

  fun reviewCard(cardId: Long, remembered: Boolean) {
    viewModelScope.launch(Dispatchers.IO) {
      try {
        val now = System.currentTimeMillis()
        val strength = emergence.cardStrength(cardId) ?: return@launch
        val (next, dueAt) = reschedule(strength, remembered, now)
        emergence.applyReview(cardId, next, dueAt, now)
      } catch (t: Throwable) {
        Log.e(TAG, "Review failed", t)
      }
    }
  }

  fun sinkCard(cardId: Long) {
    viewModelScope.launch(Dispatchers.IO) {
      try {
        emergence.sinkCard(cardId)
      } catch (t: Throwable) {
        Log.e(TAG, "Sink failed", t)
      }
    }
  }

  // Occasion boundary (5d-lite): captures within the inactivity window share
  // a session — promotion counts distinct sessions, so one sitting is one
  // encounter no matter how many shots it takes.
  private val sessionPrefs =
    application.getSharedPreferences("tideline_session", Application.MODE_PRIVATE)

  private fun currentSessionId(): String = liveSessionId(sessionPrefs)

  val history = dao.observeLatest().stateIn(
    scope = viewModelScope,
    started = SharingStarted.WhileSubscribed(stopTimeoutMillis = 5_000),
    initialValue = emptyList(),
  )

  private var engine: Engine? = null
  private var conversation: Conversation? = null

  // Standard pronunciation — the platform TTS speaks a row's original in its
  // own language, regenerated from text on demand (never stored). The same
  // split as the web: the RECORDING is material, the standard voice is free.
  private var ttsReady = false
  private val tts: TextToSpeech by lazy {
    TextToSpeech(getApplication()) { status -> ttsReady = status == TextToSpeech.SUCCESS }
  }

  fun speak(text: String, langName: String?) {
    if (text.isBlank()) return
    val t = tts
    if (!ttsReady) return
    val locale = when (langName) {
      "Japanese" -> java.util.Locale.JAPANESE
      "Korean" -> java.util.Locale.KOREAN
      "French" -> java.util.Locale.FRENCH
      "German" -> java.util.Locale.GERMAN
      "Italian" -> java.util.Locale.ITALIAN
      "Spanish" -> java.util.Locale("es")
      "Chinese" -> java.util.Locale.CHINESE
      "English" -> java.util.Locale.ENGLISH
      // No reliable label: honest script sniff, then English.
      else -> when (detectScriptLanguage(text)) {
        "Japanese" -> java.util.Locale.JAPANESE
        "Korean" -> java.util.Locale.KOREAN
        else -> if (text.any { it.code in 0x4E00..0x9FFF }) java.util.Locale.CHINESE
        else java.util.Locale.ENGLISH
      }
    }
    t.language = locale
    t.speak(text, TextToSpeech.QUEUE_FLUSH, null, "tideline-speak")
  }

  // The captured recording, played back — dictation material. WAV bytes go
  // through a small cache file (MediaPlayer has no byte[] source).
  private var player: android.media.MediaPlayer? = null

  fun playRecording(wav: ByteArray) {
    viewModelScope.launch(Dispatchers.IO) {
      try {
        val f = java.io.File(getApplication<Application>().cacheDir, "tideline_replay.wav")
        f.writeBytes(wav)
        player?.release()
        player = android.media.MediaPlayer().apply {
          setDataSource(f.absolutePath)
          setOnCompletionListener { it.release(); if (player === it) player = null }
          prepare()
          start()
        }
      } catch (t: Throwable) {
        Log.e(TAG, "Replay failed", t)
      }
    }
  }

  // Geometry source for photo-word masks: OCR owns WHERE a word sits in the
  // capture (the VLM's self-reported boxes probe as spatial hallucination),
  // the LLM keeps owning WHAT it says and means.
  private val textRecognizer by lazy {
    TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
  }

  /** OCR the prepared capture and return each term's normalized box as the
   * JSON string the drawer stores ("[x0,y0,x1,y1]"); terms the OCR never saw
   * are absent. Fail-soft: any error means no geometry, never no row. */
  private suspend fun termGeometry(
    prepared: ByteArray,
    terms: List<ImageReply.Term>,
  ): Map<String, String> {
    return try {
      val bitmap = BitmapFactory.decodeByteArray(prepared, 0, prepared.size) ?: return emptyMap()
      val words = ocrWords(textRecognizer, bitmap)
      val boxes = matchTermBoxes(terms.map { it.original }, words, bitmap.width, bitmap.height)
      Log.i(
        TAG,
        "BENCH ocr_words=${words.size} matched=${boxes.size}/${terms.size} " +
          "boxes=${JSONObject(boxes.mapValues { JSONArray(it.value) })}"
      )
      bitmap.recycle()
      boxes.mapValues { JSONArray(it.value).toString() }
    } catch (t: Throwable) {
      Log.e(TAG, "Term geometry failed", t)
      emptyMap()
    }
  }

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
        maybeRunDebugCapture()
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

  /*
   * Dev loop: a fixed image in the app's external files dir runs through the
   * EXACT image→translation pipeline as soon as the engine is ready — so the
   * image path can be iterated over adb without anyone pointing a camera
   * (the camera→translation leg is already verified; what iterates now is
   * image→translation). Queued because the intent arrives before init ends.
   */
  private var pendingDebugImage: String? = null
  private var pendingDebugAudio: String? = null

  fun queueDebugImage(fileName: String) {
    pendingDebugImage = fileName
    maybeRunDebugCapture()
  }

  /** Same dev loop for the audio path: a WAV in the external files dir runs
   * through the exact mic→translation pipeline (sans mic). */
  fun queueDebugAudio(fileName: String) {
    pendingDebugAudio = fileName
    maybeRunDebugCapture()
  }

  private fun maybeRunDebugCapture() {
    if (_ui.value.engineState != EngineState.READY) return
    val imageName = pendingDebugImage
    val audioName = pendingDebugAudio
    pendingDebugImage = null
    pendingDebugAudio = null
    if (imageName == null && audioName == null) return
    if (!beginImageInference()) return
    viewModelScope.launch(Dispatchers.IO) {
      val name = imageName ?: audioName!!
      val file = java.io.File(getApplication<Application>().getExternalFilesDir(null), name)
      val bytes = try {
        file.readBytes()
      } catch (t: Throwable) {
        Log.e(TAG, "Debug capture unreadable: $file", t)
        _ui.value = _ui.value.copy(engineState = EngineState.READY)
        return@launch
      }
      Log.i(TAG, "BENCH debug_capture=$name size=${bytes.size}")
      if (imageName != null) {
        runImageInference(bytes, exifRotationDegrees(bytes))
      } else {
        runAudioInference(bytes, seconds = bytes.size / 32_000)
      }
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
    // TERM lines = the emergence loop's feed: each original=translation pair
    // becomes its own drawer row (the shape promotion/clustering reads),
    // instead of one unpromotable "[image N B]" placeholder. They come LAST so
    // a garbled tail degrades the vocabulary, never the translation the user
    // is waiting on. One TERM per line, deliberately NO "|" separator: the
    // |-spec bled into TRANSLATION ("x | y | z" lists) and that rhythm is a
    // repetition attractor on litertlm E2B — it looped the same words for
    // ~5400 chars / 189 s and never reached SCENE (probe: terms_prompt_probe,
    // line shape 5/5 with natural-sentence translations, |-shape degenerated).
    // The literal example line matters: the on-device quant dropped the
    // "TERM:" prefix and the "= translation" half when given only a format
    // description (it answered bare word lines) — a concrete sample anchors
    // the shape far harder than a spec for a small model.
    val prompt =
      "Look at this image and reply with these lines:\n" +
        "TRANSLATION: all visible text translated to $lang, as one natural " +
        "sentence or phrase (write NONE if there is no text)\n" +
        "SCENE: 5-8 words naming where/what this is — place, activity, or notable objects\n" +
        "Then 1-6 key words from the image worth learning, each on its own " +
        "line exactly like this example:\n" +
        "TERM: Exit = 出口\n" +
        "Skip brand names, logos and proper names — they are not vocabulary."
    dispatchInference(
      contents = Contents.of(listOf(Content.ImageBytes(prepared), Content.Text(prompt))),
      originalLabel = "[image ${prepared.size} B]",
      source = "image",
      lang = lang,
      sourceImage = prepared,
    )
  }

  /*
   * Audio translation — Phase 5b live mic.
   *
   * Tap to record (16 kHz mono WAV, the format the probe verified against
   * the bundled Conformer encoder), tap again to stop and translate: the
   * bytes go straight to the LLM via Content.AudioBytes — no third-party
   * ASR. The reply's TRANSCRIPT line (what was actually said, in the
   * speaker's language) becomes the drawer row's `original`, which is what
   * lets a heard phrase enter the emergence loop; fail-soft to an
   * "[audio Ns]" label when the model skips the marker. Audio precedes text
   * in the contents, mirroring the image path.
   */
  private val recorder = WavRecorder()

  fun toggleRecording() {
    if (recorder.isRecording) {
      val seconds = recorder.seconds()
      val wav = try {
        recorder.stop()
      } catch (t: Throwable) {
        Log.e(TAG, "Mic stop failed", t)
        _ui.value = _ui.value.copy(recording = false, errorMessage = "Recording failed")
        return
      }
      _ui.value = _ui.value.copy(recording = false)
      translateAudio(wav, seconds)
    } else {
      if (_ui.value.engineState != EngineState.READY) return
      try {
        recorder.start()
        _ui.value = _ui.value.copy(recording = true, errorMessage = null)
      } catch (t: Throwable) {
        Log.e(TAG, "Mic start failed", t)
        _ui.value = _ui.value.copy(recording = false, errorMessage = "Mic unavailable")
      }
    }
  }

  private fun translateAudio(wav: ByteArray, seconds: Int) {
    if (!beginImageInference()) return
    runAudioInference(wav, seconds)
  }

  // The literal example anchors the two-line shape (the 5a lesson: a format
  // description alone gets ignored — the first live take came back as
  // "<transcript> 翻译：<chinese>" with no markers at all).
  private fun runAudioInference(wav: ByteArray, seconds: Int) {
    val lang = _ui.value.targetLang
    val prompt =
      "Listen to this audio and reply with exactly three lines like this " +
        "example:\n" +
        "TRANSCRIPT: How much is this?\n" +
        "TRANSLATION: 这个多少钱?\n" +
        "LANGUAGE: English\n" +
        "TRANSCRIPT is the speech exactly as spoken, in its own language; " +
        "TRANSLATION is that speech in $lang; LANGUAGE is the language spoken."
    dispatchInference(
      contents = Contents.of(listOf(Content.AudioBytes(wav), Content.Text(prompt))),
      originalLabel = "[audio ${seconds}s]",
      source = "audio",
      lang = lang,
      sourceAudio = wav,
    )
  }

  /*
   * Shared inference dispatch for every input modality. Caller has already set
   * engineState = INFERRING. Streams tokens into ui.translation, logs the BENCH
   * triple (start / first_token / done), and persists the finished row tagged
   * with `source`. Keeping one body means text and image stay strictly in sync.
   */
  /*
   * Format-compliance retry, engineering-style: when an image pass reads the
   * text fine but skips the TERM lines (single-shot compliance on this quant
   * is photo-dependent — one capture went 2/2 with terms, another 0/3), ask
   * ONCE more in the same conversation. The image is already in context, so
   * the follow-up is text-only (~2 s, no re-encode) and single-task, which
   * complies far better than the three-part ask. Fail-soft: no terms after
   * the retry → the plain summary row sediments as before.
   */
  private fun dispatchTermsRetry(
    translated: String,
    sceneGist: String?,
    originalLabel: String,
    lang: String,
    sourceImage: ByteArray,
  ) {
    val conv = conversation ?: run { finishImagePersist(translated, sceneGist, originalLabel, lang, sourceImage, emptyList()); return }
    val acc = StringBuilder()
    val prompt =
      "Now list 1-6 key words you can see in that image, each on its own " +
        "line exactly like this example:\nTERM: Exit = $lang translation of Exit"
    try {
      conv.sendMessageAsync(
        Contents.of(listOf(Content.Text(prompt))),
        object : MessageCallback {
          override fun onMessage(message: Message) { acc.append(message.toString()) }
          override fun onDone() {
            val terms = parseImageReply(acc.toString().trim(), lang).terms
            Log.i(TAG, "BENCH terms_retry got=${terms.size}")
            finishImagePersist(translated, sceneGist, originalLabel, lang, sourceImage, terms)
          }
          override fun onError(throwable: Throwable) {
            Log.e(TAG, "Terms retry failed", throwable)
            finishImagePersist(translated, sceneGist, originalLabel, lang, sourceImage, emptyList())
          }
        },
        emptyMap(),
      )
    } catch (t: Throwable) {
      Log.e(TAG, "Terms retry send failed", t)
      finishImagePersist(translated, sceneGist, originalLabel, lang, sourceImage, emptyList())
    }
  }

  /** Final leg of an image pass: flip READY, sediment rows, log geometry. */
  private fun finishImagePersist(
    translated: String,
    sceneGist: String?,
    originalLabel: String,
    lang: String,
    sourceImage: ByteArray?,
    terms: List<ImageReply.Term>,
  ) {
    _ui.value = _ui.value.copy(engineState = EngineState.READY, translation = translated)
    viewModelScope.launch(Dispatchers.IO) {
      // Geometry first, so each vocabulary row carries WHERE its word sits in
      // the photo (the toggleable mask's anchor) alongside the photo itself.
      val regions = if (sourceImage != null && terms.isNotEmpty()) {
        termGeometry(sourceImage, terms)
      } else emptyMap()
      val rows = if (terms.isNotEmpty()) {
        terms.map { term ->
          TranslationEntity(
            original = term.original,
            targetLang = lang,
            translated = term.translated,
            source = "image",
            contextSnippet = sceneGist,
            sessionId = currentSessionId(),
            sourceImage = sourceImage,
            sourceRegion = regions[term.original],
            sourceLang = detectScriptLanguage(term.original),
          )
        }
      } else if (translated.isNotEmpty() && translated.length <= MAX_PERSIST_CHARS) {
        listOf(
          TranslationEntity(
            original = originalLabel,
            targetLang = lang,
            translated = translated,
            source = "image",
            contextSnippet = sceneGist,
            sessionId = currentSessionId(),
            sourceImage = sourceImage,
          )
        )
      } else emptyList()
      try {
        rows.forEach { dao.insert(it) }
        emergenceSweep(db.openHelper.writableDatabase)
      } catch (t: Throwable) {
        Log.e(TAG, "Persist translation failed", t)
      }
    }
  }

  private fun dispatchInference(
    contents: Contents,
    originalLabel: String,
    source: String,
    lang: String,
    sourceImage: ByteArray? = null,
    sourceAudio: ByteArray? = null,
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
            // The raw reply is the only way to see HOW the on-device model
            // deviates from the format (the Mac probe passes where the device
            // fails, so the divergence lives in this exact string).
            Log.i(TAG, "BENCH raw=\"${raw.replace("\n", "\\n").take(600)}\"")
            // Image prompt returns marked TRANSLATION / SCENE / TERMS lines;
            // text/audio replies carry no markers and pass through unchanged
            // (gist null, no terms).
            val reply = parseImageReply(raw, lang)
            val translated = reply.translated
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
            // The words are the sediment. An image pass that read text but
            // skipped the TERM lines gets ONE text-only follow-up in the same
            // conversation (the image is still in context) before settling for
            // the summary row; the translation is already on screen while the
            // retry runs. Text/audio keep the original single-row path.
            if (source == "image" && sourceImage != null) {
              if (reply.terms.isEmpty() &&
                translated.isNotEmpty() && !translated.equals("NONE", ignoreCase = true)
              ) {
                _ui.value = _ui.value.copy(translation = translated)
                dispatchTermsRetry(translated, reply.sceneGist, originalLabel, lang, sourceImage)
              } else {
                finishImagePersist(translated, reply.sceneGist, originalLabel, lang, sourceImage, reply.terms)
              }
            } else {
              // Audio: the transcript (what was actually said, in its own
              // language) is the row's original — that's what lets a heard
              // phrase enter the emergence loop. Text keeps its typed input.
              val audio = if (source == "audio") parseAudioReply(raw) else null
              val rowTranslated = audio?.translated ?: translated
              val rowOriginal = audio?.transcript ?: originalLabel
              // The speech's own language: the model's report first, honest
              // script detection as fallback (kana/hangul only — Latin and
              // pure Han stay null rather than guess).
              val rowLang = audio?.language ?: detectScriptLanguage(rowOriginal)
              if (audio != null) {
                Log.i(TAG, "BENCH audio transcript=\"${audio.transcript?.take(80)}\" lang=$rowLang")
              }
              _ui.value = _ui.value.copy(engineState = EngineState.READY, translation = rowTranslated)
              if (rowTranslated.isNotEmpty() && rowTranslated.length <= MAX_PERSIST_CHARS) {
                viewModelScope.launch(Dispatchers.IO) {
                  try {
                    dao.insert(
                      TranslationEntity(
                        original = rowOriginal,
                        targetLang = lang,
                        translated = rowTranslated,
                        source = source,
                        contextSnippet = reply.sceneGist,
                        sessionId = currentSessionId(),
                        sourceAudio = if (source == "audio") sourceAudio else null,
                        sourceLang = rowLang,
                      )
                    )
                    emergenceSweep(db.openHelper.writableDatabase)
                  } catch (t: Throwable) {
                    Log.e(TAG, "Persist translation failed", t)
                  }
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
    try {
      textRecognizer.close()
    } catch (_: Throwable) {}
    try {
      if (recorder.isRecording) recorder.stop()
    } catch (_: Throwable) {}
    try {
      if (ttsReady) tts.shutdown()
    } catch (_: Throwable) {}
    try {
      player?.release()
    } catch (_: Throwable) {}
    conversation = null
    engine = null
    super.onCleared()
  }
}
