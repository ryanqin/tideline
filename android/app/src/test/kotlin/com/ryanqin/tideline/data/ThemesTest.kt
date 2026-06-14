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
    sceneLabel: String? = null,
    sourceLang: String? = "Japanese",
    createdAt: Long = now,
  ) = ThemeRow(
    id = id,
    original = original,
    targetLang = "Chinese",
    translated = translated,
    source = "image",
    contextSnippet = null,
    sessionId = null,
    sourceRegion = null,
    sourceLang = sourceLang,
    createdAt = createdAt,
    hasImage = false,
    hasAudio = false,
    sceneLabel = sceneLabel,
  )

  @Test
  fun `a scene type holding two concepts becomes a scene`() {
    val groups = themeGroups(
      listOf(
        row(1, "ラーメン", "拉面", sceneLabel = "拉面店"),
        row(2, "餃子", "煎饺", sceneLabel = "拉面店"),
      )
    )
    assertEquals(1, groups.size)
    assertEquals("拉面店", groups[0].sceneLabel)
    assertEquals("Japanese", groups[0].sourceLang)
    assertEquals(listOf(1L, 2L), groups[0].members.map { it.id })
  }

  @Test
  fun `words met at the same scene type on different visits cluster as one`() {
    // The cross-visit heart: a station sign one day and a platform sign another
    // both carry the 车站 label, so they gather into one scene type.
    val groups = themeGroups(
      listOf(
        row(1, "出口", "出口", sceneLabel = "车站", createdAt = now - 1000),
        row(2, "切符", "车票", sceneLabel = "车站", createdAt = now - 1000),
        row(3, "地下鉄", "地铁", sceneLabel = "车站", createdAt = now),
      )
    )
    assertEquals(1, groups.size)
    assertEquals(listOf(1L, 2L, 3L), groups[0].members.map { it.id })
  }

  @Test
  fun `a one-concept scene is not a scene`() {
    // The same word re-captured, and a same-language synonym folding onto the
    // same first-language rendering — all one concept, so no scene.
    val groups = themeGroups(
      listOf(
        row(1, "ラーメン", "拉面", sceneLabel = "拉面店"),
        row(2, "ラーメン", "拉面", sceneLabel = "拉面店"),
        row(3, "中華そば", "拉面", sceneLabel = "拉面店"),
      )
    )
    assertTrue(groups.isEmpty())
  }

  @Test
  fun `labelless rows never form scenes`() {
    val groups = themeGroups(
      listOf(
        row(1, "ラーメン", "拉面"),
        row(2, "餃子", "煎饺"),
      )
    )
    assertTrue(groups.isEmpty())
  }

  @Test
  fun `concept edges travel through rows outside the scene`() {
    // Inside 拉面店 the two rows look like two concepts; a labelless row shares
    // its word with one and its rendering with the other, folding them into
    // one concept — the partition is global, like the core's.
    val groups = themeGroups(
      listOf(
        row(1, "中華そば", "拉面", sceneLabel = "拉面店"),
        row(2, "ラーメン", "面条", sceneLabel = "拉面店"),
        row(3, "ラーメン", "拉面"),
      )
    )
    assertTrue(groups.isEmpty())
  }

  @Test
  fun `a concept met at two scene types belongs to both`() {
    val groups = themeGroups(
      listOf(
        row(1, "刺身", "生鱼片", sceneLabel = "寿司店"),
        row(2, "寿司", "寿司", sceneLabel = "寿司店"),
        row(3, "刺身", "生鱼片", sceneLabel = "居酒屋"),
        row(4, "焼き鳥", "烤鸡肉串", sceneLabel = "居酒屋"),
      )
    )
    assertEquals(2, groups.size)
  }

  private fun group(label: String, latestAt: Long) = ThemeGroup(
    sceneLabel = label,
    sourceLang = "Japanese",
    members = listOf(
      row(1, "ラーメン", "拉面", sceneLabel = label, createdAt = latestAt),
      row(2, "餃子", "煎饺", sceneLabel = label, createdAt = latestAt),
    ),
  )

  @Test
  fun `a never-reviewed scene is due by default, a scheduled one waits its turn`() {
    val fresh = group("拉面店", now)
    val resting = group("居酒屋", now)
    val overdue = group("车站", now)
    val states = mapOf(
      "居酒屋" to ThemeReviewEntity("居酒屋", strength = 2, dueAt = now + 1),
      "车站" to ThemeReviewEntity("车站", strength = 2, dueAt = now - 1),
    )
    val due = dueThemes(listOf(fresh, resting, overdue), states, nowMs = now)
    assertEquals(listOf("拉面店", "车站"), due.map { it.group.sceneLabel })
    assertEquals(0, due[0].strength)
    assertNull(due.find { it.group.sceneLabel == "居酒屋" })
  }

  @Test
  fun `the weakest scene washes ashore first, newer scenes breaking ties`() {
    val weakOld = group("旧弱", latestAt = now - 1000)
    val weakNew = group("新弱", latestAt = now)
    val firm = group("熟", latestAt = now)
    val states = mapOf(
      "熟" to ThemeReviewEntity("熟", strength = 3, dueAt = now - 1),
      "旧弱" to ThemeReviewEntity("旧弱", strength = 1, dueAt = now - 1),
      "新弱" to ThemeReviewEntity("新弱", strength = 1, dueAt = now - 1),
    )
    val due = dueThemes(listOf(firm, weakOld, weakNew), states, nowMs = now)
    assertEquals(listOf("新弱", "旧弱", "熟"), due.map { it.group.sceneLabel })
  }
}
