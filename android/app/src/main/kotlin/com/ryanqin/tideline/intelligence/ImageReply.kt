/*
 * Image-reply parsing — the words are the sediment.
 *
 * The image prompt asks for three marked lines: TRANSLATION (what the user
 * reads now), SCENE (the episodic gist), TERMS (the vocabulary actually met —
 * original=translation pairs). TERMS is what lets a photographed menu enter
 * the emergence loop: each pair becomes its own drawer row, exactly the shape
 * the Python core's promotion/clustering reads. Without it an image capture
 * stored only an "[image N B]" placeholder that could never promote.
 *
 * Parsing is fail-soft at every level (mirrors tideline_engineering_vs_
 * reasoning: the model only garnishes, never load-bears): a missing TERMS
 * line, a NONE, or a malformed pair just yields fewer terms — the
 * translation itself never depends on the model following the format.
 * Text/audio replies carry no markers and pass through unchanged.
 */

package com.ryanqin.tideline.intelligence

private const val MAX_TERMS = 8
private const val MAX_TERM_LENGTH = 60

data class ImageReply(
  val translated: String,
  val sceneGist: String?,
  // Which language the visible text is in, as the model reports it — the
  // image-level source language (one sign / package is usually one language).
  // It backfills a term's source_lang when the deterministic script check
  // can't pin one (Latin words like "Premium" carry no script signal), so the
  // by-language lens and the (日→中) langtag work for photographed words too.
  val language: String?,
  val terms: List<Term>,
  // Structurally sound pairs whose rendering failed the script guard
  // ("Premium = 高 premium"): the word was READ fine, only its translation
  // came back half-borrowed. Worth one single-task follow-up ask each — the
  // bare word translates cleanly ("Premium" → 高级); the half-borrowing is
  // list-context laziness, not ability.
  val retryWorthy: List<String> = emptyList(),
) {
  data class Term(val original: String, val translated: String)
}

/** A speech reply: what was said (foreign text — the drawer's `original`,
 * which is what lets a heard phrase enter the emergence loop), what it means,
 * and which language it was spoken in (picks the TTS voice for the standard
 * pronunciation). Markerless replies pass through as translation-only. */
data class AudioReply(
  val transcript: String?,
  val translated: String,
  val language: String? = null,
)

fun parseAudioReply(raw: String): AudioReply {
  val text = raw.trim()
  val transcriptIdx = text.indexOf("TRANSCRIPT:", ignoreCase = true)
  val translationIdx = text.indexOf("TRANSLATION:", ignoreCase = true)
  if (translationIdx < 0) {
    // The model's most natural deviation (seen on the first live take):
    // "<transcript> 翻译：<chinese>" with no markers. Honor it.
    val zh = Regex("(?:翻译|译文)\\s*[:：]").find(text)
    if (zh != null) {
      val transcript = text.substring(0, zh.range.first).trim().ifBlank { null }
      val translated = text.substring(zh.range.last + 1).trim()
      if (translated.isNotEmpty()) return AudioReply(transcript, translated)
    }
    // No markers at all — the whole reply is the translation (probe shape).
    return AudioReply(transcript = null, translated = text)
  }
  val transcript = if (transcriptIdx >= 0 && transcriptIdx < translationIdx) {
    text.substring(transcriptIdx + "TRANSCRIPT:".length, translationIdx)
      .trim().ifBlank { null }
  } else null
  val translated = text.substring(translationIdx + "TRANSLATION:".length)
    .lineSequence().firstOrNull()?.trim().orEmpty()
  val langIdx = text.indexOf("LANGUAGE:", ignoreCase = true)
  val language = if (langIdx >= 0) {
    text.substring(langIdx + "LANGUAGE:".length)
      .lineSequence().firstOrNull()?.trim()
      // a single capitalized word like "English"/"Japanese"; anything
      // chattier than that is the model rambling, not a language name
      ?.takeIf { it.isNotEmpty() && it.length <= 20 && !it.contains(' ') }
  } else null
  return AudioReply(transcript = transcript, translated = translated, language = language)
}

/** Does the rendering actually live in the target language's script? A weak
 * model sometimes HALF-translates a term ("Premium" → "高 premium"), leaving
 * the source word inside the "meaning" — the exact-echo guard below can't see
 * it, and once sedimented it promotes into a review card that quizzes you on
 * a non-meaning. Same failure family as the core gloss's script-consistency
 * guard: rather wrong-by-absence than wrong-by-content. For a Chinese target:
 * at least one CJK char and zero Latin letters. Targets without a rule pass
 * (honest: no rule, no claim). Internal so the word-fix follow-up holds its
 * answers to the same bar. */
internal fun rendersInTargetScript(translated: String, targetLang: String): Boolean {
  if (!targetLang.equals("Chinese", ignoreCase = true)) return true
  val hasCjk = translated.any { it.code in 0x4E00..0x9FFF }
  val hasLatin = translated.any { it in 'a'..'z' || it in 'A'..'Z' }
  return hasCjk && !hasLatin
}

