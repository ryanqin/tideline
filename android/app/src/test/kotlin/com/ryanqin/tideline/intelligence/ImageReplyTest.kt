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
    val pairs = (1..12).joinToString(" | ") { "词$it=t$it" } + " | 词1=重复"
    val reply = parseImageReply("TRANSLATION: x\nSCENE: y\nTERMS: $pairs")
    assertEquals(8, reply.terms.size)
    assertEquals("t1", reply.terms.first { it.original == "词1" }.translated)
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
  fun `translation survives a garbled terms tail`() {
    val reply = parseImageReply(
      "TRANSLATION: 完整的翻译内容\nSCENE: 居酒屋\nTERMS: 焼き鳥="
    )
    assertEquals("完整的翻译内容", reply.translated)
    assertEquals("居酒屋", reply.sceneGist)
    assertTrue(reply.terms.isEmpty())
  }
}
