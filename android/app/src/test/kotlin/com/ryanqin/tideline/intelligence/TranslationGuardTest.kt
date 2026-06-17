package com.ryanqin.tideline.intelligence

import org.junit.Assert.assertEquals
import org.junit.Test

class TranslationGuardTest {

  @Test
  fun `a real foreign to native translation passes`() {
    assertEquals(
      TranslationOutcome.TRANSLATED,
      judgeTranslation("こんにちは", "你好", "Japanese", "Chinese"),
    )
    // French (Latin) → Chinese, the fr_cheese case
    assertEquals(
      TranslationOutcome.TRANSLATED,
      judgeTranslation("OFFRE SPECIALE", "特价优惠", "French", "Chinese"),
    )
  }

  @Test
  fun `model reading the source as the native language is same-language`() {
    // jp_exit: 非常口 read (wrongly) as Chinese, image so no text source
    assertEquals(
      TranslationOutcome.SAME_AS_NATIVE,
      judgeTranslation(null, "非常口 非常口", "Chinese", "Chinese"),
    )
    // spelling variants of the native language still match
    assertEquals(
      TranslationOutcome.SAME_AS_NATIVE,
      judgeTranslation(null, "你好", "中文", "Chinese"),
    )
    assertEquals(
      TranslationOutcome.SAME_AS_NATIVE,
      judgeTranslation(null, "你好", "zh", "Chinese"),
    )
  }

  @Test
  fun `an echoed source is not translated`() {
    // typed Chinese sentence comes back unchanged
    assertEquals(
      TranslationOutcome.NOT_TRANSLATED,
      judgeTranslation("你好世界", "你好世界", null, "Chinese"),
    )
    // punctuation / spacing differences still read as an echo
    assertEquals(
      TranslationOutcome.NOT_TRANSLATED,
      judgeTranslation("これは日本語です", "これは日本語です。", null, "Chinese"),
    )
  }

  @Test
  fun `a blank translation is not translated`() {
    assertEquals(
      TranslationOutcome.NOT_TRANSLATED,
      judgeTranslation("hello", "", "English", "Chinese"),
    )
  }

  @Test
  fun `an image with no text source relies on the reported language`() {
    // source null (image); reported French → passes through
    assertEquals(
      TranslationOutcome.TRANSLATED,
      judgeTranslation(null, "特价优惠", "French", "Chinese"),
    )
  }

  @Test
  fun `a short same-glyph word is not falsely flagged as an echo`() {
    // 寿司 is identical in Japanese and Chinese — a legit translation, must pass
    assertEquals(
      TranslationOutcome.TRANSLATED,
      judgeTranslation("寿司", "寿司", null, "Chinese"),
    )
    // a 1-char source translating to a 2-char native word
    assertEquals(
      TranslationOutcome.TRANSLATED,
      judgeTranslation("駅", "车站", "Japanese", "Chinese"),
    )
  }
}
