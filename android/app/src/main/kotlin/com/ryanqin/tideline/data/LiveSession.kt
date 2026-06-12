/*
 * Occasion boundaries (Phase 5d-lite), mirroring the web core's
 * _live_session_id: captures within the inactivity window share a session
 * (one sitting = one occasion); a longer gap mints a new id. Persisted in
 * SharedPreferences so the boundary survives app restarts — with the old
 * app-launch UUID, killing the app between captures of the SAME package
 * looked like independent encounters and inflated every word on it.
 *
 * Promotion counts distinct sessions, so this id is what makes "met three
 * times" mean "met on three occasions".
 */

package com.ryanqin.tideline.data

import android.content.SharedPreferences
import java.util.UUID

const val LIVE_SESSION_WINDOW_MS = 30L * 60 * 1000

/** Pure decision: keep the current session or mint a new one. */
fun resolveLiveSession(
  currentId: String?,
  lastAtMs: Long,
  nowMs: Long,
  mint: () -> String = { "live-" + UUID.randomUUID().toString().replace("-", "").take(12) },
): String =
  if (!currentId.isNullOrBlank() && nowMs - lastAtMs <= LIVE_SESSION_WINDOW_MS) currentId
  else mint()

/** The session id for a capture happening NOW; refreshes the window. */
fun liveSessionId(prefs: SharedPreferences, nowMs: Long = System.currentTimeMillis()): String {
  val id = resolveLiveSession(
    currentId = prefs.getString("live_session_id", null),
    lastAtMs = prefs.getLong("live_session_last_at", 0L),
    nowMs = nowMs,
  )
  prefs.edit()
    .putString("live_session_id", id)
    .putLong("live_session_last_at", nowMs)
    .apply()
  return id
}
