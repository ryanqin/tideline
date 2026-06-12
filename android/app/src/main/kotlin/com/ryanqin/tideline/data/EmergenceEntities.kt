/*
 * Emergence-tier tables — column-for-column mirrors of the Python core
 * (tools/candidate.py + tools/card.py), so a device DB pulled to the desktop
 * reads identically there. Timestamps are epoch millis on Android (same
 * convention as translations.created_at).
 *
 * candidates: drawer entries whose occurrence count crossed the night-watch
 * threshold. cards: the review deck — auto-generated from candidates
 * (opt-out: the user curates by sinking), carrying the spaced-repetition
 * schedule (strength / due_at / reviews).
 */

package com.ryanqin.tideline.data

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
  tableName = "candidates",
  indices = [Index(value = ["original", "target_lang"], unique = true)],
)
data class CandidateEntity(
  @PrimaryKey(autoGenerate = true) val id: Long = 0,
  @ColumnInfo(name = "original") val original: String,
  @ColumnInfo(name = "target_lang") val targetLang: String,
  @ColumnInfo(name = "translated") val translated: String,
  @ColumnInfo(name = "occurrence_count") val occurrenceCount: Int,
  @ColumnInfo(name = "first_seen_at") val firstSeenAt: Long,
  @ColumnInfo(name = "last_seen_at") val lastSeenAt: Long,
  @ColumnInfo(name = "promoted_at") val promotedAt: Long = System.currentTimeMillis(),
)

@Entity(
  tableName = "candidate_evidence",
  primaryKeys = ["candidate_id", "translation_id"],
  foreignKeys = [
    ForeignKey(
      entity = CandidateEntity::class,
      parentColumns = ["id"], childColumns = ["candidate_id"],
      onDelete = ForeignKey.CASCADE,
    ),
    ForeignKey(
      entity = TranslationEntity::class,
      parentColumns = ["id"], childColumns = ["translation_id"],
      onDelete = ForeignKey.CASCADE,
    ),
  ],
  indices = [Index("candidate_id"), Index("translation_id")],
)
data class CandidateEvidenceEntity(
  @ColumnInfo(name = "candidate_id") val candidateId: Long,
  @ColumnInfo(name = "translation_id") val translationId: Long,
  @ColumnInfo(name = "recorded_at") val recordedAt: Long = System.currentTimeMillis(),
)

@Entity(
  tableName = "cards",
  foreignKeys = [
    ForeignKey(
      entity = CandidateEntity::class,
      parentColumns = ["id"], childColumns = ["candidate_id"],
      onDelete = ForeignKey.CASCADE,
    ),
  ],
  indices = [Index(value = ["candidate_id"], unique = true)],
)
data class CardEntity(
  @PrimaryKey(autoGenerate = true) val id: Long = 0,
  @ColumnInfo(name = "candidate_id") val candidateId: Long,
  @ColumnInfo(name = "original") val original: String,
  @ColumnInfo(name = "target_lang") val targetLang: String,
  @ColumnInfo(name = "translated") val translated: String,
  // 'active' (in the review deck) or 'sunk' (curated away, never resurfaced)
  @ColumnInfo(name = "state") val state: String = "active",
  @ColumnInfo(name = "strength") val strength: Int = 0,
  // null = brand new, i.e. ready for its first review
  @ColumnInfo(name = "due_at") val dueAt: Long? = null,
  @ColumnInfo(name = "last_reviewed_at") val lastReviewedAt: Long? = null,
  @ColumnInfo(name = "reviews") val reviews: Int = 0,
  @ColumnInfo(name = "created_at") val createdAt: Long = System.currentTimeMillis(),
)
