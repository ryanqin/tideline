// Shared UI translations for the Tideline playground.
//
// The first language is the single "me" anchor: it also picks the interface
// locale (Chinese -> zh, everything else -> en fallback until more locales
// land). Only user-facing chrome is translated here — code comments stay
// English (open-source convention). Both pages load this before their inline
// script, so `t()` / `setLocale()` / `applyStaticI18n()` are globals.

const I18N = {
  en: {
    nav_translate: "Translate",
    nav_learnings: "Learnings",
    title_translate: "Tideline — translate",
    title_learnings: "Tideline — learnings",

    // translate page
    translate_q: "What do you want to translate?",
    translate_ph: "Type text, paste a menu line, drop in a phrase...",
    into_first: "Into your first language",
    btn_translate: "Translate",
    index_hint:
      "Everything you translate is stored locally. After enough translations " +
      'pile up, wade into the shore — or head to the <a href="/learnings">' +
      "shelves</a> — to see the clusters that have quietly formed in the " +
      "background.",

    // learnings page
    learnings_hint:
      "What's quietly come together so far. Cards surface on their own as " +
      "terms repeat — keep the ones worth studying and sink the rest. Each " +
      "card keeps the stack of moments it grew from.",
    first_lang_label: "Your first language",
    ui_lang_label: "Interface",

    // museum (the shelves on the dunes — the full collection, the list floor)
    nav_museum: "Museum",
    title_museum: "Tideline — museum",
    museum_hint:
      "Everything that's washed up, shelved on the dunes. Browse it by card, " +
      "language, or theme — tap one to open what it holds.",
    lens_cards: "Cards",
    lens_language: "Language",
    lens_theme: "Theme",
    back_to_shore: "Water's edge",
    // the doorway from the shore up to the shelves on the dunes (§10.7)
    to_shelves_aria: "Back up the beach to the shelves on the dunes",

    cards_empty:
      "No cards yet — cards surface on their own once a term repeats enough; " +
      "you keep the ones worth studying and sink the rest.",
    by_language_empty:
      "No learnings yet — once translations repeat, they group by source language here.",
    themes_empty:
      "No themes yet — as related words pile up, they quietly gather into a " +
      "remembered scene you can revisit here.",

    sink: "Sink",
    sink_title: "Sink this card back to sediment",
    reveal_all: "Reveal all",
    mask: "Mask",
    tap_reveal: "tap to reveal",
    photo_mask: "masks",
    speak_standard: "standard pronunciation",
    play_capture: "play the recording",
    review_got: "I remembered",
    review_missed: "Didn't come",
    no_context: "a quiet one — no scene saved",

    // how a moment was caught — warm, human, never "source: image"
    src_image: "seen",
    src_audio: "heard",
    src_text: "looked up",
    // humanized time — the moment matters, its clock-time recedes
    time_just_now: "just now",
    time_today: "today",
    time_yesterday: "yesterday",
    time_days_ago: "{n} days ago",
    time_last_week: "last week",

    lang_Chinese: "Chinese", lang_English: "English", lang_Japanese: "Japanese",
    lang_French: "French", lang_Spanish: "Spanish", lang_German: "German",
    lang_Italian: "Italian", lang_Korean: "Korean", lang_Unknown: "Unknown",
  },
  zh: {
    nav_translate: "翻译",
    nav_learnings: "学习",
    title_translate: "Tideline — 翻译",
    title_learnings: "Tideline — 学习",

    // translate page
    translate_q: "想翻译什么?",
    translate_ph: "输入文字,粘贴一行菜单,丢进一句话……",
    into_first: "译成你的第一语言",
    btn_translate: "翻译",
    index_hint:
      "你翻译的一切都只存在本地。等翻译攒得够多,涉水走进海岸,或直接去" +
      '<a href="/learnings">货架</a>,看那些在后台悄悄成形的聚类。',

    // learnings page
    learnings_hint:
      "到目前为止悄悄沉淀下来的东西。词反复出现,卡片会自己浮现——留下值得学的," +
      "把其余的沉回去。每张卡都留着它生长出来的那叠片刻。",
    first_lang_label: "你的第一语言",
    ui_lang_label: "界面",

    // 陈列馆(沙丘上的货架 — 完整收藏,也是 list 退路)
    nav_museum: "陈列馆",
    title_museum: "Tideline — 陈列馆",
    museum_hint:
      "冲上岸的一切,陈列在沙丘的货架上。按卡片、语言或主题来逛——" +
      "点开一件,看它收着什么。",
    lens_cards: "卡片",
    lens_language: "语言",
    lens_theme: "主题",
    back_to_shore: "回到水边",
    // 从海岸沿沙滩走回沙丘上的货架(§10.7)
    to_shelves_aria: "沿沙滩走回沙丘上的货架",

    cards_empty:
      "还没有卡片——一个词反复出现得够多,卡片会自己浮现;你留下值得学的," +
      "把其余的沉回去。",
    by_language_empty: "还没有沉淀——翻译开始重复后,会在这里按原文语言归拢。",
    themes_empty: "还没有主题——相关的词攒多了,会在这里悄悄聚成一段可以回访的记忆。",

    sink: "沉底",
    sink_title: "把这张卡沉回沉淀层",
    reveal_all: "全部揭开",
    mask: "重新遮住",
    tap_reveal: "点一下揭开",
    photo_mask: "遮罩",
    speak_standard: "标准读音",
    play_capture: "播放原声",
    review_got: "想起来了",
    review_missed: "没想起来",
    no_context: "安静的一次 — 没留下情景",

    // 这个片刻是怎么遇上的 — 用人话,不是 "来源:图片"
    src_image: "看到的",
    src_audio: "听到的",
    src_text: "查过的",
    // 人话时间 — 重要的是那个片刻,钟点退到后面
    time_just_now: "刚刚",
    time_today: "今天",
    time_yesterday: "昨天",
    time_days_ago: "{n} 天前",
    time_last_week: "上周",

    lang_Chinese: "中文", lang_English: "英语", lang_Japanese: "日语",
    lang_French: "法语", lang_Spanish: "西班牙语", lang_German: "德语",
    lang_Italian: "意大利语", lang_Korean: "韩语", lang_Unknown: "未知",
  },
};

