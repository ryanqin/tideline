package com.ryanqin.tideline.data

import org.junit.Assert.assertEquals
import org.junit.Test

/** Mirror of core test_step6b's canonical_word checks — same rule, both ends. */
class CasingTest {

  @Test
  fun `lowercases shouted common nouns, keeps proper nouns, leaves CJK alone`() {
    assertEquals("premium", canonicalWord("PREMIUM"))
    assertEquals("premium", canonicalWord("Premium"))
    assertEquals("alcohol", canonicalWord("ALCOHOL"))
    assertEquals("germs", canonicalWord("germs"))
    // likely proper nouns keep their casing
    assertEquals("NASA", canonicalWord("NASA"))      // short all-caps acronym
    assertEquals("iPhone", canonicalWord("iPhone"))  // internal uppercase
    // no ASCII-cased letters → untouched
    assertEquals("ラーメン", canonicalWord("ラーメン"))
    assertEquals("拉面", canonicalWord("拉面"))
    // idempotent
    assertEquals("premium", canonicalWord(canonicalWord("PREMIUM")))
  }

  // --- heal merge logic (mergeCardStates) — mirror of core heal_casing_splits

  @Test
  fun `merged casing card keeps the strongest progress`() {
    val merged = mergeCardStates(
      listOf(
        CardState(1, "active", strength = 3, dueAt = 100L, lastReviewedAt = 50L, reviews = 5),
        CardState(2, "active", strength = 1, dueAt = 200L, lastReviewedAt = 60L, reviews = 1),
      )
    )!!
    // strongest box wins, so a word you already knew never goes back to new
    assertEquals(3, merged.strength)
    assertEquals(5, merged.reviews)
    assertEquals(100L, merged.dueAt)   // the strong card's schedule, kept whole
    assertEquals("active", merged.state)
  }

  @Test
  fun `merged casing card is active if any variant is active`() {
    val merged = mergeCardStates(
      listOf(
        CardState(1, "sunk", 2, null, null, 2),
        CardState(2, "active", 0, null, null, 0),
      )
    )!!
    assertEquals("active", merged.state)
  }

  @Test
  fun `merged casing card stays sunk only if every variant was sunk`() {
    val merged = mergeCardStates(
      listOf(
        CardState(1, "sunk", 2, null, null, 2),
        CardState(2, "sunk", 0, null, null, 0),
      )
    )!!
    assertEquals("sunk", merged.state)
  }

  @Test
  fun `merging no cards is null`() {
    assertEquals(null, mergeCardStates(emptyList()))
  }
}
