/*
 * Tideline drawer row.
 *
 * Mirrors `translations` table in tideline/core/src/tideline/tools/translation.py
 * column-for-column (with created_at stored as epoch millis on Android since
 * Room doesn't have a TIMESTAMP-with-default type). Same column names keep
 * future export/import between the Python core and Android shell straightforward.
 */

package com.ryanqin.tideline.data

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

@Suppress("ArrayInDataClass")
@Entity(tableName = "translations")
data class TranslationEntity(
  @PrimaryKey(autoGenerate = true) val id: Long = 0,
  @ColumnInfo(name = "original") val original: String,
  @ColumnInfo(name = "target_lang") val targetLang: String,
  @ColumnInfo(name = "translated") val translated: String,
  // text / image / audio — Phase 3 only emits "text"; image/audio land in Phase 5+.
  @ColumnInfo(name = "source") val source: String? = "text",
  // Surrounding text from OCR / transcript. null for keyboard input.
  @ColumnInfo(name = "context_snippet") val contextSnippet: String? = null,
  // Tideline 原意是"一次外出绑组",MVP 用 app 启动 UUID 顶替。Phase 5d 再做真情景边界。
  @ColumnInfo(name = "session_id") val sessionId: String? = null,
  // The captured photo itself (prepared/downscaled JPEG) — recall material,
  // kept after the VLM reads it. Mirrors Python core's source_image BLOB
  // (§3.2); null for text/audio captures.
  @ColumnInfo(name = "source_image", typeAffinity = ColumnInfo.BLOB)
  val sourceImage: ByteArray? = null,
  @ColumnInfo(name = "created_at") val createdAt: Long = System.currentTimeMillis(),
)
