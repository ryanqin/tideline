"""Translation guard — fail empty, never with a wrong answer (DESIGN §3.3).

Mirrors the Android shell's TranslationGuardTest: the guard is a pure function,
so its judgement is unit-tested on both ends with the same cases. Tideline only
translates INTO your first language, so a same-language source or a plain echo
isn't a real result — it must be flagged, not surfaced or sedimented.
"""

from __future__ import annotations

from tideline.intelligence.translation_guard import (
    TranslationOutcome,
    judge_translation,
)


def test_a_real_foreign_to_native_translation_passes():
    assert (
        judge_translation("こんにちは", "你好", "Japanese", "Chinese")
        == TranslationOutcome.TRANSLATED
    )
    # French (Latin) → Chinese, the fr_cheese case
    assert (
        judge_translation("OFFRE SPECIALE", "特价优惠", "French", "Chinese")
        == TranslationOutcome.TRANSLATED
    )


def test_model_reading_the_source_as_native_is_same_language():
    # jp_exit: 非常口 read (wrongly) as Chinese, image so no text source
    assert (
        judge_translation(None, "非常口 非常口", "Chinese", "Chinese")
        == TranslationOutcome.SAME_AS_NATIVE
    )
    # spelling variants of the native language still match
    assert (
        judge_translation(None, "你好", "中文", "Chinese")
        == TranslationOutcome.SAME_AS_NATIVE
    )
    assert (
        judge_translation(None, "你好", "zh", "Chinese")
        == TranslationOutcome.SAME_AS_NATIVE
    )


def test_an_echoed_source_is_not_translated():
    # a typed Chinese sentence comes back unchanged
    assert (
        judge_translation("你好世界", "你好世界", None, "Chinese")
        == TranslationOutcome.NOT_TRANSLATED
    )
    # punctuation / spacing differences still read as an echo
    assert (
        judge_translation("これは日本語です", "これは日本語です。", None, "Chinese")
        == TranslationOutcome.NOT_TRANSLATED
    )


def test_a_half_translation_that_echoes_the_foreign_word_is_not_translated():
    # the "Premium 高级" pattern: the model glossed it but the foreign word rode
    # along in the output — a longer echo with extra content, still flagged.
    assert (
        judge_translation("Premium", "Premium 高级", None, "Chinese")
        == TranslationOutcome.NOT_TRANSLATED
    )


def test_a_blank_translation_is_not_translated():
    assert (
        judge_translation("hello", "", "English", "Chinese")
        == TranslationOutcome.NOT_TRANSLATED
    )
    # whitespace-only is just as blank
    assert (
        judge_translation("hello", "   ", "English", "Chinese")
        == TranslationOutcome.NOT_TRANSLATED
    )


def test_an_image_with_no_text_source_relies_on_the_reported_language():
    # source None (image); reported French → passes through
    assert (
        judge_translation(None, "特价优惠", "French", "Chinese")
        == TranslationOutcome.TRANSLATED
    )


def test_a_short_same_glyph_word_is_not_falsely_flagged_as_an_echo():
    # 寿司 is identical in Japanese and Chinese — a legit translation, must pass
    assert (
        judge_translation("寿司", "寿司", None, "Chinese")
        == TranslationOutcome.TRANSLATED
    )
    # a 1-char source translating to a 2-char native word
    assert (
        judge_translation("駅", "车站", "Japanese", "Chinese")
        == TranslationOutcome.TRANSLATED
    )


def test_an_unknown_language_matches_native_on_its_raw_spelling():
    # the guard doesn't know every language; two identical spellings still fold
    # together (mirrors the Android canonLang fallback), so a Swahili-into-
    # Swahili setting is caught even though it isn't in the fold table.
    assert (
        judge_translation(None, "habari", "Swahili", "Swahili")
        == TranslationOutcome.SAME_AS_NATIVE
    )
    # ...but two different languages don't.
    assert (
        judge_translation("Bonjour", "你好", "French", "Chinese")
        == TranslationOutcome.TRANSLATED
    )
