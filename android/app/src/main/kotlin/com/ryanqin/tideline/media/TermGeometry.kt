/*
 * Word geometry for photo-word masks (annotation overlays).
 *
 * The LLM owns WHAT a captured word says and means (TERM pairs); this module
 * owns WHERE it sits in the photo. On-device OCR gives deterministic pixel
 * boxes for the words the model already read — a 2B VLM's self-reported
 * box_2d landed in empty space when probed, so geometry is engineering's job
 * (engineering carries, model garnishes).
 *
 * Matching is fail-soft per term: a term the OCR can't find simply gets no
 * box — the vocabulary row still sediments, the mask just has nothing to
 * anchor for that word.
 */

package com.ryanqin.tideline.media

import android.graphics.Bitmap
import android.graphics.Rect
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.Text
import com.google.mlkit.vision.text.TextRecognizer
import kotlin.coroutines.resume
import kotlinx.coroutines.suspendCancellableCoroutine

/** One OCR'd word: its raw text and pixel box in the prepared image. */
data class OcrWord(val text: String, val box: Rect)

/** Run ML Kit text recognition over the prepared capture bitmap. */
suspend fun ocrWords(recognizer: TextRecognizer, bitmap: Bitmap): List<OcrWord> =
  suspendCancellableCoroutine { cont ->
    recognizer.process(InputImage.fromBitmap(bitmap, 0))
      .addOnSuccessListener { text: Text ->
        val words = text.textBlocks.asSequence()
          .flatMap { it.lines.asSequence() }
          .flatMap { it.elements.asSequence() }
          .mapNotNull { el -> el.boundingBox?.let { OcrWord(el.text, it) } }
          .toList()
        cont.resume(words)
      }
      .addOnFailureListener { cont.resume(emptyList()) }
  }

/** Letters and digits only, uppercased — "75%" matches "75 %", "Magicare," matches "MagiCare". */
private fun normalize(s: String): String =
  s.uppercase().filter { it.isLetterOrDigit() }

/**
 * Find each term's box as the union of a consecutive run of OCR words whose
 * normalized concatenation equals the normalized term ("HAND SANITIZING
 * WIPES" = three OCR words). Returns normalized [x0, y0, x1, y1] in 0..1 of
 * the prepared image; terms the OCR never saw are simply absent.
 */
fun matchTermBoxes(
  termOriginals: List<String>,
  words: List<OcrWord>,
  imageWidth: Int,
  imageHeight: Int,
): Map<String, List<Double>> {
  if (imageWidth <= 0 || imageHeight <= 0 || words.isEmpty()) return emptyMap()
  val result = mutableMapOf<String, List<Double>>()
  for (term in termOriginals) {
    val target = normalize(term)
    if (target.isEmpty()) continue
    var match: Rect? = null
    outer@ for (start in words.indices) {
      var acc = ""
      var union: Rect? = null
      for (end in start until words.size) {
        acc += normalize(words[end].text)
        union = Rect(union ?: words[end].box).apply { union(words[end].box) }
        when {
          acc == target -> { match = union; break@outer }
          acc.length >= target.length -> continue@outer
        }
      }
    }
    match?.let {
      result[term] = listOf(
        it.left.toDouble() / imageWidth,
        it.top.toDouble() / imageHeight,
        it.right.toDouble() / imageWidth,
        it.bottom.toDouble() / imageHeight,
      )
    }
  }
  return result
}
