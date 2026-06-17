/*
 * Translation guard — did a real foreign → your-language translation happen?
 *
 * Tideline only translates INTO your first language (DESIGN §3.3); a
 * "same-language" translation isn't a real use case. When the on-device model
 * hits its edge — the source was already your language, or it just echoed the
 * source without translating it — there is no useful result to show. Rather
 * than surface a wrong / no-op "translation", judge it here so the UI can say,
 * honestly, that this one was beyond reach — and skip sedimenting it, so the
 * emergence loop is never fed garbage. Mirrors tideline_engineering_vs_
 * reasoning: fail empty, never fail with a wrong answer.
 *
 * Known limit: a source in Han characters the model labels as Japanese yet
 * leaves untranslated (国産茶 → 国産茶) can't be caught by script — Japanese
 * kanji and Chinese share glyphs, so on-device there's no signal that "茶葉" is
 * unrendered Japanese rather than Chinese. Guard catches the cases the model
 * itself flags (source read as the native language) and plain echoes.
 *
 * Pure Kotlin (no Android deps) so the judgement is unit-tested.
 */

package com.ryanqin.tideline.intelligence

enum class TranslationOutcome {
  /** A real foreign → native translation; show it and let it sediment. */
  TRANSLATED,

  /** The source is (or was read as) the reader's own language — nothing to do. */
  SAME_AS_NATIVE,

  /** The model echoed the source; no translation landed. */
  NOT_TRANSLATED,
}

/** Judge whether a real translation into [nativeLang] happened. [source] is the
 * input we have text for (typed text / audio transcript; null for an image,
 * whose "source" is pixels). [reportedLang] is the model's LANGUAGE line
 * (image / audio; null for typed text). */
fun judgeTranslation(
  source: String?,
  translated: String,
  reportedLang: String?,
  nativeLang: String,
): TranslationOutcome {
  if (translated.isBlank()) return TranslationOutcome.NOT_TRANSLATED
  // 1. The model says the source is already the reader's language.
  if (reportedLang != null && sameLanguage(reportedLang, nativeLang)) {
    return TranslationOutcome.SAME_AS_NATIVE
  }
  // 2. The output still essentially IS the input — the model echoed it.
  if (source != null && looksUntranslated(source, translated)) {
    return TranslationOutcome.NOT_TRANSLATED
  }
  return TranslationOutcome.TRANSLATED
}

private fun sameLanguage(a: String, b: String): Boolean {
  val na = canonLang(a)
  return na.isNotEmpty() && na == canonLang(b)
}

// Fold common spellings of a language to one token, so the model's "Chinese" /
// "中文" / "zh" all match the native-language setting.
private fun canonLang(s: String): String {
  val t = s.trim().lowercase()
  return when {
    t.contains("chinese") || t.contains("mandarin") || t.contains("中文") ||
      t.contains("汉语") || t == "zh" || t.startsWith("zh-") -> "chinese"
    t.contains("japanese") || t.contains("日本") || t == "ja" -> "japanese"
    t.contains("korean") || t.contains("한국") || t == "ko" -> "korean"
    t.contains("english") || t == "en" -> "english"
    t.contains("french") || t.contains("français") || t == "fr" -> "french"
    else -> t
  }
}

/** The translation still mostly IS the source — the model echoed it instead of
 * translating. Compares on letters/digits only (punctuation and spacing don't
 * count), so "非常口 非常口" vs "非常口非常口" still reads as an echo. */
private fun looksUntranslated(source: String, translated: String): Boolean {
  val a = normalizeForCompare(source)
  val b = normalizeForCompare(translated)
  // Require a few characters before calling it an echo, so a short same-glyph
  // word (寿司 is identical in Japanese and Chinese — a legit term) is never
  // mistaken for a non-translation.
  if (a.length < 4 || b.isEmpty()) return false
  if (a == b) return true
  // One fully contains the other's content (a longer echo with extra noise).
  val shorter = if (a.length <= b.length) a else b
  val longer = if (a.length <= b.length) b else a
  return shorter.length >= 4 && longer.contains(shorter)
}

private fun normalizeForCompare(s: String): String =
  buildString { for (c in s) if (c.isLetterOrDigit()) append(c.lowercaseChar()) }
