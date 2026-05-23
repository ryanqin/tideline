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

  @Query("SELECT * FROM translations ORDER BY id DESC LIMIT $LATEST_LIMIT")
  fun observeLatest(): Flow<List<TranslationEntity>>

  @Query("SELECT COUNT(*) FROM translations")
  suspend fun count(): Int
}
