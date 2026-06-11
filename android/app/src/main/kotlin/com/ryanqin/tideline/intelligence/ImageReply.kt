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
  val terms: List<Term>,
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

/** One "original = translation" pair → a Term, or null when malformed. */
private fun termFromPair(segment: String): ImageReply.Term? {
  val parts = segment.split('=', '→', limit = 2)
  if (parts.size != 2) return null
  val orig = parts[0].trim()
  val trans = parts[1].trim()
  return when {
    orig.isEmpty() || trans.isEmpty() -> null
    orig.length > MAX_TERM_LENGTH || trans.length > MAX_TERM_LENGTH -> null
    // A weak model sometimes echoes the format spec itself
    // ("original=translation") instead of filling it in — that must not
    // become a vocabulary row.
    orig.contains("original", ignoreCase = true) ||
      trans.contains("translation", ignoreCase = true) -> null
    else -> ImageReply.Term(orig, trans)
  }
}

fun parseImageReply(raw: String): ImageReply {
  val text = raw.trim()
  val sceneIdx = text.indexOf("SCENE:", ignoreCase = true)
  val termsIdx = text.indexOf("TERMS:", ignoreCase = true)
  val firstTermIdx = Regex("(?im)^\\s*TERM:").find(text)?.range?.first ?: -1

  val cutIdx = listOf(sceneIdx, termsIdx, firstTermIdx)
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
  val lineTerms = Regex("(?im)^\\s*TERM:\\s*(.+)$").findAll(text)
    .mapNotNull { m -> termFromPair(m.groupValues[1]) }
    .toList()

  // Legacy fallback: a single "TERMS: a=b | c=d" line.
  val inlineTerms = if (termsIdx >= 0) {
    val line = text.substring(termsIdx + "TERMS:".length)
      .lineSequence().firstOrNull()?.trim().orEmpty()
    if (line.equals("NONE", ignoreCase = true)) emptyList()
    else line.split('|', ';').mapNotNull { termFromPair(it) }
  } else emptyList()

  val terms = lineTerms.ifEmpty { inlineTerms }
    .distinctBy { it.original }
    .take(MAX_TERMS)

  return ImageReply(translated = translated, sceneGist = sceneGist, terms = terms)
}
