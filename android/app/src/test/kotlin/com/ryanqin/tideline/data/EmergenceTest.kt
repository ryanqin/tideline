package com.ryanqin.tideline.data

import org.junit.Assert.assertEquals
import org.junit.Test

class EmergenceTest {

  private val now = 1_700_000_000_000L
  private val day = 24L * 60 * 60 * 1000

  @Test
  fun `remembered climbs the ladder and pushes the due date out`() {
    val (s1, due1) = reschedule(strength = 0, remembered = true, nowMs = now)
    assertEquals(1, s1)
    assertEquals(now + 1 * day, due1)

    val (s2, due2) = reschedule(strength = 1, remembered = true, nowMs = now)
    assertEquals(2, s2)
    assertEquals(now + 3 * day, due2)
  }

  @Test
  fun `forgotten drops a box and comes back sooner`() {
    val (s, due) = reschedule(strength = 3, remembered = false, nowMs = now)
    assertEquals(2, s)
    assertEquals(now + 3 * day, due)
  }

  @Test
  fun `ladder is capped at the top and floored at zero`() {
    val top = REVIEW_INTERVALS_DAYS.size - 1
    val (sTop, dueTop) = reschedule(strength = top, remembered = true, nowMs = now)
    assertEquals(top, sTop)
    assertEquals(now + 75 * day, dueTop)

    val (sFloor, dueFloor) = reschedule(strength = 0, remembered = false, nowMs = now)
    assertEquals(0, sFloor)
    // floor interval is 0 days — a struggling card stays due right away,
    // the Leitner answer to "I keep missing this one"
    assertEquals(now, dueFloor)
  }
}
