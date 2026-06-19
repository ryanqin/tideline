/*
 * The emergence sweep + spaced repetition, on the phone.
 *
 * Logic mirrored 1:1 from the Python core (promotion.py / tools/card.py):
 *  - drawer entries met in >= threshold distinct OCCASIONS (sessions)
 *    promote to candidates (UPSERT keyed on (original, target_lang) — the id
 *    stays stable so evidence survives). Counting sessions, not rows, keeps
 *    a re-photographed package from inflating every word on it at once.
 *  - every contributing translation links via candidate_evidence
 *  - every candidate auto-promotes to an active card (opt-out: INSERT OR
 *    IGNORE on candidate_id is the whole "a sunk card never resurfaces"
 *    mechanism)
 *  - reviews walk the same Leitner ladder as the core
 *
 * All deterministic SQL — the night-watch needs no model and runs in
 * milliseconds, so it sweeps at startup AND after every capture (the same
 * live-sweep shape the web grew in core).
 */

package com.ryanqin.tideline.data

import androidx.sqlite.db.SupportSQLiteDatabase

const val PROMOTION_THRESHOLD = 3

// Mirror of core _REVIEW_INTERVALS_DAYS — strength indexes this ladder.
val REVIEW_INTERVALS_DAYS = intArrayOf(0, 1, 3, 7, 16, 35, 75)

private const val DAY_MS = 24L * 60 * 60 * 1000

/** Leitner step: remembered climbs a box (longer interval), forgotten drops
 * one (comes back sooner). Returns (new strength, new due_at millis). */
fun reschedule(strength: Int, remembered: Boolean, nowMs: Long): Pair<Int, Long> {
  val maxBox = REVIEW_INTERVALS_DAYS.size - 1
  val next = if (remembered) minOf(strength + 1, maxBox) else maxOf(strength - 1, 0)
  return next to nowMs + REVIEW_INTERVALS_DAYS[next] * DAY_MS
}

/** A card's review state, for merging casing variants. */
internal data class CardState(
  val candidateId: Long,
  val state: String,
  val strength: Int,
  val dueAt: Long?,
  val lastReviewedAt: Long?,
  val reviews: Int,
)

/** The review state to carry onto a merged casing group: the strongest box
 * wins (don't make a known word new again), tie-broken by reviews then
 * recency; active unless every casing was sunk — sinking one casing of a word
 * shouldn't bury a kept one. Mirror of core heal_casing_splits. Pure, so the
 * decision is unit-tested without a DB. */
internal fun mergeCardStates(cards: List<CardState>): CardState? {
  if (cards.isEmpty()) return null
  val best = cards.maxWith(
    compareBy({ it.strength }, { it.reviews }, { it.lastReviewedAt ?: Long.MIN_VALUE })
  )
  return best.copy(state = if (cards.all { it.state == "sunk" }) "sunk" else "active")
}

/** Collapse candidates that split on casing before canonicalWord keyed the
 * table — "PREMIUM" and "Premium" promoted as two candidates + two cards under
 * an older build. Mirror of core promotion.heal_casing_splits: each
 * (canonical, target_lang) group folds onto one canonical candidate carrying
 * the strongest review progress; counts and evidence are left for the promote
 * step below to re-derive (it groups case-insensitively). The lossless
 * alternative to a destructive reinstall. Runs inside emergenceSweep's
 * transaction ahead of the upsert; idempotent and a no-op once healed. */
private fun healCasingSplits(db: SupportSQLiteDatabase) {
  data class Member(val id: Long, val original: String)
  val groups = LinkedHashMap<Pair<String, String>, MutableList<Member>>()
  db.query("SELECT id, original, target_lang FROM candidates").use { c ->
    while (c.moveToNext()) {
      groups.getOrPut(canonicalWord(c.getString(1)) to c.getString(2)) { mutableListOf() }
        .add(Member(c.getLong(0), c.getString(1)))
    }
  }
  for ((key, members) in groups) {
    val canon = key.first
    if (members.size == 1 && members[0].original == canon) continue
    val ids = members.map { it.id }
    // survivor: the row already canonical, else rename the lowest id
    var survivor = members.firstOrNull { it.original == canon }?.id
    if (survivor == null) {
      survivor = ids.minOrNull()!!
      db.execSQL("UPDATE candidates SET original = ? WHERE id = ?", arrayOf<Any?>(canon, survivor))
    }
    // carry the strongest progress onto the survivor's card (cards exist from a
    // prior sweep's auto-promote — the very rows we're healing)
    val placeholders = ids.joinToString(",") { "?" }
    val cards = mutableListOf<CardState>()
    db.query(
      "SELECT candidate_id, state, strength, due_at, last_reviewed_at, reviews " +
        "FROM cards WHERE candidate_id IN ($placeholders)",
      ids.toTypedArray(),
    ).use { c ->
      while (c.moveToNext()) {
        cards.add(
          CardState(
            c.getLong(0), c.getString(1), c.getInt(2),
            if (c.isNull(3)) null else c.getLong(3),
            if (c.isNull(4)) null else c.getLong(4),
            c.getInt(5),
          )
        )
      }
    }
    mergeCardStates(cards)?.let { m ->
      db.execSQL(
        "UPDATE cards SET original = ?, state = ?, strength = ?, due_at = ?, " +
          "last_reviewed_at = ?, reviews = ? WHERE candidate_id = ?",
        arrayOf<Any?>(canon, m.state, m.strength, m.dueAt, m.lastReviewedAt, m.reviews, survivor),
      )
    }
    val dups = ids.filter { it != survivor }
    if (dups.isNotEmpty()) {
      val dupPh = dups.joinToString(",") { "?" }
      val dupArr = dups.toTypedArray()
      db.execSQL("DELETE FROM cards WHERE candidate_id IN ($dupPh)", dupArr)
      db.execSQL("DELETE FROM candidate_evidence WHERE candidate_id IN ($dupPh)", dupArr)
      db.execSQL("DELETE FROM candidates WHERE id IN ($dupPh)", dupArr)
    }
  }
}

