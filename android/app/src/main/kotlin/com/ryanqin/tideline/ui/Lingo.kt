/*
 * The web's i18n voice, carried to the phone (zh dictionary, i18n.js) — the
 * same human words for languages, sources and time. A moment's hour steps
 * back; what matters is "昨天 · 看到的", never "2026-06-11T23:48 source=image".
 */

package com.ryanqin.tideline.ui

import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

object Lingo {

  private val LANG_NAME = mapOf(
    "Chinese" to "中文", "English" to "英语", "Japanese" to "日语",
    "French" to "法语", "Spanish" to "西班牙语", "German" to "德语",
    "Italian" to "意大利语", "Korean" to "韩语",
  )
  private val LANG_SHORT = mapOf(
    "Chinese" to "中", "English" to "英", "Japanese" to "日",
    "French" to "法", "Spanish" to "西", "German" to "德",
    "Italian" to "意", "Korean" to "韩",
  )

  fun langName(name: String?): String = name?.let { LANG_NAME[it] ?: it } ?: "未知"

  fun langShort(name: String?): String = name?.let { LANG_SHORT[it] ?: it } ?: "?"

  /** "(日→中)" — which language the original came from. */
  fun langTag(source: String?, target: String?): String =
    "(${langShort(source)}→${langShort(target)})"

  /** How a moment was caught, in human words — never "source: image". */
  fun srcLabel(source: String?): String = when (source) {
    "image" -> "看到的"
    "audio" -> "听到的"
    else -> "查过的"
  }

  private val MONTH_DAY = SimpleDateFormat("M月d日", Locale.getDefault())

  private fun sameDay(a: Calendar, b: Calendar): Boolean =
    a.get(Calendar.YEAR) == b.get(Calendar.YEAR) &&
      a.get(Calendar.DAY_OF_YEAR) == b.get(Calendar.DAY_OF_YEAR)

  /** Mirrors the web's humanTime: 刚刚 / 今天 / 昨天 / N 天前 / 上周 / M月d日. */
  fun humanTime(thenMs: Long, nowMs: Long = System.currentTimeMillis()): String {
    val ms = nowMs - thenMs
    if (ms < 60_000) return "刚刚"
    val then = Calendar.getInstance().apply { timeInMillis = thenMs }
    val now = Calendar.getInstance().apply { timeInMillis = nowMs }
    if (sameDay(then, now)) return "今天"
    val yesterday = Calendar.getInstance().apply {
      timeInMillis = nowMs
      add(Calendar.DAY_OF_YEAR, -1)
    }
    if (sameDay(then, yesterday)) return "昨天"
    val days = ms / 86_400_000
    if (days < 7) return "$days 天前"
    if (days < 14) return "上周"
    return MONTH_DAY.format(Date(thenMs))
  }
}
