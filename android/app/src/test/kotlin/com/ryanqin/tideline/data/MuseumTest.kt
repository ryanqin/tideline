package com.ryanqin.tideline.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class MuseumTest {

  private val now = 1_700_000_000_000L

  private fun card(
    id: Long,
    original: String,
    translated: String,
    sourceLang: String? = "Japanese",
    createdAt: Long = now,
  ) = MuseumCard(
    card = CardEntity(
      id = id, candidateId = id, original = original, targetLang = "Chinese",
      translated = translated, createdAt = createdAt,
    ),
    sourceLang = sourceLang,
  )

  private fun row(
    id: Long,
    original: String,
    translated: String = "义$id",
    sourceLang: String? = "Japanese",
  ) = ThemeRow(
    id = id, original = original, targetLang = "Chinese", translated = translated,
    source = "text", contextSnippet = null, sessionId = null, sourceRegion = null,
    sourceLang = sourceLang, createdAt = now, hasImage = false, hasAudio = false,
  )

  @Test
  fun `same-language synonyms shelve as one meaning, languages stay apart`() {
    val groups = cardGroups(
      listOf(
        card(1, "ラーメン", "拉面"),
        card(2, "中華そば", "拉面"),
        card(3, "métro", "地铁", sourceLang = "French"),
        card(4, "地下鉄", "地铁"),
      )
    )
    assertEquals(3, groups.size)
    val ramen = groups.first { it.translated == "拉面" }
    assertEquals(listOf("ラーメン", "中華そば"), ramen.cards.map { it.card.original })
    // 地铁 from two languages = two shelves (§3.3)
    assertEquals(2, groups.count { it.translated == "地铁" })
  }

  @Test
  fun `language buckets count encounters and point at matured cards`() {
    val cards = listOf(card(7, "ラーメン", "拉面"))
    val buckets = langBuckets(
      listOf(
        row(1, "ラーメン"), row(2, "ラーメン"), row(3, "駅"),
        row(4, "mystery", sourceLang = null),
      ),
      cards,
    )
    assertEquals(listOf("Japanese", null), buckets.map { it.lang })
    val ja = buckets[0]
    assertEquals(listOf("ラーメン", "駅"), ja.words.map { it.original })
    assertEquals(2, ja.words[0].count)
    assertEquals(7L, ja.words[0].cardId)
    assertNull(ja.words[1].cardId)
  }

  @Test
  fun `case variants of a word fold into one tile, displayed canonical`() {
    val cards = listOf(card(9, "premium", "高级", sourceLang = "English"))
    val buckets = langBuckets(
      listOf(
        row(1, "PREMIUM", sourceLang = "English"),
        row(2, "Premium", sourceLang = "English"),
        row(3, "ALCOHOL", sourceLang = "English"),
      ),
      cards,
    )
    val en = buckets.first { it.lang == "English" }
    // PREMIUM + Premium = one canonical "premium" tile (count 2), pointing at
    // the matured card; ALCOHOL folds to "alcohol".
    assertEquals(listOf("premium", "alcohol"), en.words.map { it.original })
    assertEquals(2, en.words[0].count)
    assertEquals(9L, en.words[0].cardId)
  }
}