let LOCALE = "en";

// The interface language we default to before the user picks one: it follows
// the first language (Chinese → zh, else → en). Once the user chooses an
// interface language it's independent (server: ui_locale).
function localeFor(nativeLang) {
  return nativeLang === "Chinese" ? "zh" : "en";
}

// Set the active UI locale directly (a locale, not a language name).
function setLocale(locale) {
  LOCALE = locale === "zh" ? "zh" : "en";
  document.documentElement.lang = LOCALE === "zh" ? "zh-Hans" : "en";
}

function t(key) {
  const table = I18N[LOCALE] || I18N.en;
  const val = key in table ? table[key] : I18N.en[key];
  return val == null ? key : val;
}

// Language NAMES, locale-aware, one source of truth for the whole UI so neither
// locale leaks the other's script. Full form (langName) for section labels —
// the by-language lens — reuses the lang_* keys: "Japanese" / "日语". Compact
// form (langShort) for the dense inline source→target tag: a single CJK glyph
// in Chinese (日→中), a two-letter code in English (JA→ZH), never the other
// script. Replaces the per-file LANG_SHORT copies sheet.js and learnings.html
// each carried.
const LANG_SHORT = {
  zh: { Japanese: "日", English: "英", Chinese: "中", French: "法",
        Spanish: "西", German: "德", Italian: "意", Korean: "韩", Unknown: "?" },
  en: { Japanese: "JA", English: "EN", Chinese: "ZH", French: "FR",
        Spanish: "ES", German: "DE", Italian: "IT", Korean: "KO", Unknown: "?" },
};
function langShort(name) {
  const m = LANG_SHORT[LOCALE] || LANG_SHORT.en;
  return m[name] || name || "?";
}
function langName(name) {
  if (!name) return "";
  const v = t("lang_" + name);
  return v === "lang_" + name ? name : v;  // t() echoes the key when unmapped
}

