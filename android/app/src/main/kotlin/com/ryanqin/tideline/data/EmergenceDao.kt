/*
 * Review-deck queries. The due ordering mirrors core's due_cards: brand-new
 * cards (NULL due_at) first, then most overdue — that's what the tide
 * carries ashore first. The schedule itself stays internal (DESIGN §10.3):
 * nothing here surfaces counts or dates to the user.
 */

package com.ryanqin.tideline.data

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface EmergenceDao {

  // New cards (NULL due) first, then most overdue; among equally-new cards
  // the words met most often come first — without the tiebreak the order
  // degraded to GROUP BY's alphabetical accident ("75%" sorting before
  // ALCOHOL on a wipes package).
  @Query(
    "SELECT cards.* FROM cards " +
      "JOIN candidates ON candidates.id = cards.candidate_id " +
      "WHERE cards.state = 'active' " +
      "AND (cards.due_at IS NULL OR cards.due_at <= :nowMs) " +
      "ORDER BY cards.due_at IS NULL DESC, cards.due_at ASC, " +
      "candidates.occurrence_count DESC, cards.id DESC LIMIT :limit"
  )
  suspend fun dueCards(nowMs: Long, limit: Int = 20): List<CardEntity>

  @Query(
    "UPDATE cards SET strength = :strength, due_at = :dueAt, " +
      "last_reviewed_at = :nowMs, reviews = reviews + 1 WHERE id = :cardId"
  )
  suspend fun applyReview(cardId: Long, strength: Int, dueAt: Long, nowMs: Long)

  @Query("SELECT strength FROM cards WHERE id = :cardId")
  suspend fun cardStrength(cardId: Long): Int?

  @Query("UPDATE cards SET state = 'sunk' WHERE id = :cardId")
  suspend fun sinkCard(cardId: Long)

  /** A card's lived moments — the captures it grew from (photos, regions,
   * recordings ride along for the review screen). */
  @Query(
    "SELECT t.* FROM translations t " +
      "JOIN candidate_evidence ce ON ce.translation_id = t.id " +
      "JOIN cards c ON c.candidate_id = ce.candidate_id " +
      "WHERE c.id = :cardId ORDER BY t.created_at"
  )
  suspend fun cardMoments(cardId: Long): List<TranslationEntity>

  // --- the scene tier -------------------------------------------------------

  /** Every row, blobs left behind — theme grouping reads the whole library
   * (the concept partition is global), so photos/recordings are flagged and
   * fetched on demand instead. */
  @Query(
    "SELECT id, original, target_lang AS targetLang, translated, source, " +
      "context_snippet AS contextSnippet, session_id AS sessionId, " +
      "source_region AS sourceRegion, source_lang AS sourceLang, " +
      "created_at AS createdAt, " +
      "source_image IS NOT NULL AS hasImage, " +
      "source_audio IS NOT NULL AS hasAudio " +
      "FROM translations"
  )
  suspend fun themeRows(): List<ThemeRow>

  /** Every active card with the language its evidence was met in — the
   * museum's cards lens. The language is derived from the card's moments
   * (cards mirror core's schema, which keeps language on the translations). */
  @Query(
    "SELECT c.*, " +
      "(SELECT t.source_lang FROM translations t " +
      " JOIN candidate_evidence ce ON ce.translation_id = t.id " +
      " WHERE ce.candidate_id = c.candidate_id AND t.source_lang IS NOT NULL " +
      " ORDER BY t.id LIMIT 1) AS sourceLang " +
      "FROM cards c WHERE c.state = 'active' ORDER BY c.created_at DESC"
  )
  suspend fun museumCards(): List<MuseumCard>

  @Query("SELECT * FROM theme_reviews")
  suspend fun themeReviewStates(): List<ThemeReviewEntity>

  @Query("SELECT * FROM theme_reviews WHERE session_id = :sessionId")
  suspend fun themeReview(sessionId: String): ThemeReviewEntity?

  @Insert(onConflict = OnConflictStrategy.REPLACE)
  suspend fun upsertThemeReview(row: ThemeReviewEntity)
}
