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

  const LANG_SHORT = { Japanese: "日", English: "英", Chinese: "中", French: "法",
    Spanish: "西", German: "德", Italian: "意", Korean: "韩" };
  const shortLang = (n) => LANG_SHORT[n] || esc(n || "?");
  // Tideline always translates into your language, so the tag tells you which
  // language the original came from.
  const annot = (src, tgt) => `<span class="langtag">(${shortLang(src)}→${shortLang(tgt)})</span>`;

  // How a moment was caught, drawn small and warm: a photo seen, a voice heard,
  // a phrase looked up. Monochrome inline SVG (inherits currentColor).
  const SRC_GLYPH = {
    image: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8.5" cy="8.5" r="1.6"/><path d="M21 15l-5-5L5 21"/></svg>',
    audio: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 10v4M8 6v12M12 8.5v7M16 4v16M20 10v4"/></svg>',
    text: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>',
  };
  const srcGlyph = (s) => SRC_GLYPH[s] || SRC_GLYPH.text;
  const srcLabel = (s) => { const k = { image: "src_image", audio: "src_audio", text: "src_text" }[s]; return k ? t(k) : ""; };

  // One lived moment in the stack behind a card (DESIGN §3.2). A moment with a
  // captured scene leads with it; a silent one keeps only its quiet when/how on
  // one compact line, so a card of silent moments stays a tidy log.
  function momentRow(m) {
    const meta = [humanTime(m.at), srcLabel(m.source)].filter(Boolean).map(esc).join('<span class="dot">·</span>');
    if (!m.context) {
      return `<div class="moment moment--compact"><span class="moment-glyph" aria-hidden="true">${srcGlyph(m.source)}</span><span class="moment-meta">${meta || esc(t("no_context"))}</span></div>`;
    }
    return `<div class="moment"><span class="moment-glyph" aria-hidden="true">${srcGlyph(m.source)}</span><span class="moment-body"><span class="moment-context">${esc(m.context)}</span>${meta ? `<span class="moment-meta">${meta}</span>` : ""}</span></div>`;
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
    // In review mode (a due card the tide carried ashore) the foreign word is
    // masked: you see the meaning, reach for the word, reveal it, then self-
    // grade — that outcome feeds the schedule (DESIGN §10.3). The museum opens
    // cards plainly (no review), so it stays browsing, not a quiz.
    const reviewable = currentOpts.review && !c.readonly && c.id != null;
    const word = reviewable
      ? `<span class="masked" role="button" tabindex="0" title="${esc(t("tap_reveal"))}">${esc(c.original)}</span>`
      : esc(c.original);
    const grade = reviewable
      ? `<div class="review-grade">
          <button type="button" class="grade-missed" data-card-id="${c.id}">${esc(t("review_missed"))}</button>
          <button type="button" class="grade-got" data-card-id="${c.id}">${esc(t("review_got"))}</button>
        </div>`
      : "";
    return `<div class="cluster card">
        <div class="card-head">
          <h2>${word} → ${esc(c.translated)} ${annot(c.source_lang, c.target_lang)}</h2>
          ${sink}
        </div>
        ${body}
        ${grade}
      </div>`;
  }
  // shell → a concept cluster: the synonyms that gathered under one meaning.
  function conceptSheet(c) {
    return `<div class="cluster">
        <h2>${esc(c.title || "")}</h2>
        <div class="members">${(c.members || []).map((m) => `
          <div class="member">
            <span class="original">${shortLang(m.source_lang)} ${esc(m.original)}</span>
            <span class="translated">${esc(m.translated)}</span>
            ${m.context ? `<span class="context">${esc(m.context)}</span>` : ""}
          </div>`).join("")}</div>
      </div>`;
  }
  // crab → a theme: masked recall — you see the meaning, recall the word
  // (tap to reveal); "reveal all" flips to plain browsing. On the shore (review
  // mode) a scene is a review unit too: recall the night's words, then self-
  // grade once — that outcome reschedules the whole scene (DESIGN §10.3, keyed
  // on session_id). The museum opens themes plainly (no review), so it stays
  // browsing, not a quiz — same split as cards.
  function themeSheet(c) {
    const rows = (c.members || []).map((m) => `
      <div class="member">
        <span class="translated">${esc(m.translated)}</span>
        <span class="masked" role="button" tabindex="0" title="${esc(t("tap_reveal"))}">${esc(m.original)}</span>
        ${m.context ? `<span class="context">${esc(m.context)}</span>` : ""}
      </div>`).join("");
    const reviewable = currentOpts.review && c.session_id != null;
    const grade = reviewable
      ? `<div class="review-grade">
          <button type="button" class="grade-missed" data-session-id="${esc(c.session_id)}">${esc(t("review_missed"))}</button>
          <button type="button" class="grade-got" data-session-id="${esc(c.session_id)}">${esc(t("review_got"))}</button>
        </div>`
      : "";
    return `<div class="theme">
        <h2>${esc(c.title || "")}</h2>
        <div class="theme-tools"><button type="button" class="reveal-all">${esc(t("reveal_all"))}</button></div>
        <div class="members">${rows}</div>
        ${grade}
      </div>`;
  }

  const RENDER = { glass: cardSheet, crab: themeSheet, shell: conceptSheet };

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
      '<div class="sheet-panel" role="dialog" aria-modal="true" aria-label="海岸拾物">' +
        '<button class="sheet-close" id="sheetClose" type="button" aria-label="收起">' +
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
    const render = RENDER[kind] || conceptSheet;
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
