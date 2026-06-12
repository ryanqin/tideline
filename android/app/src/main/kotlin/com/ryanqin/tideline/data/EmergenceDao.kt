/*
 * Review-deck queries. The due ordering mirrors core's due_cards: brand-new
 * cards (NULL due_at) first, then most overdue — that's what the tide
 * carries ashore first. The schedule itself stays internal (DESIGN §10.3):
 * nothing here surfaces counts or dates to the user.
 */

package com.ryanqin.tideline.data

import androidx.room.Dao
import androidx.room.Query

@Dao
interface EmergenceDao {

  @Query(
    "SELECT * FROM cards WHERE state = 'active' " +
      "AND (due_at IS NULL OR due_at <= :nowMs) " +
      "ORDER BY due_at IS NULL DESC, due_at ASC LIMIT :limit"
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
}
