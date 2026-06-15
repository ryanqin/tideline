package com.ryanqin.tideline.intelligence

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class SceneNamingTest {

  @Test
  fun `a clean name passes straight through`() {
    assertEquals("暖汤馆", parseSceneName("暖汤馆"))
  }

  @Test
  fun `the first non-empty line wins`() {
    assertEquals("站途暖", parseSceneName("\n  \n站途暖\n这是因为...\n"))
  }

  @Test
  fun `english and chinese preambles are stripped`() {
    assertEquals("暖汤馆", parseSceneName("Name: 暖汤馆"))
    assertEquals("暖汤馆", parseSceneName("名字：暖汤馆"))
    assertEquals("暖汤馆", parseSceneName("名称: 暖汤馆"))
  }

  @Test
  fun `surrounding quotes and brackets are removed (half and full width)`() {
    assertEquals("暖汤馆", parseSceneName("\"暖汤馆\""))
    assertEquals("暖汤馆", parseSceneName("「暖汤馆」"))
    assertEquals("暖汤馆", parseSceneName("“暖汤馆”"))
    assertEquals("暖汤馆", parseSceneName("**暖汤馆**"))
  }

  @Test
  fun `empty or unparseable replies yield null (caller keeps the bare label)`() {
    assertNull(parseSceneName(null))
    assertNull(parseSceneName(""))
    assertNull(parseSceneName("   \n  \n"))
    assertNull(parseSceneName("「」"))
  }

  @Test
  fun `a rambling answer is capped, not dropped`() {
    val rambled = "这家店让我想起了很多很多温暖的回忆和故事"
    val name = parseSceneName(rambled)!!
    assertTrue("kept the head within the cap", name.length <= 12)
    assertTrue(rambled.startsWith(name))
  }

  @Test
  fun `the scene prompt carries the label, the words and the first language`() {
    val prompt = buildScenePrompt("拉面店", listOf("拉面", "煎饺", "酱油"), "Chinese")
    assertTrue(prompt.contains("「拉面店」"))
    assertTrue(prompt.contains("拉面、煎饺、酱油"))
    assertTrue(prompt.contains("Chinese"))
  }

  @Test
  fun `the scene prompt caps the word list at eight`() {
    val terms = (1..12).map { "词$it" }
    val prompt = buildScenePrompt("书店", terms, "Chinese")
    assertTrue(prompt.contains("词8"))
    assertTrue("the ninth word is dropped", !prompt.contains("词9"))
  }

  @Test
  fun `a blank label or first language is a programming error`() {
    assertThrows(IllegalArgumentException::class.java) {
      buildScenePrompt("", listOf("拉面"), "Chinese")
    }
    assertThrows(IllegalArgumentException::class.java) {
      buildScenePrompt("拉面店", listOf("拉面"), " ")
    }
  }
}
