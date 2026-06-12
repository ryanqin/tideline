// The warm creature sheet — shared by the shore (index) and the museum
// (learnings). Tap a shell / crab / sea-glass anywhere and the same panel rises
// holding what washed up: a card's lived moments, a concept's synonyms, or a
// theme's masked recall. ONE copy of this flow, so the two surfaces stay one
// visual language (DESIGN §10.5 / §10.7) and never drift. The learning
// interaction is not reinvented here — this is its single doorway.
//
// Depends on the i18n globals (t / humanTime) loaded before it. The host page
// owns the data and what to do after a sink (onSink); the sheet only renders +
// raises + lowers, and runs the sink fetch.

(function (global) {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  }

  // Tideline always translates into your language, so the tag tells you which
  // language the original came from. The compact name comes from i18n's
  // locale-aware langShort (one source of truth — a CJK glyph in zh, a
  // two-letter code in en — so neither locale leaks the other's script).
  const annot = (src, tgt) => `<span class="langtag">(${langShort(src)}→${langShort(tgt)})</span>`;

  // --- pronunciation -------------------------------------------------------
  // Two kinds of sound, two sources: the CAPTURED recording (dictation
  // material — what the moment actually sounded like, served from the drawer)
  // and the STANDARD pronunciation (never stored — the browser's own TTS
  // regenerates it from text, the same way every translation app does).
  const TTS_LANG = {
    Japanese: "ja-JP", English: "en-US", French: "fr-FR", Spanish: "es-ES",
    German: "de-DE", Italian: "it-IT", Korean: "ko-KR", Chinese: "zh-CN",
  };
  function speak(text, langName) {
    if (!("speechSynthesis" in window) || !text) return;
    let code = TTS_LANG[langName];
    if (!code) {
      // honest fallback: sniff the script when the row has no language
      if (/[぀-ヿ]/.test(text)) code = "ja-JP";
      else if (/[가-힯]/.test(text)) code = "ko-KR";
      else if (/[一-鿿]/.test(text)) code = "zh-CN";
      else code = "en-US";
    }
    const u = new SpeechSynthesisUtterance(text);
    u.lang = code;
    u.rate = 0.92;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  }

  const SPEAKER_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H2v6h4l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M18.5 5.5a9 9 0 0 1 0 13"/></svg>';
  const PLAY_SVG = '<svg viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M8 5.5v13l11-6.5z"/></svg>';

  // Standard pronunciation of a word/phrase, in its own language (TTS).
  const speakBtn = (text, lang) => text
    ? `<button type="button" class="speak-btn" data-speak="${esc(text)}" data-speak-lang="${esc(lang || "")}" aria-label="Standard pronunciation" title="${esc(t("speak_standard"))}">${SPEAKER_SVG}</button>`
    : "";
  // The captured recording behind a heard moment.
  const playBtn = (m) => (m.has_audio && m.id != null)
    ? `<button type="button" class="play-btn" data-audio-id="${Number(m.id)}" aria-label="Play the recording" title="${esc(t("play_capture"))}">${PLAY_SVG}</button>`
    : "";

  // How a moment was caught, drawn small and warm: a photo seen, a voice heard,
  // a phrase looked up. Monochrome inline SVG (inherits currentColor).
  const SRC_GLYPH = {
    image: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8.5" cy="8.5" r="1.6"/><path d="M21 15l-5-5L5 21"/></svg>',
    audio: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 10v4M8 6v12M12 8.5v7M16 4v16M20 10v4"/></svg>',
    text: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>',
  };
  const srcGlyph = (s) => SRC_GLYPH[s] || SRC_GLYPH.text;
  const srcLabel = (s) => { const k = { image: "src_image", audio: "src_audio", text: "src_text" }[s]; return k ? t(k) : ""; };

  // One lived moment in the stack behind a card (DESIGN §3.2). A moment with
  // captured material leads with it — the photo it was read from, then the
  // scene line; a silent one keeps only its quiet when/how on one compact
  // line, so a card of silent moments stays a tidy log.
  const capturePhoto = (m, cls) => (m.has_image && m.id != null)
    ? `<img class="${cls}" src="/api/translations/${Number(m.id)}/image" alt="" loading="lazy">`
    : "";

  // A photo that knows WHERE its word sits gets a mask over that spot — the
  // full form of recall-by-photo: see the place, the word itself covered,
  // reach for it, tap to reveal. The corner chip hides the masks entirely
  // (plain photo), so the annotation is there when wanted, gone when not.
  function photoFigure(m, cls) {
    const photo = capturePhoto(m, cls);
    if (!photo) return "";
    const r = Array.isArray(m.region) && m.region.length === 4 ? m.region.map(Number) : null;
    if (!r || r.some(isNaN)) return photo;
    const pct = (v) => (Math.max(0, Math.min(1, v)) * 100).toFixed(2) + "%";
    const mask = `<button type="button" class="photo-mask" aria-label="Reveal the word in the photo"
        style="left:${pct(r[0])};top:${pct(r[1])};width:${pct(r[2] - r[0])};height:${pct(r[3] - r[1])}"
        title="${esc(t("tap_reveal"))}"></button>`;
    const chip = `<button type="button" class="mask-toggle" aria-label="Toggle photo masks">${esc(t("photo_mask"))}</button>`;
    return `<span class="photo-frame">${photo}${mask}${chip}</span>`;
  }

  function momentRow(m) {
    const meta = [humanTime(m.at), srcLabel(m.source)].filter(Boolean).map(esc).join('<span class="dot">·</span>');
    // In review the photo comes whole: the word is the SHOWN question (the
    // review direction is the translation direction, §3.3), so masking its
    // pixels would fight the card. Browsing keeps the maskable figure — the
    // look-at-the-place-and-reach game stays a museum pastime.
    const photo = currentOpts.review
      ? capturePhoto(m, "moment-photo")
      : photoFigure(m, "moment-photo");
    const play = playBtn(m);
    if (!m.context && !photo) {
      return `<div class="moment moment--compact"><span class="moment-glyph" aria-hidden="true">${srcGlyph(m.source)}</span><span class="moment-meta">${meta || esc(t("no_context"))}</span>${play}</div>`;
    }
    return `<div class="moment"><span class="moment-glyph" aria-hidden="true">${srcGlyph(m.source)}</span><span class="moment-body">${photo}${m.context ? `<span class="moment-context">${esc(m.context)}</span>` : ""}${meta || play ? `<span class="moment-meta">${meta}${play ? `<span class="dot">·</span>${play}` : ""}</span>` : ""}</span></div>`;
  }

  // glass → a card: the word, the direction, and the stack of lived moments it
  // grew from; sink returns it to the sea. A read-only glass (a by-language term
  // that hasn't matured into a card) carries no sink and no moment stack — just
  // the word, the direction, and how many times it's been met.
  function cardSheet(c) {
    const sink = c.readonly
      ? ""
      : `<button type="button" class="sink-btn" data-card-id="${c.id}" title="${esc(t("sink_title"))}">${esc(t("sink"))}</button>`;
    const body = c.readonly
      ? (c.count ? `<div class="moments"><div class="moment moment--compact"><span class="moment-meta">${esc(c.count)}×</span></div></div>` : "")
      : `<div class="moments">${(c.moments || []).map(momentRow).join("")}</div>`;
    // In review mode (a due card the tide carried ashore) the MEANING is
    // masked: the foreign word — the form you'll meet again in the world — is
    // the shown question, and you reach for what it means (the review
    // direction IS the translation direction, §3.3). Reveal, then self-grade;
    // that outcome feeds the schedule (DESIGN §10.3). The museum opens cards
    // plainly (no review), so it stays browsing, not a quiz.
    const reviewable = currentOpts.review && !c.readonly && c.id != null;
    const meaning = reviewable
      ? `<span class="masked" role="button" tabindex="0" title="${esc(t("tap_reveal"))}">${esc(c.translated)}</span>`
      : esc(c.translated);
    // The standard pronunciation belongs to the shown word — part of the
    // question, speakable any time (it can't leak the masked meaning).
    const sayWord = speakBtn(c.original, c.source_lang);
    const grade = reviewable
      ? `<div class="review-grade">
          <button type="button" class="grade-missed" data-card-id="${c.id}">${esc(t("review_missed"))}</button>
          <button type="button" class="grade-got" data-card-id="${c.id}">${esc(t("review_got"))}</button>
        </div>`
      : "";
    return `<div class="cluster card">
        <div class="card-head">
          <h2>${esc(c.original)} → ${meaning} ${annot(c.source_lang, c.target_lang)}${sayWord}</h2>
          ${sink}
        </div>
        ${body}
        ${grade}
      </div>`;
  }

  // A concept group in the museum's card deck: same-language synonyms that
  // share a meaning (拉面 ← 中華そば / ラーメン) collapse to one shelf tile, so
  // the deck never shows the meaning twice. Opening it shows the meaning once,
  // then each foreign word that carried it — its own moments, its own sink
  // (each is still an independent card; the grouping is only how the deck
  // BROWSES them, and the shore still reviews each word on its own). A different
  // language with the same meaning stays its own tile (DESIGN §3.3: one cluster
  // is one language pair), so a group is always single-language.
  function cardGroupSheet(g) {
    const words = (g.cards || []).map((c) => {
      const moments = `<div class="moments">${(c.moments || []).map(momentRow).join("")}</div>`;
      return `<div class="group-word">
          <div class="card-head">
            <h3>${esc(c.original)}${speakBtn(c.original, c.source_lang || g.source_lang)}</h3>
            <button type="button" class="sink-btn" data-card-id="${c.id}" title="${esc(t("sink_title"))}">${esc(t("sink"))}</button>
          </div>
          ${moments}
        </div>`;
    }).join("");
    return `<div class="cluster card">
        <h2>${esc(g.translated)} ${annot(g.source_lang, g.target_lang)}</h2>
        <div class="group-words">${words}</div>
      </div>`;
  }
  // crab → a theme: masked recall — the scene's foreign words shown as met,
  // each MEANING behind its patch (the review direction is the translation
  // direction, §3.3); "reveal all" flips to plain browsing. On the shore
  // (review mode) a scene is a review unit too: reach for the night's
  // meanings, then self-grade once — that outcome reschedules the whole scene
  // (DESIGN §10.3, keyed on session_id). The museum opens themes plainly (no
  // review), so it stays browsing, not a quiz — same split as cards.
  function themeSheet(c) {
    // One recall row per concept. A scene is a single-language capture
    // session, so rows sharing a translation share a concept (账单 ← addition /
    // facture); collapse them, or the same meaning hides behind two patches
    // that read as duplicates. The shown side then holds every foreign word
    // that meant it — the scene's whole synonym set poses one question.
    const byMeaning = [];
    const seen = new Map();
    (c.members || []).forEach((m) => {
      let g = seen.get(m.translated);
      if (!g) {
        g = { translated: m.translated, originals: [], context: "" };
        seen.set(m.translated, g);
        byMeaning.push(g);
      }
      if (!g.originals.includes(m.original)) g.originals.push(m.original);
      if (!g.context && m.context) g.context = m.context;
    });
    // .translated is the row's lead-slot class (styling), not its content:
    // the foreign words lead the row now, the meaning sits behind the patch.
    const rows = byMeaning.map((g) => `
      <div class="member">
        <span class="translated">${esc(g.originals.join(" / "))}</span>
        <span class="masked" role="button" tabindex="0" title="${esc(t("tap_reveal"))}">${esc(g.translated)}</span>
        ${g.context ? `<span class="context">${esc(g.context)}</span>` : ""}
      </div>`).join("");
    const reviewable = currentOpts.review && c.session_id != null;
    const grade = reviewable
      ? `<div class="review-grade">
          <button type="button" class="grade-missed" data-session-id="${esc(c.session_id)}">${esc(t("review_missed"))}</button>
          <button type="button" class="grade-got" data-session-id="${esc(c.session_id)}">${esc(t("review_got"))}</button>
        </div>`
      : "";
    // The scene's own photo (when the capture kept one) leads the recall —
    // you see the place again and reach for its words, instead of recalling
    // against a bare list. One photo stands for the occasion; the per-word
    // moment stacks still hold each capture's own.
    const photoMember = (c.members || []).find((m) => m.has_image && m.id != null);
    const scenePhoto = photoMember ? capturePhoto(photoMember, "theme-photo") : "";
    return `<div class="theme">
        <h2>${esc(c.title || "")}</h2>
        ${scenePhoto}
        <div class="theme-tools"><button type="button" class="reveal-all">${esc(t("reveal_all"))}</button></div>
        <div class="members">${rows}</div>
        ${grade}
      </div>`;
  }

  const RENDER = { glass: cardSheet, cardgroup: cardGroupSheet, crab: themeSheet };

  let root = null, content = null, current = null, onSink = null;
  let onReview = null, currentOpts = {};

  // Inject the sheet chrome once (idempotent). Kept in document.body and fixed
  // to the viewport so the same panel serves both the shore and the museum,
  // above whatever world is behind it.
  function mount() {
    if (root) return;
    root = document.createElement("div");
    root.className = "creature-sheet";
    root.id = "creatureSheet";
    root.setAttribute("aria-hidden", "true");
    root.innerHTML =
      '<div class="sheet-scrim" id="sheetScrim"></div>' +
      '<div class="sheet-panel" role="dialog" aria-modal="true" aria-label="Shore findings">' +
        '<button class="sheet-close" id="sheetClose" type="button" aria-label="Close">' +
          '<span class="sheet-grip" aria-hidden="true"></span>' +
        '</button>' +
        '<div class="sheet-content" id="sheetContent"></div>' +
      '</div>';
    document.body.appendChild(root);
    content = root.querySelector("#sheetContent");

    root.querySelector("#sheetScrim").addEventListener("click", close);
    root.querySelector("#sheetClose").addEventListener("click", close);

    // One delegated handler inside the sheet: sink a card, reveal a masked word,
    // or flip the whole theme between recall and plain view.
    content.addEventListener("click", async (e) => {
      const sinkBtn = e.target.closest(".sink-btn");
      if (sinkBtn) {
        sinkBtn.disabled = true;
        try {
          const r = await fetch("/api/cards/sink", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ card_id: Number(sinkBtn.dataset.cardId) }),
          });
          if (!r.ok) { sinkBtn.disabled = false; return; }
          const sunk = current;
          close();
          if (onSink) onSink(sunk);   // the page slips it back under + repaints
        } catch (err) { sinkBtn.disabled = false; }
        return;
      }
      const grade = e.target.closest(".grade-got, .grade-missed");
      if (grade) {
        grade.disabled = true;
        const remembered = grade.classList.contains("grade-got");
        // One grade flow, two review units: a card (a word) or a theme (a whole
        // scene). The button carries whichever id it has; route to its endpoint.
        const cardId = grade.dataset.cardId;
        const url = cardId ? "/api/cards/review" : "/api/themes/review";
        const body = cardId
          ? { card_id: Number(cardId), remembered }
          : { session_id: grade.dataset.sessionId, remembered };
        try {
          const r = await fetch(url, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          });
          if (!r.ok) { grade.disabled = false; return; }
          const reviewed = current;
          close();
          if (onReview) onReview(reviewed);   // the tide reschedules it away
        } catch (err) { grade.disabled = false; }
        return;
      }
      const playB = e.target.closest(".play-btn");
      if (playB) {
        try {
          new Audio(`/api/translations/${Number(playB.dataset.audioId)}/audio`).play();
        } catch (err) {}
        return;
      }
      const speakB = e.target.closest(".speak-btn");
      if (speakB) {
        speak(speakB.dataset.speak, speakB.dataset.speakLang || null);
        return;
      }
      const photoMask = e.target.closest(".photo-mask");
      if (photoMask) {
        photoMask.classList.toggle("revealed");
        return;
      }
      const maskToggle = e.target.closest(".mask-toggle");
      if (maskToggle) {
        maskToggle.closest(".photo-frame").classList.toggle("masks-off");
        return;
      }
      const revealAll = e.target.closest(".reveal-all");
      if (revealAll) {
        const masks = content.querySelectorAll(".masked");
        const anyHidden = [...masks].some((s) => !s.classList.contains("revealed"));
        masks.forEach((s) => s.classList.toggle("revealed", anyHidden));
        revealAll.textContent = anyHidden ? t("mask") : t("reveal_all");
        return;
      }
      const mask = e.target.closest(".masked");
      if (mask) mask.classList.toggle("revealed");
    });
    content.addEventListener("keydown", (e) => {
      if ((e.key === "Enter" || e.key === " ") && e.target.closest(".masked")) {
        e.preventDefault();
        e.target.closest(".masked").classList.toggle("revealed");
      }
    });
  }

  // Raise the sheet over `data` (a card / cluster / theme). `kind` is the
  // creature kind (glass / shell / crab). opts.onSink(data) runs after a
  // successful sink, so the host page can drop it from its own collection.
  function open(kind, data, opts) {
    mount();
    opts = opts || {};
    currentOpts = opts;
    onSink = opts.onSink || null;
    onReview = opts.onReview || null;
    current = data;
    const render = RENDER[kind] || cardSheet;
    content.innerHTML = render(data || {});
    content.scrollTop = 0;
    root.classList.add("is-open");
    root.setAttribute("aria-hidden", "false");
  }

  function close() {
    if (!root || !root.classList.contains("is-open")) return;
    root.classList.remove("is-open");
    root.setAttribute("aria-hidden", "true");
    current = null;
  }

  const isOpen = () => !!(root && root.classList.contains("is-open"));

  global.Sheet = { mount, open, close, isOpen };
})(typeof window !== "undefined" ? window : globalThis);
