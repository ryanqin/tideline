/*
 * Deterministic script → language detection, mirroring the Python core's
 * detect_script honesty rule: ONLY scripts that pin a language unambiguously
 * get an answer (kana → Japanese, hangul → Korean). Pure Han is ambiguous
 * (Chinese / Japanese kanji) and Latin spans dozens of languages — both stay
 * null rather than guess; the model's own report (audio LANGUAGE line) or the
 * web's real-model sweep fills those in.
 */

package com.ryanqin.tideline.intelligence

fun detectScriptLanguage(text: String): String? {
  var sawHangul = false
  var sawKana = false
  for (ch in text) {
    val code = ch.code
    when {
      code in 0x3040..0x30FF || code in 0x31F0..0x31FF -> sawKana = true   // hiragana/katakana
      code in 0xAC00..0xD7AF || code in 0x1100..0x11FF -> sawHangul = true // hangul
    }
  }
  return when {
    sawKana -> "Japanese"
    sawHangul -> "Korean"
    else -> null
  }
}
