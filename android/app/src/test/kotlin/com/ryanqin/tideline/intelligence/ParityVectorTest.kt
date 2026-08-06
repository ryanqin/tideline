/*
 * The cross-language parity vectors, run against the phone's implementations.
 *
 * These cases live in the repo's parity/vectors directory, outside both ends,
 * and the core's pytest suite reads the same files. (Written without a glob:
 * Kotlin block comments nest, so a stray slash-star in here silently swallows
 * the comment's own terminator.)
 * That is the whole point: two copies of a
 * case list is the shape that drifted in the first place — 한글すし answered
 * Korean on one end and Japanese on the other, and a Chinese scene name was
 * cleaned by one parser and waved through by the other, for over a year.
 *
 * Until now the two ends were checked by transcribing one into the other's
 * language and running the transcription. That proves the specifications agree.
 * It does not prove the shipped code does — a faithful reading can still be a
 * reading. This file closes that gap for the two rules a JSON vector can carry
 * (string in, string out); the richer ones, like the ashore mix, stay specified
 * in DESIGN §10.5.1 and tested separately on each side.
 */

package com.ryanqin.tideline.intelligence

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

private data class Vector(val id: String, val input: String, val expected: String?, val note: String)

private fun loadVectors(resource: String): List<Vector> {
  val text = checkNotNull(
    object {}.javaClass.classLoader.getResourceAsStream(resource)
  ) {
    "parity vector $resource not on the test classpath — see the test sourceSet " +
      "in app/build.gradle.kts, which points at /parity/vectors"
  }.bufferedReader().readText()

  return Json.parseToJsonElement(text).jsonObject["cases"]!!.jsonArray.map { el ->
    val o = el.jsonObject
    Vector(
      id = o["id"]!!.jsonPrimitive.content,
      input = o["input"]!!.jsonPrimitive.content,
      // A null expectation means "the rule declines to answer" — not a missing
      // case. jsonPrimitive.contentOrNull would flatten the two together.
      expected = o["expected"]!!.jsonPrimitive.let { if (it.toString() == "null") null else it.content },
      note = o["note"]?.jsonPrimitive?.content ?: "",
    )
  }
}

class ParityVectorTest {

  @Test
  fun `script detection matches the shared vectors`() {
    val cases = loadVectors("script_lang.json")
    assertTrue("expected the shared vector file to be populated", cases.size >= 12)
    val wrong = cases.filter { detectScriptLanguage(it.input) != it.expected }
    assertTrue(
      "these cases disagree with /parity/vectors/script_lang.json — the core " +
        "reads the same file, so a difference here IS the two ends diverging: " +
        wrong.joinToString("; ") {
          "${it.id} ${it.input.ifEmpty { "<empty>" }} -> " +
            "${detectScriptLanguage(it.input)} (expected ${it.expected}) [${it.note}]"
        },
      wrong.isEmpty(),
    )
  }

  @Test
  fun `scene name parsing matches the shared vectors`() {
    val cases = loadVectors("scene_name.json")
    assertTrue("expected the shared vector file to be populated", cases.size >= 18)
    val wrong = cases.filter { parseSceneName(it.input) != it.expected }
    assertTrue(
      "these cases disagree with /parity/vectors/scene_name.json: " +
        wrong.joinToString("; ") {
          "${it.id} ${it.input} -> ${parseSceneName(it.input)} " +
            "(expected ${it.expected}) [${it.note}]"
        },
      wrong.isEmpty(),
    )
  }

  @Test
  fun `the divergence that motivated these vectors is pinned on this end too`() {
    // Kana outranks hangul, and the whole string is scanned before deciding —
    // so word order cannot change the answer. The core used to return on the
    // first character it recognised and answered Korean here.
    assertEquals("Japanese", detectScriptLanguage("한글すし"))
    assertEquals("Japanese", detectScriptLanguage("すし한글"))
    // A Chinese scene name arrives with a preamble and a decoration; both ends
    // must land on the same three characters.
    assertEquals("生活集市", parseSceneName("名字：生活集市 🛒"))
  }
}
