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
      'Everything you translate is stored locally. After enough translations ' +
      'pile up, head to <a href="/learnings">Learnings</a> to see the clusters ' +
      "that have quietly formed in the background.",

    // learnings page
    learnings_hint:
      "What's quietly come together so far. Cards surface on their own as " +
      "terms repeat — keep the ones worth studying and sink the rest. Each " +
      "card keeps the stack of moments it grew from.",
    first_lang_label: "Your first language",
    deck_title: "Your review deck — cards",
    clusters_title: "Clusters",
    by_concept: "By concept",
    by_language: "By language",
    themes_title: "Themes — moments that belong together",
    candidates_title: "Candidates — repeated translations",

    // museum (the shelves on the dunes — the full collection, the list floor)
    nav_museum: "Museum",
    title_museum: "Tideline — museum",
    museum_hint:
      "Everything that's washed up, shelved on the dunes. Browse it by card, " +
      "concept, language, or theme — tap a shell to open what it holds.",
    lens_cards: "Cards",
    lens_concept: "Concept",
    lens_language: "Language",
    lens_theme: "Theme",
    museum_forming: "Still forming",
    back_to_shore: "Back to the shore",

    cards_empty:
      "No cards yet — cards surface on their own once a term repeats enough; " +
      "you keep the ones worth studying and sink the rest.",
    clusters_empty: "No clusters yet. Keep translating and they'll surface on their own.",
    by_language_empty:
      "No learnings yet — once translations repeat, they group by source language here.",
    themes_empty:
      "No themes yet — as related words pile up, they quietly gather into a " +
      "remembered scene you can revisit here.",
    candidates_empty: "No candidates yet.",

    sink: "Sink",
    sink_title: "Sink this card back to sediment",
    reveal_all: "Reveal all",
    mask: "Mask",
    tap_reveal: "tap to reveal",
    tap_recall: "open to recall",
    no_context: "a quiet one — no scene saved",
    moment_one: "moment",
    moment_many: "moments",
    cluster_fallback: "Cluster #",
    theme_fallback: "A theme #",

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

    err_cards: "Couldn't load cards: ",
    err_clusters: "Couldn't load clusters: ",
    err_languages: "Couldn't load language groups: ",
    err_themes: "Couldn't load themes: ",
    err_candidates: "Couldn't load candidates: ",

    lang_Chinese: "Chinese", lang_English: "English", lang_Japanese: "Japanese",
    lang_French: "French", lang_Spanish: "Spanish", lang_German: "German",
    lang_Italian: "Italian", lang_Korean: "Korean",
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
      '你翻译的一切都只存在本地。等翻译攒得够多,去<a href="/learnings">学习</a>页' +
      "看那些在后台悄悄成形的聚类。",

    // learnings page
    learnings_hint:
      "到目前为止悄悄沉淀下来的东西。词反复出现,卡片会自己浮现——留下值得学的," +
      "把其余的沉回去。每张卡都留着它生长出来的那叠片刻。",
    first_lang_label: "你的第一语言",
    deck_title: "你的复习卡组",
    clusters_title: "聚类",
    by_concept: "按概念",
    by_language: "按语言",
    themes_title: "主题 — 属于同一段的片刻",
    candidates_title: "候选 — 反复出现的翻译",

    // 陈列馆(沙丘上的货架 — 完整收藏,也是 list 退路)
    nav_museum: "陈列馆",
    title_museum: "Tideline — 陈列馆",
    museum_hint:
      "冲上岸的一切,陈列在沙丘的货架上。按卡片、概念、语言或主题来逛——" +
      "点一只贝壳,看它收着什么。",
    lens_cards: "卡片",
    lens_concept: "概念",
    lens_language: "语言",
    lens_theme: "主题",
    museum_forming: "还在成形",
    back_to_shore: "回到海岸",

    cards_empty:
      "还没有卡片——一个词反复出现得够多,卡片会自己浮现;你留下值得学的," +
      "把其余的沉回去。",
    clusters_empty: "还没有聚类。继续翻译,它们会自己浮现。",
    by_language_empty: "还没有沉淀——翻译开始重复后,会在这里按原文语言归拢。",
    themes_empty: "还没有主题——相关的词攒多了,会在这里悄悄聚成一段可以回访的记忆。",
    candidates_empty: "还没有候选。",

    sink: "沉底",
    sink_title: "把这张卡沉回沉淀层",
    reveal_all: "全部揭开",
    mask: "重新遮住",
    tap_reveal: "点一下揭开",
    tap_recall: "翻开回忆",
    no_context: "安静的一次 — 没留下情景",
    moment_one: "个片刻",
    moment_many: "个片刻",
    cluster_fallback: "聚类 #",
    theme_fallback: "主题 #",

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

    err_cards: "卡片加载失败:",
    err_clusters: "聚类加载失败:",
    err_languages: "语言分组加载失败:",
    err_themes: "主题加载失败:",
    err_candidates: "候选加载失败:",

    lang_Chinese: "中文", lang_English: "英语", lang_Japanese: "日语",
    lang_French: "法语", lang_Spanish: "西班牙语", lang_German: "德语",
    lang_Italian: "意大利语", lang_Korean: "韩语",
  },
};

let LOCALE = "en";

function localeFor(nativeLang) {
  return nativeLang === "Chinese" ? "zh" : "en";
}

function setLocale(nativeLang) {
  LOCALE = localeFor(nativeLang);
  document.documentElement.lang = LOCALE === "zh" ? "zh-Hans" : "en";
}

function t(key) {
  const table = I18N[LOCALE] || I18N.en;
  const val = key in table ? table[key] : I18N.en[key];
  return val == null ? key : val;
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

// Wire the header's shared first-language picker (#native-lang). Loads the
// current value, localizes the page, and on change persists it + re-localizes
// + runs the page's own refresh hook. `onChanged(lang)` fires once on load and
// again on every change, so each page routes its own re-render through it.
async function setupIdentityPicker(onChanged) {
  let lang = "English";
  try {
    const r = await fetch("/api/identity");
    const id = await r.json();
    if (id && id.native_lang) lang = id.native_lang;
  } catch (e) {
    /* fall back to the English UI */
  }
  setLocale(lang);
  applyStaticI18n();
  const sel = document.getElementById("native-lang");
  if (sel) {
    sel.value = lang;
    sel.addEventListener("change", async () => {
      const next = sel.value;
      sel.disabled = true;
      try {
        const r = await fetch("/api/identity", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ native_lang: next }),
        });
        if (r.ok) {
          setLocale(next);
          applyStaticI18n();
          if (onChanged) onChanged(next);
        }
      } catch (e) {
        /* keep the previous selection */
      } finally {
        sel.disabled = false;
      }
    });
  }
  if (onChanged) onChanged(lang);
}