/** How one "original = translation" segment parsed. */
private sealed interface PairParse {
  data class Ok(val term: ImageReply.Term) : PairParse
  /** Structurally fine, but the rendering failed the script guard — the
   * word itself is worth a single-task follow-up ask. */
  data class HalfTranslated(val original: String) : PairParse
  data object Bad : PairParse
}

private fun parsePair(segment: String, targetLang: String): PairParse {
  val parts = segment.split('=', '→', limit = 2)
  if (parts.size != 2) return PairParse.Bad
  val orig = parts[0].trim()
  val trans = parts[1].trim()
  return when {
    orig.isEmpty() || trans.isEmpty() -> PairParse.Bad
    orig.length > MAX_TERM_LENGTH || trans.length > MAX_TERM_LENGTH -> PairParse.Bad
    // A vocabulary card teaches a WORD: bare numbers / percentages /
    // punctuation ("75%", "99.9%") carry no language to learn — require at
    // least one letter (any script). "75% ALCOHOL" still passes.
    orig.none { it.isLetter() } -> PairParse.Bad
    // A weak model sometimes echoes the format spec itself
    // ("original=translation") instead of filling it in — that must not
    // become a vocabulary row.
    orig.contains("original", ignoreCase = true) ||
      trans.contains("translation", ignoreCase = true) -> PairParse.Bad
    // Half-translations don't sediment — but the word is real; flag it for
    // the follow-up instead of dropping it on the sand.
    !rendersInTargetScript(trans, targetLang) -> PairParse.HalfTranslated(orig)
    else -> PairParse.Ok(ImageReply.Term(orig, trans))
  }
}

fun parseImageReply(raw: String, targetLang: String = "Chinese"): ImageReply {
  val text = raw.trim()
  val sceneIdx = text.indexOf("SCENE:", ignoreCase = true)
  val languageIdx = text.indexOf("LANGUAGE:", ignoreCase = true)
  val termsIdx = text.indexOf("TERMS:", ignoreCase = true)
  val firstTermIdx = Regex("(?im)^\\s*TERM:").find(text)?.range?.first ?: -1

  val cutIdx = listOf(sceneIdx, languageIdx, termsIdx, firstTermIdx)
    .filter { it >= 0 }.minOrNull() ?: text.length
  val translated = text.substring(0, cutIdx)
    .replace(Regex("(?i)TRANSLATION:\\s*"), "")
    .trim()

  val sceneGist = if (sceneIdx >= 0) {
    text.substring(sceneIdx + "SCENE:".length)
      .lineSequence().firstOrNull()
      ?.let { line ->
        // Defensive: a model that crams TERMS / a TERM pair onto the scene
        // line shouldn't leak the pairs into the gist.
        val t = Regex("(?i)TERMS?:").find(line)?.range?.first ?: -1
        (if (t >= 0) line.substring(0, t) else line).trim().ifBlank { null }
      }
  } else null

  // Preferred shape: one "TERM: original = translation" per line. The earlier
  // |-separated single-line spec bled into TRANSLATION (the model answered
  // everything as "x | y | z" lists) and that rhythm is a repetition
  // attractor on-device — litertlm E2B looped the same words for thousands
  // of characters and never reached SCENE/TERMS.
  val lineParses = Regex("(?im)^\\s*TERM:\\s*(.+)$").findAll(text)
    .map { m -> parsePair(m.groupValues[1], targetLang) }
    .toList()

  // Legacy fallback: a single "TERMS: a=b | c=d" line.
  val inlineParses = if (termsIdx >= 0) {
    val line = text.substring(termsIdx + "TERMS:".length)
      .lineSequence().firstOrNull()?.trim().orEmpty()
    if (line.equals("NONE", ignoreCase = true)) emptyList()
    else line.split('|', ';').map { parsePair(it, targetLang) }
  } else emptyList()

  // The image-level source language: a single capitalized word like
  // "English"/"Japanese" (same shape and guard as the audio LANGUAGE line);
  // anything chattier is the model rambling, not a language name.
  val language = if (languageIdx >= 0) {
    text.substring(languageIdx + "LANGUAGE:".length)
      .lineSequence().firstOrNull()?.trim()
      ?.takeIf { it.isNotEmpty() && it.length <= 20 && !it.contains(' ') }
  } else null

  // Per-line TERM rows win when they carry anything real (a half-translated
  // row counts: the format WAS followed, only the rendering needs the fix).
  val chosen = if (lineParses.any { it !is PairParse.Bad }) lineParses else inlineParses
  val terms = chosen.filterIsInstance<PairParse.Ok>().map { it.term }
    .distinctBy { it.original }
    .take(MAX_TERMS)
  val retryWorthy = chosen.filterIsInstance<PairParse.HalfTranslated>().map { it.original }
    .distinct()
    .filter { o -> terms.none { it.original == o } }
    .take(MAX_TERMS)

  return ImageReply(
    translated = translated, sceneGist = sceneGist, language = language,
    terms = terms, retryWorthy = retryWorthy,
  )
}
