package com.ryanqin.tideline.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ThemesTest {

  private val now = 1_700_000_000_000L

  private fun row(
    id: Long,
    original: String,
    translated: String,
    sessionId: String? = null,
    sourceLang: String? = "Japanese",
    createdAt: Long = now,
  ) = ThemeRow(
    id = id,
    original = original,
    targetLang = "Chinese",
    translated = translated,
    source = "text",
    contextSnippet = null,
    sessionId = sessionId,
    sourceRegion = null,
    sourceLang = sourceLang,
    createdAt = createdAt,
    hasImage = false,
    hasAudio = false,
  )

  @Test
  fun `a session holding two concepts becomes a scene`() {
    val groups = themeGroups(
      listOf(
        row(1, "ラーメン", "拉面", sessionId = "s1"),
        row(2, "餃子", "煎饺", sessionId = "s1"),
      )
    )
    assertEquals(1, groups.size)
    assertEquals("s1", groups[0].sessionId)
    assertEquals("Japanese", groups[0].sourceLang)
    assertEquals(listOf(1L, 2L), groups[0].members.map { it.id })
  }

  @Test
  fun `a one-concept session is not a scene`() {
    // The same word re-captured, and a same-language synonym folding onto the
    // same first-language rendering — all one concept, so no scene.
    val groups = themeGroups(
      listOf(
        row(1, "ラーメン", "拉面", sessionId = "s1"),
        row(2, "ラーメン", "拉面", sessionId = "s1"),
        row(3, "中華そば", "拉面", sessionId = "s1"),
      )
    )
    assertTrue(groups.isEmpty())
  }

  @Test
  fun `a mixed-language sitting splits into one scene per language`() {
    val groups = themeGroups(
      listOf(
        row(1, "ラーメン", "拉面", sessionId = "s1", sourceLang = "Japanese"),
        row(2, "餃子", "煎饺", sessionId = "s1", sourceLang = "Japanese"),
        row(3, "café", "咖啡馆", sessionId = "s1", sourceLang = "French"),
        row(4, "thé", "茶", sessionId = "s1", sourceLang = "French"),
      )
    )
    assertEquals(2, groups.size)
    assertEquals(setOf("Japanese", "French"), groups.map { it.sourceLang }.toSet())
    groups.forEach { assertEquals("s1", it.sessionId) }
  }

  @Test
  fun `sessionless rows never form scenes`() {
    val groups = themeGroups(
      listOf(
        row(1, "ラーメン", "拉面"),
        row(2, "餃子", "煎饺"),
      )
    )
    assertTrue(groups.isEmpty())
  }

  @Test
  fun `concept edges travel through rows outside the session`() {
    // Inside s1 the two rows look like two concepts; a sessionless row shares
    // its word with one and its rendering with the other, folding them into
    // one concept — the partition is global, like the core's.
    val groups = themeGroups(
      listOf(
        row(1, "中華そば", "拉面", sessionId = "s1"),
        row(2, "ラーメン", "面条", sessionId = "s1"),
        row(3, "ラーメン", "拉面"),
      )
    )
    assertTrue(groups.isEmpty())
  }

  @Test
  fun `same rendering in two languages stays two concepts`() {
    // 駅 and station both render to 车站 but are two language-pairs (§3.3) —
    // inside one (deliberately mixed) session they stay distinct concepts,
    // but each language bucket holds only one, so neither forms a scene.
    val groups = themeGroups(
      listOf(
        row(1, "駅", "车站", sessionId = "s1", sourceLang = "Japanese"),
        row(2, "station", "车站", sessionId = "s1", sourceLang = "English"),
      )
    )
    assertTrue(groups.isEmpty())
  }

  private fun group(sessionId: String, latestAt: Long) = ThemeGroup(
    sessionId = sessionId,
    sourceLang = "Japanese",
    members = listOf(
      row(1, "ラーメン", "拉面", sessionId = sessionId, createdAt = latestAt),
      row(2, "餃子", "煎饺", sessionId = sessionId, createdAt = latestAt),
    ),
  )

  @Test
  fun `a never-reviewed scene is due by default, a scheduled one waits its turn`() {
    val fresh = group("fresh", now)
    val resting = group("resting", now)
    val overdue = group("overdue", now)
    val states = mapOf(
      "resting" to ThemeReviewEntity("resting", strength = 2, dueAt = now + 1),
      "overdue" to ThemeReviewEntity("overdue", strength = 2, dueAt = now - 1),
    )
    val due = dueThemes(listOf(fresh, resting, overdue), states, nowMs = now)
    assertEquals(listOf("fresh", "overdue"), due.map { it.group.sessionId })
    assertEquals(0, due[0].strength)
    assertNull(due.find { it.group.sessionId == "resting" })
  }

  @Test
  fun `the weakest scene washes ashore first, newer occasions breaking ties`() {
    val weakOld = group("weak-old", latestAt = now - 1000)
    val weakNew = group("weak-new", latestAt = now)
    val firm = group("firm", latestAt = now)
    val states = mapOf(
      "firm" to ThemeReviewEntity("firm", strength = 3, dueAt = now - 1),
      "weak-old" to ThemeReviewEntity("weak-old", strength = 1, dueAt = now - 1),
      "weak-new" to ThemeReviewEntity("weak-new", strength = 1, dueAt = now - 1),
    )
    val due = dueThemes(listOf(firm, weakOld, weakNew), states, nowMs = now)
    assertEquals(listOf("weak-new", "weak-old", "firm"), due.map { it.group.sessionId })
  }
}
