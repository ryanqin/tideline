/*
 * B6 for scene types — a warm name for a KIND of place.
 *
 * Mirror of the core's intelligence/episodic_title.py (the SCENE path only):
 * SCENE_SYSTEM_PROMPT / build_scene_prompt / parse_response. On the phone a
 * theme is a scene TYPE clustered across visits (拉面店 / 车站); its bare label
 * is the deterministic grouping key (Themes.kt — load-bearing), but the title
 * that surfaces on the shore wants a little warmth: 拉面店 → 暖汤馆. The model
 * only garnishes; the night-watch sweep in the ViewModel feeds these prompts to
 * the on-device model and stores the parsed name in scene_names.
 *
 * Pure Kotlin (no Android deps) so the prompt builder and parser are unit
 * tested — the bench measures the exact strings the night-watch runs, exactly
 * like the core keeps its atom bench and engine on one shared prompt module.
 */

package com.ryanqin.tideline.intelligence

// Mirrors core episodic_title.SCENE_SYSTEM_PROMPT verbatim — a warm, recurring
// place name, never a one-time event, never a bare category. Kept in English
// (the system instruction) like the core; the user-turn prompt below carries
// the Chinese framing and the reader's first language.
const val SCENE_SYSTEM_PROMPT =
  "Give a warm 3-6 character Chinese name to a KIND of place a learner keeps " +
    "returning to. It should evoke the place and its mood, keep the place " +
    "recognizable, and read as a recurring kind of spot — NOT a one-time event " +
    "('the night...', 'one Sunday') and NOT a bare category label. Output only " +
    "the name."

// Common preambles a model bolts onto its answer. Core strips English ones
// (title/name); on-device the model often replies in Chinese, so 名字/名称 are
// stripped too — a defensive extension, not a different prompt.
private val SCENE_NAME_PREFIX = Regex(
  "^\\s*(title|episodic title|cluster|name|名字|名称)\\s*[:：\\-]\\s*",
  RegexOption.IGNORE_CASE,
)

// A B6 scene name is 3-6 characters; this is the rambling-answer backstop. CJK
// names aren't space-delimited, so cap by character (core caps by word for its
// English-leaning titles).
private const val MAX_NAME_CHARS = 12

private const val MAX_PROMPT_TERMS = 8

// Emoji / pictographs / dingbats the on-device model tacks onto a name (超市 →
// "生活集市 🛒"). The web's E4B doesn't do this; the smaller on-device E2B does
// on roughly half its names. Matched by code point (\x{...}), NOT by a
// [\uD800-\uDFFF] surrogate class — the JVM sees a well-formed pair like 🛒
// (U+1F6D2) as one code point, so a surrogate class never matches it. Plain CJK
// names (and U+3000–303F punctuation) are untouched.
private val SCENE_DECORATION = Regex(
  "[\\x{1F000}-\\x{1FAFF}\\x{2600}-\\x{27BF}\\x{2B00}-\\x{2BFF}\\x{2190}-\\x{21FF}" +
    "\\x{2300}-\\x{23FF}\\x{FE00}-\\x{FE0F}\\x{200D}]",
)

/** Render a scene type into the B6 naming prompt — mirrors core
 * build_scene_prompt. `terms` are the words met at that kind of place (capped);
 * the name is written in `nativeLang`, the reader's first language. */
fun buildScenePrompt(sceneLabel: String, terms: List<String>, nativeLang: String): String {
  require(sceneLabel.isNotBlank()) { "buildScenePrompt requires a sceneLabel" }
  require(nativeLang.isNotBlank()) { "buildScenePrompt requires a nativeLang" }
  val words = terms.take(MAX_PROMPT_TERMS).joinToString("、")
  return "这是一类反复去的地方,类型是「$sceneLabel」,在这里遇到过这些词:" +
    "$words。请给它起一个温暖、有韵味的 $nativeLang 短名(3-6 字)," +
    "既能让人认出是哪类地方,又带一点情绪;不要写成'那一夜'式的单次事件," +
    "也不要只是干巴巴的类别词。只输出名字。"
}

/** Extract a clean scene name from a model reply — mirror of core
 * parse_response: the first non-empty line, common preambles stripped,
 * surrounding quotes/marks removed, length-capped. Null for empty /
 * unparseable replies (the caller keeps the bare scene_label as the title). */
fun parseSceneName(response: String?): String? {
  if (response.isNullOrEmpty()) return null
  val firstLine = response.lineSequence()
    .map { it.trim() }
    .firstOrNull { it.isNotEmpty() }
    ?: return null
  var cleaned = SCENE_NAME_PREFIX.replace(firstLine, "")
  // Half- and full-width quotes / brackets / list marks a model wraps around
  // the bare name.
  cleaned = cleaned.trim(' ', '\t', '"', '\'', '`', '*', '#', '.', '。', '：', ':',
    '「', '」', '“', '”', '《', '》')
  // Strip the emoji the on-device model decorates names with ("生活集市 🛒" →
  // "生活集市"), then re-trim the space they leave behind.
  cleaned = SCENE_DECORATION.replace(cleaned, "").trim()
  if (cleaned.isEmpty()) return null
  if (cleaned.length > MAX_NAME_CHARS) cleaned = cleaned.take(MAX_NAME_CHARS)
  return cleaned
}
