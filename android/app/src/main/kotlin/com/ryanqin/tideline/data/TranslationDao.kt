/*
 * Translation DAO.
 *
 * Recent-first ordering by id matches Python core's CLI list (which orders by
 * implicit ROWID). Cap at LATEST_LIMIT for the UI; if portfolio demos need
 * more history later, paging or count APIs can be added then.
 */

package com.ryanqin.tideline.data

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

private const val LATEST_LIMIT = 50

@Dao
interface TranslationDao {

  @Insert
  suspend fun insert(entity: TranslationEntity): Long

  // NULL out source_image in the list the UI observes: the history view only
  // renders text, and 50 rows x a few hundred KB of JPEG per emission is real
  // memory. Fetch a row's photo on demand instead when a detail view needs it.
  @Query(
    "SELECT id, original, target_lang, translated, source, context_snippet, " +
      "session_id, NULL AS source_image, source_region, created_at " +
      "FROM translations ORDER BY id DESC LIMIT $LATEST_LIMIT"
  )
  fun observeLatest(): Flow<List<TranslationEntity>>

  @Query("SELECT source_image FROM translations WHERE id = :id")
  suspend fun imageFor(id: Long): ByteArray?

  @Query("SELECT COUNT(*) FROM translations")
  suspend fun count(): Int
}
