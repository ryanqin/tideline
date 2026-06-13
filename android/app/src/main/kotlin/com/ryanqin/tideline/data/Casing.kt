/*
 * Casing normalization — mirror of core promotion.py's canonical_word.
 *
 * "Lowercase except proper nouns": a shouted common noun on a package
 * (PREMIUM, ALCOHOL) becomes its lemma (premium, alcohol) so it stops
 * splitting into two candidates and two review cards, while a short all-caps
 * acronym (NASA, USB) or an internally-capitalised name (iPhone) keeps its
 * casing, and a word with no ASCII-cased letters (CJK, kana) is untouched.
 *
 * Deterministic and idempotent, so it keys the candidates table directly. A
 * garnish-level heuristic (proper-noun detection is fuzzy) — the model already
 * skips proper names, and a miss here is only cosmetic.
 */

package com.ryanqin.tideline.data

fun canonicalWord(word: String): String {
  val letters = word.filter { it.code < 128 && it.isLetter() }
  if (letters.isEmpty()) return word
  // an internal uppercase (an upper right after a lower): iPhone, McD, eBay
  for (i in 1 until word.length) {
    if (word[i].isUpperCase() && word[i - 1].isLowerCase()) return word
  }
  // a short all-caps acronym keeps its shout: NASA, USB, EU
  if (letters.length <= 4 && letters.all { it.isUpperCase() }) return word
  return word.lowercase()
}
