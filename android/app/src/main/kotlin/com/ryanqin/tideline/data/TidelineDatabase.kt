/*
 * Tideline Room database — single-table v1.
 *
 * fallbackToDestructiveMigration is fine for a dev build (no real user data
 * to protect yet); turn on real migrations from the first portfolio-stable
 * release onward if/when we keep user data.
 */

package com.ryanqin.tideline.data

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(entities = [TranslationEntity::class], version = 1, exportSchema = false)
abstract class TidelineDatabase : RoomDatabase() {

  abstract fun translationDao(): TranslationDao

  companion object {
    @Volatile
    private var instance: TidelineDatabase? = null

    fun get(context: Context): TidelineDatabase {
      return instance ?: synchronized(this) {
        instance ?: Room.databaseBuilder(
          context.applicationContext,
          TidelineDatabase::class.java,
          "tideline.db",
        )
          .fallbackToDestructiveMigration(dropAllTables = true)
          .build()
          .also { instance = it }
      }
    }
  }
}
