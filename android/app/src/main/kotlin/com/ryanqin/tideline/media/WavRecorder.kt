/*
 * Phase 5b — live mic capture.
 *
 * Records 16 kHz mono PCM16 (the format the audio probe verified end-to-end
 * against the bundled Conformer encoder) and returns it as WAV bytes for
 * Content.AudioBytes — no temp file, no third-party ASR; the speech goes to
 * the LLM the same way a photo's bytes do.
 *
 * The caller owns the RECORD_AUDIO permission gate. Recording is capped so a
 * forgotten session can't grow unbounded.
 */

package com.ryanqin.tideline.media

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import java.io.ByteArrayOutputStream
import kotlin.concurrent.thread

private const val SAMPLE_RATE = 16_000
private const val MAX_SECONDS = 30
private const val MAX_PCM_BYTES = SAMPLE_RATE * 2 * MAX_SECONDS

class WavRecorder {

  private var record: AudioRecord? = null
  private var reader: Thread? = null
  private val pcm = ByteArrayOutputStream()
  @Volatile private var running = false

  val isRecording: Boolean get() = running

  /** Begin capturing; throws if the mic can't be opened. Caller has already
   * been granted RECORD_AUDIO (lint can't see the runtime gate). */
  @SuppressLint("MissingPermission")
  fun start() {
    if (running) return
    pcm.reset()
    val minBuf = AudioRecord.getMinBufferSize(
      SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT
    )
    val r = AudioRecord(
      MediaRecorder.AudioSource.MIC,
      SAMPLE_RATE,
      AudioFormat.CHANNEL_IN_MONO,
      AudioFormat.ENCODING_PCM_16BIT,
      maxOf(minBuf, 8192),
    )
    check(r.state == AudioRecord.STATE_INITIALIZED) { "mic unavailable" }
    record = r
    r.startRecording()
    running = true
    reader = thread(name = "tideline-mic") {
      val chunk = ByteArray(4096)
      while (running && pcm.size() < MAX_PCM_BYTES) {
        val n = r.read(chunk, 0, chunk.size)
        if (n > 0) pcm.write(chunk, 0, n)
      }
    }
  }

  /** Stop and return the capture as a complete WAV (16 kHz mono PCM16). */
  fun stop(): ByteArray {
    running = false
    reader?.join(1_000)
    reader = null
    try {
      record?.stop()
    } catch (_: Throwable) {}
    record?.release()
    record = null
    return wavOf(pcm.toByteArray())
  }

  /** Seconds captured so far (approximate, for labels/logs). */
  fun seconds(): Int = pcm.size() / (SAMPLE_RATE * 2)

  private fun wavOf(pcmBytes: ByteArray): ByteArray {
    val out = ByteArrayOutputStream(44 + pcmBytes.size)
    fun le32(v: Int) = out.write(byteArrayOf(
      (v and 0xff).toByte(), (v shr 8 and 0xff).toByte(),
      (v shr 16 and 0xff).toByte(), (v shr 24 and 0xff).toByte()))
    fun le16(v: Int) = out.write(byteArrayOf((v and 0xff).toByte(), (v shr 8 and 0xff).toByte()))
    out.write("RIFF".toByteArray()); le32(36 + pcmBytes.size); out.write("WAVE".toByteArray())
    out.write("fmt ".toByteArray()); le32(16); le16(1); le16(1)
    le32(SAMPLE_RATE); le32(SAMPLE_RATE * 2); le16(2); le16(16)
    out.write("data".toByteArray()); le32(pcmBytes.size); out.write(pcmBytes)
    return out.toByteArray()
  }
}