/** The night-watch, in milliseconds: promote drawer→candidates→cards. */
fun emergenceSweep(db: SupportSQLiteDatabase, nowMs: Long = System.currentTimeMillis()) {
  db.beginTransaction()
  try {
    // Heal any casing splits an older build left (PREMIUM vs Premium as two
    // candidates) before re-deriving counts on the one canonical row.
    healCasingSplits(db)
    // drawer → candidates (UPSERT keeps ids stable; count/last_seen refresh).
    // Group case-insensitively (COLLATE NOCASE) so PREMIUM and Premium count
    // as ONE word's occasions, then store the display casing canonicalised
    // (lowercase except proper nouns) — so the candidate's UNIQUE(original) key
    // is stable. SQLite can't call canonicalWord mid-query, so read the merged
    // groups and UPSERT each (mirrors core's fetch-transform-executemany).
    db.query(
      """
      SELECT
          original,
          target_lang,
          (SELECT translated FROM translations t2
           WHERE t2.original = t.original COLLATE NOCASE
             AND t2.target_lang = t.target_lang
           ORDER BY id DESC LIMIT 1),
          COUNT(*),
          MIN(created_at),
          MAX(created_at)
      FROM translations t
      GROUP BY original COLLATE NOCASE, target_lang
      HAVING COUNT(DISTINCT COALESCE(session_id, 'row#' || id)) >= $PROMOTION_THRESHOLD
      """
    ).use { c ->
      while (c.moveToNext()) {
        db.execSQL(
          """
          INSERT INTO candidates
              (original, target_lang, translated, occurrence_count,
               first_seen_at, last_seen_at, promoted_at)
          VALUES (?, ?, ?, ?, ?, ?, ?)
          ON CONFLICT(original, target_lang) DO UPDATE SET
              translated = excluded.translated,
              occurrence_count = excluded.occurrence_count,
              last_seen_at = excluded.last_seen_at
          """,
          arrayOf(
            canonicalWord(c.getString(0)),
            c.getString(1),
            c.getString(2),
            c.getLong(3),
            c.getLong(4),
            c.getLong(5),
            nowMs,
          ),
        )
      }
    }
    // evidence back-links (idempotent on the composite key) — case-insensitive,
    // since the candidate's stored original is canonical ("premium") while the
    // drawer keeps each row as met ("PREMIUM").
    db.execSQL(
      """
      INSERT OR IGNORE INTO candidate_evidence (candidate_id, translation_id, recorded_at)
      SELECT c.id, t.id, $nowMs
      FROM candidates c
      JOIN translations t
        ON t.original = c.original COLLATE NOCASE
       AND t.target_lang = c.target_lang
      """
    )
    // candidates → active cards (opt-out; sunk cards never resurrect)
    db.execSQL(
      """
      INSERT OR IGNORE INTO cards
          (candidate_id, original, target_lang, translated,
           state, strength, reviews, created_at)
      SELECT id, original, target_lang, translated, 'active', 0, 0, $nowMs
      FROM candidates
      """
    )
    // A card is the candidate's projection, not a snapshot: when a later
    // capture (or a word-fix retry) improves the rendering, the card's
    // meaning follows. Without this a card frozen at creation keeps quizzing
    // an old translation after the drawer has moved on.
    db.execSQL(
      """
      UPDATE cards SET translated =
          (SELECT translated FROM candidates WHERE candidates.id = cards.candidate_id)
      WHERE translated <>
          (SELECT translated FROM candidates WHERE candidates.id = cards.candidate_id)
      """
    )
    db.setTransactionSuccessful()
  } finally {
    db.endTransaction()
  }
}