// A moment's worth is in the moment, not its clock-time (DESIGN §3.2), so we
// soften the ISO timestamp into something human and let it recede: "today",
// "3 days ago", or — once it's old enough — a warm short date. Locale-aware.
function humanTime(iso) {
  if (!iso) return "";
  const then = new Date(iso);
  if (isNaN(then.getTime())) return "";
  const now = new Date();
  const ms = now - then;
  if (ms < 60000) return t("time_just_now");
  if (then.toDateString() === now.toDateString()) return t("time_today");
  const y = new Date(now);
  y.setDate(now.getDate() - 1);
  if (then.toDateString() === y.toDateString()) return t("time_yesterday");
  const days = Math.floor(ms / 86400000);
  if (days < 7) return t("time_days_ago").replace("{n}", days);
  if (days < 14) return t("time_last_week");
  return new Intl.DateTimeFormat(LOCALE === "zh" ? "zh-CN" : "en-US", {
    month: "short",
    day: "numeric",
  }).format(then);
}

// Fill every element tagged data-i18n / -placeholder / -title / -html from the
// current locale. Call after setLocale (and after any static-DOM rebuild).
function applyStaticI18n(root) {
  root = root || document;
  root.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  root.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  root.querySelectorAll("[data-i18n-title]").forEach((el) => {
    el.title = t(el.dataset.i18nTitle);
  });
  root.querySelectorAll("[data-i18n-html]").forEach((el) => {
    el.innerHTML = t(el.dataset.i18nHtml);
  });
}

// Wire the header's two shared pickers: the first language (#native-lang →
// translation target) and the interface language (#ui-locale → UI locale).
// They are independent settings, EXCEPT the UI follows the first language until
// the user explicitly picks an interface language (the smart default). Loads
// both, localizes the page, persists changes, and routes each page's re-render
// through `onChanged(nativeLang)` (fired once on load and on every change).
async function setupIdentityPicker(onChanged) {
  let native = "English", uiLocale = "en", uiExplicit = false;
  try {
    const id = await (await fetch("/api/identity")).json();
    if (id) {
      if (id.native_lang) native = id.native_lang;
      if (id.ui_locale) uiLocale = id.ui_locale;
      uiExplicit = !!id.ui_locale_set;
    }
  } catch (e) {
    /* fall back to the English UI */
  }
  setLocale(uiLocale);
  applyStaticI18n();

  const nat = document.getElementById("native-lang");
  const ui = document.getElementById("ui-locale");
  const syncUiPicker = () => { if (ui) ui.value = LOCALE; };

  // First language: the translation target (§3.3). While the interface language
  // is still following it (not yet chosen), changing it also moves the UI;
  // once the UI language is explicit, the first language no longer touches it.
  if (nat) {
    nat.value = native;
    nat.addEventListener("change", async () => {
      const next = nat.value;
      nat.disabled = true;
      try {
        const r = await fetch("/api/identity", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ native_lang: next }),
        });
        if (r.ok) {
          native = next;
          if (!uiExplicit) { setLocale(localeFor(next)); applyStaticI18n(); syncUiPicker(); }
          if (onChanged) onChanged(next);
        }
      } catch (e) {
        /* keep the previous selection */
      } finally {
        nat.disabled = false;
      }
    });
  }

  // Interface language: its own setting. Choosing one makes it explicit, so it
  // stops following the first language from here on.
  if (ui) {
    syncUiPicker();
    ui.addEventListener("change", async () => {
      const next = ui.value;
      ui.disabled = true;
      try {
        const r = await fetch("/api/ui-locale", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ locale: next }),
        });
        if (r.ok) {
          uiExplicit = true;
          setLocale(next);
          applyStaticI18n();
          if (onChanged) onChanged(native);
        }
      } catch (e) {
        /* keep the previous selection */
      } finally {
        ui.disabled = false;
      }
    });
  }

  if (onChanged) onChanged(native);
}
