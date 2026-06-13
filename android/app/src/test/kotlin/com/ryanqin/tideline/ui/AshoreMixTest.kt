package com.ryanqin.tideline.ui

import com.ryanqin.tideline.data.CardEntity
import com.ryanqin.tideline.data.ThemeGroup
import com.ryanqin.tideline.data.ThemeRow
import org.junit.Assert.assertEquals
import org.junit.Test

class AshoreMixTest {

  private fun word(id: Long, original: String) = ReviewItem.Word(
    CardEntity(
      id = id, candidateId = id, original = original,
      targetLang = "Chinese", translated = "义$id", createdAt = 0L,
    )
  )

  private fun scene(sessionId: String, vararg originals: String) = ReviewItem.Scene(
    ThemeGroup(
      sessionId = sessionId,
      sourceLang = "English",
      members = originals.mapIndexed { i, o ->
        ThemeRow(
          id = i + 100L, original = o, targetLang = "Chinese", translated = "义$o",
          source = "image", contextSnippet = null, sessionId = sessionId,
          sourceRegion = null, sourceLang = "English", createdAt = 0L,
          hasImage = false, hasAudio = false,
        )
      },
    ),
    strength = 0,
  )

  @Test
  fun `a word covered by an ashore scene folds into it`() {
    val mix = ashoreMix(
      listOf(
        word(1, "Alcohol"), word(2, "Wipes"), word(3, "駅"),
        scene("s1", "Alcohol", "Wipes"),
      )
    )
    // the scene represents Alcohol and Wipes; only the uncovered word remains
    assertEquals(
      listOf("s:s1", "w:駅"),
      mix.map { if (it is ReviewItem.Scene) "s:${it.group.sessionId}" else "w:${(it as ReviewItem.Word).card.original}" },
    )
  }

  @Test
  fun `with no scenes due the beach is all words, as before`() {
    val mix = ashoreMix((1L..7L).map { word(it, "w$it") })
    assertEquals(ASHORE, mix.size)
    assertEquals(listOf("w1", "w2", "w3", "w4", "w5"), mix.map { (it as ReviewItem.Word).card.original })
  }

  @Test
  fun `at most two scenes wash up and words fill the rest`() {
    val mix = ashoreMix(
      listOf(
        scene("s1", "a"), scene("s2", "b"), scene("s3", "c"),
        word(1, "x"), word(2, "y"), word(3, "z"), word(4, "q"),
      )
    )
    assertEquals(5, mix.size)
    assertEquals(2, mix.count { it is ReviewItem.Scene })
    assertEquals(listOf("x", "y", "z"), mix.filterIsInstance<ReviewItem.Word>().map { it.card.original })
  }

  @Test
  fun `an occasion that covers every due word holds the beach alone`() {
    val mix = ashoreMix(
      listOf(
        word(1, "Alcohol"), word(2, "Wipes"),
        scene("s1", "Alcohol", "Wipes"),
        scene("s2", "Alcohol", "Wipes"),
      )
    )
    assertEquals(2, mix.size)
    assertEquals(2, mix.count { it is ReviewItem.Scene })
  }
}
