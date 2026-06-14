package com.ryanqin.tideline.intelligence

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ImageReplyTest {

  @Test
  fun `full three-line reply parses translation, gist and terms`() {
    val reply = parseImageReply(
      "TRANSLATION: 拉面 800日元\n" +
        "SCENE: 深夜拉面店的菜单\n" +
        "TERMS: ラーメン=拉面 | 醤油=酱油"
    )
    assertEquals("拉面 800日元", reply.translated)
    assertEquals("深夜拉面店的菜单", reply.sceneGist)
    assertEquals(
      listOf(
        ImageReply.Term("ラーメン", "拉面"),
        ImageReply.Term("醤油", "酱油"),
      ),
      reply.terms,
    )
  }

  @Test
  fun `terms NONE yields no terms`() {
    val reply = parseImageReply(
      "TRANSLATION: NONE\nSCENE: 海边的日落\nTERMS: NONE"
    )
    assertEquals("海边的日落", reply.sceneGist)
    assertTrue(reply.terms.isEmpty())
  }

  @Test
  fun `markerless reply passes through unchanged (text and audio paths)`() {
    val reply = parseImageReply("こんにちは")
    assertEquals("こんにちは", reply.translated)
    assertNull(reply.sceneGist)
    assertTrue(reply.terms.isEmpty())
  }

  @Test
  fun `malformed term segments are dropped, valid ones kept`() {
    val reply = parseImageReply(
      "TRANSLATION: 菜单\nSCENE: 餐厅\nTERMS: 駅=车站 | 没有等号的片段 | =缺原文 | 缺译文="
    )
    assertEquals(listOf(ImageReply.Term("駅", "车站")), reply.terms)
  }

  @Test
  fun `terms deduplicate by original and cap at eight`() {
    val pairs = (1..12).joinToString(" | ") { "词$it=译$it" } + " | 词1=重复"
    val reply = parseImageReply("TRANSLATION: x\nSCENE: y\nTERMS: $pairs")
    assertEquals(8, reply.terms.size)
    assertEquals("译1", reply.terms.first { it.original == "词1" }.translated)
  }

  @Test
  fun `a half-translation never sediments — the rendering must live in the target script`() {
    // The live failure: E2B rendered "Premium" as 高 premium — a borrowed
    // word inside the "meaning". CJK-only renderings pass; mixed ones are
    // flagged for the single-task word fix instead of sedimenting.
    val reply = parseImageReply(
      "TRANSLATION: 杀菌湿巾\nSCENE: 包装\n" +
        "TERM: Premium = 高 premium\n" +
        "TERM: Alcohol = 酒精\n" +
        "TERM: Wipes = wipes\n" +
        "TERM: 75% ALCOHOL = 75%酒精"
    )
    assertEquals(listOf("Alcohol", "75% ALCOHOL"), reply.terms.map { it.original })
    assertEquals(listOf("Premium", "Wipes"), reply.retryWorthy)
  }

  @Test
  fun `a row whose word already sedimented cleanly is not retried`() {
    // The same word twice, one clean one half-borrowed: the clean rendering
    // wins, no follow-up needed.
    val reply = parseImageReply(
      "TRANSLATION: x\nTERM: Premium = 优质\nTERM: Premium = 高 premium"
    )
    assertEquals(listOf(ImageReply.Term("Premium", "优质")), reply.terms)
    assertEquals(emptyList<String>(), reply.retryWorthy)
  }

  @Test
  fun `targets without a script rule pass renderings through`() {
    val reply = parseImageReply(
      "TRANSLATION: x\nTERM: 出口 = exit",
      targetLang = "English",
    )
    assertEquals(listOf(ImageReply.Term("出口", "exit")), reply.terms)
  }

  @Test
  fun `terms crammed onto the scene line do not leak into the gist`() {
    val reply = parseImageReply(
      "TRANSLATION: x\nSCENE: 车站大厅 TERMS: 駅=车站"
    )
    assertEquals("车站大厅", reply.sceneGist)
    assertEquals(listOf(ImageReply.Term("駅", "车站")), reply.terms)
  }

  @Test
  fun `line-per-term shape parses and stays out of the translation`() {
    val reply = parseImageReply(
      "TRANSLATION: 高级酒精消毒湿巾\n" +
        "SCENE: 酒精湿巾包装\n" +
        "TERM: ALCOHOL = 酒精\n" +
        "TERM: HAND SANITIZING WIPES = 手部消毒湿巾"
    )
    assertEquals("高级酒精消毒湿巾", reply.translated)
    assertEquals("酒精湿巾包装", reply.sceneGist)
    assertEquals(
      listOf(
        ImageReply.Term("ALCOHOL", "酒精"),
        ImageReply.Term("HAND SANITIZING WIPES", "手部消毒湿巾"),
      ),
      reply.terms,
    )
  }

  @Test
  fun `term lines without a scene marker do not pollute the translation`() {
    val reply = parseImageReply(
      "TRANSLATION: 出口在右边\nTERM: Exit = 出口"
    )
    assertEquals("出口在右边", reply.translated)
    assertNull(reply.sceneGist)
    assertEquals(listOf(ImageReply.Term("Exit", "出口")), reply.terms)
  }

  @Test
  fun `bare numbers and symbols are not vocabulary`() {
    val reply = parseImageReply(
      "TRANSLATION: x\nSCENE: y\n" +
        "TERM: 75% = 75%\nTERM: 99.9% = 99.9%\nTERM: 75% ALCOHOL = 75%酒精\nTERM: 駅 = 车站"
    )
    assertEquals(
      listOf(
        ImageReply.Term("75% ALCOHOL", "75%酒精"),
        ImageReply.Term("駅", "车站"),
      ),
      reply.terms,
    )
  }

  @Test
  fun `echoed format spec is rejected, not stored as a term`() {
    val reply = parseImageReply(
      "TRANSLATION: x\nSCENE: y\nTERMS: original=translation | 駅=车站 | the original word=译文"
    )
    assertEquals(listOf(ImageReply.Term("駅", "车站")), reply.terms)
  }

  @Test
  fun `arrow separator is accepted inside a pair`() {
    val reply = parseImageReply("TRANSLATION: x\nSCENE: y\nTERMS: métro→地铁")
    assertEquals(listOf(ImageReply.Term("métro", "地铁")), reply.terms)
  }

  @Test
  fun `audio reply parses transcript and translation`() {
    val reply = parseAudioReply(
      "TRANSCRIPT: Where is the station?\nTRANSLATION: 车站在哪里?"
    )
    assertEquals("Where is the station?", reply.transcript)
    assertEquals("车站在哪里?", reply.translated)
  }

  @Test
  fun `audio reply without markers is translation-only`() {
    val reply = parseAudioReply("车站在哪里?")
    assertNull(reply.transcript)
    assertEquals("车站在哪里?", reply.translated)
  }

  @Test
  fun `audio reply carries the reported language`() {
    val reply = parseAudioReply(
      "TRANSCRIPT: Where is the station?\nTRANSLATION: 车站在哪里?\nLANGUAGE: English"
    )
    assertEquals("English", reply.language)
    assertEquals("车站在哪里?", reply.translated)
  }

  @Test
  fun `rambling language line is rejected`() {
    val reply = parseAudioReply(
      "TRANSCRIPT: x\nTRANSLATION: y\nLANGUAGE: The speaker is using English"
    )
    assertNull(reply.language)
  }

  @Test
  fun `script detection answers only unambiguous scripts`() {
    assertEquals("Japanese", detectScriptLanguage("ラーメン"))
    assertEquals("Japanese", detectScriptLanguage("駅はどこ"))
    assertEquals("Korean", detectScriptLanguage("안녕하세요"))
    assertNull(detectScriptLanguage("ALCOHOL"))
    assertNull(detectScriptLanguage("拉面"))
  }

  @Test
  fun `audio reply honors the natural 翻译-separator deviation`() {
    val reply = parseAudioReply(
      "Where is the nearest train station?\n翻译：最近的火车站在哪里?"
    )
    assertEquals("Where is the nearest train station?", reply.transcript)
    assertEquals("最近的火车站在哪里?", reply.translated)
  }

  @Test
  fun `audio reply with translation marker only keeps null transcript`() {
    val reply = parseAudioReply("TRANSLATION: 你好")
    assertNull(reply.transcript)
    assertEquals("你好", reply.translated)
  }

  @Test
  fun `translation survives a garbled terms tail`() {
    val reply = parseImageReply(
      "TRANSLATION: 完整的翻译内容\nSCENE: 居酒屋\nTERMS: 焼き鳥="
    )
    assertEquals("完整的翻译内容", reply.translated)
    assertEquals("居酒屋", reply.sceneGist)
    assertTrue(reply.terms.isEmpty())
  }

  @Test
  fun `the LANGUAGE line is parsed and never bleeds into translation or terms`() {
    val reply = parseImageReply(
      "TRANSLATION: 杀菌湿巾\nSCENE: 包装\nLANGUAGE: English\n" +
        "TERM: Alcohol = 酒精\nTERM: Wipes = 湿巾"
    )
    assertEquals("English", reply.language)
    assertEquals("杀菌湿巾", reply.translated)
    assertEquals("包装", reply.sceneGist)
    assertEquals(listOf("Alcohol", "Wipes"), reply.terms.map { it.original })
  }

  @Test
  fun `a chatty LANGUAGE line is rejected as not a language name`() {
    val reply = parseImageReply(
      "TRANSLATION: x\nLANGUAGE: the text appears to be English\nTERM: Exit = 出口"
    )
    assertNull(reply.language)
    assertEquals(listOf("Exit"), reply.terms.map { it.original })
  }

  @Test
  fun `no LANGUAGE line leaves language null`() {
    val reply = parseImageReply("TRANSLATION: 菜单\nSCENE: 餐厅\nTERM: 駅 = 车站")
    assertNull(reply.language)
  }

  @Test
  fun `SCENE_TYPE is parsed and kept distinct from SCENE, never bleeding into terms`() {
    val reply = parseImageReply(
      "TRANSLATION: 拉面 800日元\nSCENE: 深夜拉面横丁的购票机\nSCENE_TYPE: 拉面店\n" +
        "LANGUAGE: Japanese\nTERM: ラーメン = 拉面\nTERM: 餃子 = 煎饺"
    )
    assertEquals("拉面店", reply.sceneType)
    assertEquals("深夜拉面横丁的购票机", reply.sceneGist)  // the two markers don't collide
    assertEquals("拉面 800日元", reply.translated)
    assertEquals(listOf("ラーメン", "餃子"), reply.terms.map { it.original })
  }

  @Test
  fun `no SCENE_TYPE line leaves sceneType null`() {
    val reply = parseImageReply("TRANSLATION: x\nSCENE: 餐厅\nTERM: 駅 = 车站")
    assertNull(reply.sceneType)
  }
}
