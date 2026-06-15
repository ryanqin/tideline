/*
 * The scene tier — theme grouping, mirrored from the core's cluster.py theme
 * path (DESIGN §3.2/§3.3).
 *
 * A theme is a SCENE TYPE — a kind of place clustered ACROSS visits, keyed on
 * the short scene label the capture model reports (拉面店 / 车站 / 咖啡馆). A
 * label holding >= 2 distinct concepts is a scene; members are every row ever
 * met at that kind of place. The model only categorises (garnish); grouping is
 * exact-match on the label (load-bearing) — clean type separation, only synonym
 * drift between near-labels. Concepts fold by construction like the core's
 * deterministic concept edges: same source word, or same first-language
 * rendering within one source language.
 *
 * Unlike the web there are no materialized cluster tables here — those exist
 * to persist B6 episodic titles, which on the phone wait for a night-watch
 * model. Grouping a personal library is milliseconds of in-memory work, so
 * themes are computed on demand; the only persisted state is the review
 * schedule (theme_reviews, keyed on scene_label — the stable handle a
 * recomputed grouping can't churn). A device DB pulled to the desktop still
 * reads whole: the web's boot sweep rebuilds its own cluster tables and picks
 * the schedule up from theme_reviews.
 */

package com.ryanqin.tideline.data

/** One translation row as the theme tier sees it — no blobs (a session's
 * photos would be real memory); has_image/has_audio say where to fetch them
 * on demand. */
data class ThemeRow(
  val id: Long,
  val original: String,
  val targetLang: String,
  val translated: String,
  val source: String?,
  val contextSnippet: String?,
  val sessionId: String?,
  val sourceRegion: String?,
  val sourceLang: String?,
  val createdAt: Long,
  val hasImage: Boolean,
  val hasAudio: Boolean,
  val sceneLabel: String? = null,
)

/** One scene type: every row met at that kind of place. */
data class ThemeGroup(
  val sceneLabel: String,
  val sourceLang: String?,
  val members: List<ThemeRow>,
  // The night-watch's warm B6 name (洁净之憩); null until the model has named
  // this label. scene_label stays the stable key (glyph seed, review schedule);
  // this is only the caption that surfaces.
  val title: String? = null,
) {
  val latestAt: Long get() = members.maxOf { it.createdAt }

  /** What surfaces to the user: the warm name once named, else the bare scene
   * type (拉面店). Mirrors the web's `title ?: scene_label`. */
  val displayName: String get() = title ?: sceneLabel
}

private class UnionFind {
  private val parent = HashMap<Long, Long>()

  fun find(x: Long): Long {
    var root = parent.getOrPut(x) { x }
    while (parent.getValue(root) != root) root = parent.getValue(root)
    var cur = x
    while (parent.getValue(cur) != root) {
      val next = parent.getValue(cur)
      parent[cur] = root
      cur = next
    }
    return root
  }

  fun union(a: Long, b: Long) {
    val ra = find(a)
    val rb = find(b)
    if (ra != rb) parent[ra] = rb
  }
}

/** Map every row id to its concept representative — the connected components
 * of the deterministic concept edges, over the WHOLE library (an edge through
 * a row outside the session can fold two of its rows into one concept, same
 * as the core's _concept_partition). Bucketing is equivalent to the pairwise
 * predicate's transitive closure without the n² walk. */
fun conceptPartition(rows: List<ThemeRow>): Map<Long, Long> {
  val uf = UnionFind()
  val unionBucket = { bucket: List<ThemeRow> ->
    bucket.zipWithNext().forEach { (a, b) -> uf.union(a.id, b.id) }
  }
  // Same source word (within one target language).
  rows.groupBy { it.original to it.targetLang }.values.forEach(unionBucket)
  // Same first-language rendering within one source language (§3.3 — 駅 and
  // station both render to 车站 but are two language-pairs, never one concept).
  rows.filter { it.translated.isNotEmpty() }
    .groupBy { Triple(it.translated, it.sourceLang ?: "", it.targetLang) }
    .values.forEach(unionBucket)
  return rows.associate { it.id to uf.find(it.id) }
}

/** Group rows into scene types by their model-reported scene_label — every row
 * met at that kind of place, across visits — keeping labels that hold >= 2
 * distinct concepts (a one-concept scene is not a scene). Newest first. (Mirror
 * of core: a label is in the target language, so a café in two source languages
 * could merge — the documented cross-language limitation.) */
fun themeGroups(rows: List<ThemeRow>): List<ThemeGroup> {
  val partition = conceptPartition(rows)
  return rows
    .filter { !it.sceneLabel.isNullOrEmpty() }
    .groupBy { it.sceneLabel!! }
    .mapNotNull { (label, members) ->
      val concepts = members.map { partition[it.id] ?: it.id }.toSet()
      if (concepts.size < 2) null
      else ThemeGroup(
        label,
        members.firstNotNullOfOrNull { it.sourceLang },
        members.sortedBy { it.id },
      )
    }
    .sortedByDescending { it.latestAt }
}

/** A due scene and how firmly it's held. */
data class DueTheme(val group: ThemeGroup, val strength: Int)

/** The scenes the tide should carry ashore now: never-reviewed ones are due
 * by default (strength 0, mirroring a brand-new card), reviewed ones when
 * their due date arrives. Weakest first, newer occasions breaking ties. */
fun dueThemes(
  groups: List<ThemeGroup>,
  states: Map<String, ThemeReviewEntity>,
  nowMs: Long,
): List<DueTheme> =
  groups.mapNotNull { g ->
    val state = states[g.sceneLabel]
    val due = state == null || state.dueAt == null || state.dueAt <= nowMs
    if (due) DueTheme(g, state?.strength ?: 0) else null
  }.sortedWith(compareBy({ it.strength }, { -it.group.latestAt }))
