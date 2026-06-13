/*
 * Museum grouping — the browse tier, pure functions over what the drawer
 * holds. Mirrors the web museum's three lenses (DESIGN §10):
 *  - cards: active cards folded by (rendering, source language) — same-
 *    language synonyms shelve as one meaning (拉面 ← 中華そば / ラーメン),
 *    different languages stay separate shelves (§3.3: one language pair).
 *  - languages: every word met, bucketed by the language it was met in —
 *    "the foreign languages I've encountered" axis.
 *  - themes: the occasions (Themes.kt's grouping, browsed instead of quizzed).
 *
 * Browsing is not a quiz: nothing here is masked or graded. The museum shows
 * what washed up; the shore (review) is where you reach for meanings.
 */

package com.ryanqin.tideline.data

import androidx.room.Embedded

/** An active card plus the language its evidence was met in (derived from the
 * card's moments — cards mirror core's schema, which has no language column;
 * the language lives on the translations). */
data class MuseumCard(
  @Embedded val card: CardEntity,
  val sourceLang: String?,
)

/** One museum shelf tile: a meaning and every same-language word that
 * carried it. */
data class CardGroup(
  val translated: String,
  val sourceLang: String?,
  val cards: List<MuseumCard>,
)

/** Fold active cards by (rendering, source language) — the web cards lens. */
fun cardGroups(cards: List<MuseumCard>): List<CardGroup> =
  cards.groupBy { it.card.translated to (it.sourceLang ?: "") }
    .map { (key, group) ->
      CardGroup(
        translated = key.first,
        sourceLang = key.second.ifEmpty { null },
        cards = group.sortedBy { it.card.id },
      )
    }
    .sortedByDescending { g -> g.cards.maxOf { it.card.createdAt } }

/** One word as the language lens shows it: the foreign form, how many times
 * it was met, and its card id when it matured into one (tappable). */
data class LangWord(
  val original: String,
  val count: Int,
  val cardId: Long?,
)

/** One language bucket: the words met in that language, most-met first. */
data class LangBucket(
  val lang: String?,
  val words: List<LangWord>,
)

/** Everything the museum shows, gathered in one read. */
data class MuseumData(
  val cardGroups: List<CardGroup>,
  val langBuckets: List<LangBucket>,
  val scenes: List<ThemeGroup>,
)

/** Bucket every drawer row by the language it was met in — the web
 * by-language lens. Unknown-language rows gather under null (shown last). */
fun langBuckets(rows: List<ThemeRow>, cards: List<MuseumCard>): List<LangBucket> {
  val cardByWord = cards.associateBy { it.card.original to it.card.targetLang }
  return rows.groupBy { it.sourceLang }
    .map { (lang, bucket) ->
      // Fold case so PREMIUM and Premium are one tile (the canonical word the
      // card carries too) — never the same word shown twice.
      val words = bucket.groupBy { canonicalWord(it.original) }
        .map { (original, met) ->
          LangWord(
            original = original,
            count = met.size,
            cardId = cardByWord[original to met.first().targetLang]?.card?.id,
          )
        }
        .sortedWith(compareByDescending<LangWord> { it.count }.thenBy { it.original })
      LangBucket(lang, words)
    }
    .sortedWith(compareBy({ it.lang == null }, { -it.words.sumOf { w -> w.count } }))
}
