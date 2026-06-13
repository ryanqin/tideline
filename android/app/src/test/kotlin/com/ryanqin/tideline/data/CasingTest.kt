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
}
