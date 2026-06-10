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

fun parseImageReply(raw: String): ImageReply {
  val text = raw.trim()
  val sceneIdx = text.indexOf("SCENE:", ignoreCase = true)
  val termsIdx = text.indexOf("TERMS:", ignoreCase = true)

  val cutIdx = listOf(sceneIdx, termsIdx).filter { it >= 0 }.minOrNull() ?: text.length
  val translated = text.substring(0, cutIdx)
    .replace(Regex("(?i)TRANSLATION:\\s*"), "")
    .trim()

  val sceneGist = if (sceneIdx >= 0) {
    text.substring(sceneIdx + "SCENE:".length)
      .lineSequence().firstOrNull()
      ?.let { line ->
        // Defensive: a model that crams TERMS onto the scene line shouldn't
        // leak the pairs into the gist.
        val t = line.indexOf("TERMS:", ignoreCase = true)
        (if (t >= 0) line.substring(0, t) else line).trim().ifBlank { null }
      }
  } else null

  val terms = if (termsIdx >= 0) {
    val line = text.substring(termsIdx + "TERMS:".length)
      .lineSequence().firstOrNull()?.trim().orEmpty()
    if (line.equals("NONE", ignoreCase = true)) emptyList()
    else line.split('|', ';')
      .mapNotNull { seg ->
        val parts = seg.split('=', '→', limit = 2)
        if (parts.size != 2) return@mapNotNull null
        val orig = parts[0].trim()
        val trans = parts[1].trim()
        if (orig.isEmpty() || trans.isEmpty()) null
        else if (orig.length > MAX_TERM_LENGTH || trans.length > MAX_TERM_LENGTH) null
        // A weak model sometimes echoes the format spec itself
        // ("original=translation") instead of filling it in — that must not
        // become a vocabulary row.
        else if (orig.contains("original", ignoreCase = true) ||
          trans.contains("translation", ignoreCase = true)) null
        else ImageReply.Term(orig, trans)
      }
      .distinctBy { it.original }
      .take(MAX_TERMS)
  } else emptyList()

  return ImageReply(translated = translated, sceneGist = sceneGist, terms = terms)
}
