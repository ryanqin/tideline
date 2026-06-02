// The living shore — a stylized, time-driven scene (DESIGN §10).
//
// Pure CSS/SVG/DOM, no game engine (§10.8). Given a moment in time it paints a
// WARM-ONLY shore (§10 locked decision: never blue or grey) — palest cream at
// noon, amber/coral at golden hour, deep ember at night, the hue always warm.
// A soft warm bloom (sun by day, dimmer moon by night) arcs across via bodyAt;
// the tide is semidiurnal, drifting ~50 min a day, breathing bigger at new/full
// moon (§10.3, §10.6). Sea and tide are drawn as a few warm lines, not colour
// blocks (§10.2). Slice 1 is the empty shore: no shells yet. The time is the
// device clock unless overridden by hand (?h=/?t=/?day=) — also how the scene
// is screenshotted across the day.

(function (global) {
  "use strict";

  const TAU = Math.PI * 2;
  const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));
  const lerp = (a, b, t) => a + (b - a) * t;
  const lerpRGB = (a, b, t) => [
    Math.round(lerp(a[0], b[0], t)),
    Math.round(lerp(a[1], b[1], t)),
    Math.round(lerp(a[2], b[2], t)),
  ];
  const css = (c, alpha) =>
    alpha == null ? `rgb(${c[0]},${c[1]},${c[2]})` : `rgba(${c[0]},${c[1]},${c[2]},${alpha})`;

  // Sky keyframes around the clock. Each: three sky stops (top→horizon), the
  // sea and sand tints under that light, plus the sun/moon's glow. Hours wrap
  // (21 → 24/0). **Warm-only (§10 locked decision): never blue or grey.** Time
  // of day is carried by how light or deep the warmth is — palest cream at
  // noon, saturated amber/coral at golden hour (18:00 = the shipped palette the
  // rest of the UI lives in), deep ember at night — the hue stays warm always.
  const SKY = [
    { h: 0,    top: [46, 36, 40],    mid: [66, 50, 50],    hor: [98, 70, 60],    sea: [40, 32, 34],   sand: [86, 68, 60],    glow: [214, 178, 150] },
    { h: 5,    top: [86, 64, 64],    mid: [134, 96, 86],   hor: [182, 124, 100], sea: [74, 58, 56],   sand: [124, 98, 84],   glow: [238, 192, 160] },
    { h: 6.5,  top: [190, 142, 128], mid: [234, 178, 142], hor: [248, 208, 160], sea: [176, 138, 114], sand: [218, 186, 152], glow: [255, 224, 184] },
    { h: 9,    top: [234, 216, 196], mid: [245, 230, 208], hor: [250, 238, 218], sea: [208, 186, 158], sand: [233, 216, 188], glow: [255, 246, 224] },
    { h: 12,   top: [241, 227, 207], mid: [248, 237, 219], hor: [252, 243, 227], sea: [214, 194, 166], sand: [237, 221, 195], glow: [255, 251, 238] },
    { h: 16,   top: [237, 212, 186], mid: [247, 226, 198], hor: [251, 232, 202], sea: [208, 178, 146], sand: [233, 210, 178], glow: [255, 242, 212] },
    { h: 18,   top: [200, 132, 108], mid: [232, 160, 112], hor: [248, 196, 128], sea: [168, 118, 92],  sand: [224, 176, 132], glow: [255, 198, 130] },
    { h: 19.5, top: [122, 80, 76],   mid: [182, 110, 86],  hor: [218, 136, 92],  sea: [98, 70, 64],   sand: [162, 120, 96],  glow: [248, 168, 118] },
    { h: 21,   top: [60, 46, 46],    mid: [86, 62, 58],    hor: [120, 82, 68],   sea: [48, 38, 38],   sand: [98, 76, 66],    glow: [220, 182, 152] },
  ];

  // Linearly interpolate the keyframes for a given fractional hour [0,24).
  function skyAt(hour) {
    hour = ((hour % 24) + 24) % 24;
    let lo = SKY[SKY.length - 1], hi = SKY[0], loH = lo.h - 24, hiH = hi.h;
    for (let i = 0; i < SKY.length; i++) {
      if (SKY[i].h <= hour) { lo = SKY[i]; loH = lo.h; hi = SKY[(i + 1) % SKY.length]; hiH = hi.h <= lo.h ? hi.h + 24 : hi.h; }
    }
    const t = hiH === loH ? 0 : clamp((hour - loH) / (hiH - loH), 0, 1);
    const out = {};
    for (const k of ["top", "mid", "hor", "sea", "sand", "glow"]) out[k] = lerpRGB(lo[k], hi[k], t);
    out.daylight = clamp((skyBrightness(hour)), 0, 1);
    return out;
  }

  // 0 at deep night, 1 at midday — drives star and glow opacity.
  function skyBrightness(hour) {
    if (hour >= 7 && hour <= 17) return 1;
    if (hour >= 5 && hour < 7) return (hour - 5) / 2;
    if (hour > 17 && hour <= 20) return 1 - (hour - 17) / 3;
    return 0;
  }

  // Moon illumination from a known new moon (2000-01-06 18:14 UTC), synodic
  // month 29.530588853 d. Good enough for a stylized crescent.
  function moonPhase(date) {
    const synodic = 29.530588853;
    const newMoon = Date.UTC(2000, 0, 6, 18, 14) / 86400000; // in days
    const days = date.getTime() / 86400000 - newMoon;
    const age = ((days % synodic) + synodic) % synodic; // 0..synodic
    const frac = age / synodic;                          // 0=new .. .5=full
    const illum = (1 - Math.cos(TAU * frac)) / 2;         // 0..1
    return { illum, waxing: frac < 0.5, age };
  }

  // Where the sun or moon sits, as fractions of the sky box. The sun owns
  // ~6→18; the moon takes the night. Both rise at the left horizon, arc to a
  // noon/midnight peak, set at the right.
  function bodyAt(hour) {
    const sunUp = hour >= 6 && hour <= 18;
    const frac = sunUp ? (hour - 6) / 12 : (((hour - 18 + 24) % 24)) / 12;
    return {
      kind: sunUp ? "sun" : "moon",
      x: lerp(0.12, 0.88, frac),
      // 1 = at horizon, 0 = at peak; sine arc.
      lift: Math.sin(clamp(frac, 0, 1) * Math.PI),
    };
  }

  // Tide level in [0,1]. Principal lunar semidiurnal (M2 ≈ 12.4206 h) keyed to
  // absolute time, so highs fall ~50 min later each solar day on their own.
  // Spring/neap: amplitude swells near new/full moon, flattens at the quarters.
  function tideAt(date) {
    const hours = date.getTime() / 3600000;
    const { illum } = moonPhase(date);
    const springNeap = 0.55 + 0.45 * Math.abs(2 * illum - 1); // 1 at new/full, ~.55 at quarter
    const level = 0.5 + 0.5 * springNeap * Math.cos(TAU * (hours / 12.4206));
    return clamp(level, 0, 1);
  }

  // --- scene drawing -------------------------------------------------------
  // Drawn at the container's real pixel size: the viewBox matches the viewport
  // aspect exactly, so nothing is cropped or stretched, and the sun/moon (with
  // their glow) are clamped to stay fully on screen whatever the shape.

  function wavePath(w, y, amp, len, phase, bottomY) {
    let d = `M 0 ${y.toFixed(1)}`;
    for (let x = 0; x <= w; x += len / 2) {
      const yy = y + Math.sin((x / len) * TAU + phase) * amp;
      d += ` Q ${(x + len / 4).toFixed(1)} ${(yy + amp).toFixed(1)} ${(x + len / 2).toFixed(1)} ${y.toFixed(1)}`;
    }
    if (bottomY != null) d += ` L ${w.toFixed(1)} ${bottomY.toFixed(1)} L 0 ${bottomY.toFixed(1)} Z`;
    return d;
  }

  // All the geometry + warm tints for a moment, shared by the static draw and
  // the breathing loop (below) so the two can never drift apart.
  function sceneGeom(date, w, h) {
    const hour = date.getHours() + date.getMinutes() / 60;
    const s = skyAt(hour);
    const body = bodyAt(hour);
    const tide = tideAt(date);
    const skyBot = h * 0.46;                            // horizon line
    const sandMid = h * 0.68;                           // sea meets sand at mid tide
    const surfY = sandMid - (tide - 0.5) * (h * 0.13);  // surf rides with the tide
    // Sun/moon as a soft warm bloom — light through haze, never a hard disc
    // (§10: warm-only, no cheap celestial coin). It arcs across the day via
    // bodyAt; the moon is just a dimmer, smaller bloom of the same warmth.
    const isSun = body.kind === "sun";
    const bloomR = clamp(Math.min(w, h) * (isSun ? 0.3 : 0.2), 110, 360);
    const peakY = skyBot * 0.3;
    const bodyX = clamp(body.x * w, w * 0.14, w * 0.86);
    const bodyY = lerp(skyBot * 0.88, peakY, body.lift);
    const coreA = isSun ? 0.55 : 0.32;
    // sea sheen + tideline marks are warm lines, not bright white (§10.2)
    const warmHi = lerpRGB(s.glow, [255, 250, 242], 0.5);
    return { hour, s, skyBot, surfY, bloomR, bodyX, bodyY, coreA, warmHi };
  }

  function sceneSVG(date, w, h) {
    const g = sceneGeom(date, w, h);
    const { s, skyBot, surfY, bloomR, bodyX, bodyY, coreA, warmHi, hour } = g;

    // The shore is BUILT from warm contour lines over one soft shade wash — no
    // colour blocks (§10.2). A field of faint lines, finer/lighter near the
    // horizon and heavier/deeper toward your feet, reads as sea then sand
    // through line density + shade alone, all in the one warm family.
    // Depth the way it was asked for: far = deep + dense, near (the sand at
    // your feet) = pale + open. Lines bunch at the horizon and open out toward
    // you; shade and weight fade from deep-far down to pale-near.
    const farLine = lerpRGB(s.sand, [70, 50, 40], 0.45);   // deep, at the far horizon
    const nearLine = lerpRGB(s.hor, s.sand, 0.35);         // pale, at your feet
    let field = "";
    const N = 17;
    for (let i = 1; i <= N; i++) {
      const d = i / (N + 1);                              // 0 far → 1 near
      const y = skyBot + d * d * (h - skyBot);            // perspective: dense far, open near
      const amp = h * (0.003 + d * 0.01);
      const len = w * (0.55 - d * 0.2);
      const a = 0.4 - d * 0.27;                           // strong far → faint near
      field += `<path d="${wavePath(w, y, amp, len, hour * 0.5 + i * 1.7)}" fill="none" stroke="${css(lerpRGB(farLine, nearLine, d), a)}" stroke-width="${(1.5 - d * 0.6).toFixed(2)}"/>`;
    }

    return `
<svg viewBox="0 0 ${w} ${h}" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="A warm shore at ${labelTime(hour)}">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${css(s.top)}"/>
      <stop offset="0.6" stop-color="${css(s.mid)}"/>
      <stop offset="1" stop-color="${css(s.hor)}"/>
    </linearGradient>
    <radialGradient id="bloom">
      <stop offset="0" stop-color="${css(s.glow, coreA)}"/>
      <stop offset="0.45" stop-color="${css(s.glow, coreA * 0.3)}"/>
      <stop offset="1" stop-color="${css(s.glow, 0)}"/>
    </radialGradient>
    <linearGradient id="ground" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${css(lerpRGB(s.sand, [70, 50, 40], 0.22))}"/>
      <stop offset="1" stop-color="${css(lerpRGB(s.hor, s.sand, 0.42))}"/>
    </linearGradient>
  </defs>

  <rect x="0" y="0" width="${w}" height="${skyBot.toFixed(1)}" fill="url(#sky)"/>
  <circle id="sh-bloom" cx="${bodyX.toFixed(1)}" cy="${bodyY.toFixed(1)}" r="${bloomR.toFixed(1)}" fill="url(#bloom)"/>

  <!-- the shore: one warm shade wash, its depth drawn entirely by contour lines -->
  <rect x="0" y="${skyBot.toFixed(1)}" width="${w}" height="${(h - skyBot).toFixed(1)}" fill="url(#ground)"/>
  ${field}

  <!-- two sea lines that breathe (animated), woven into the field -->
  <path id="sh-sheen1" d="${wavePath(w, skyBot + (surfY - skyBot) * 0.34, h * 0.004, w * 0.5, hour * 0.6)}" fill="none" stroke="${css(warmHi, 0.18)}" stroke-width="1.5"/>
  <path id="sh-sheen2" d="${wavePath(w, skyBot + (surfY - skyBot) * 0.66, h * 0.005, w * 0.42, hour)}" fill="none" stroke="${css(warmHi, 0.22)}" stroke-width="1.5"/>

  <!-- the living tideline: the brightest line, where water meets sand -->
  <path id="sh-surf-fill" d="${wavePath(w, surfY, h * 0.012, w * 0.34, hour * 1.3, surfY + h * 0.045)}" fill="${css(warmHi, 0.2)}"/>
  <path id="sh-surf-line" d="${wavePath(w, surfY, h * 0.012, w * 0.34, hour * 1.3)}" fill="none" stroke="${css(warmHi, 0.75)}" stroke-width="2.25"/>
  <path id="sh-mark" d="${wavePath(w, surfY - h * 0.07, h * 0.01, w * 0.4, hour * 0.9)}" fill="none" stroke="${css(s.sand, 0.5)}" stroke-width="1.5"/>
</svg>`;
  }

  // The shore breathing: a slow, organic ambient loop (DESIGN §10 — alive but
  // calm, never a bouncy loop). The surf eases in and out on the sand, the sea
  // sheen drifts, the warm bloom shimmers — all on long, incommensurate periods
  // so it never reads as a repeat. Honours prefers-reduced-motion (stays still).
  function startBreathing(container, date) {
    if (container.__shoreRAF) global.cancelAnimationFrame(container.__shoreRAF);
    container.__shoreRAF = null;
    const reduce = global.matchMedia && global.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce || !global.requestAnimationFrame) return;
    const svg = container.querySelector("svg");
    if (!svg) return;
    const rect = container.getBoundingClientRect ? container.getBoundingClientRect() : null;
    const w = Math.max(1, Math.round((rect && rect.width) || container.clientWidth || 1000));
    const h = Math.max(1, Math.round((rect && rect.height) || container.clientHeight || 1000));
    const g = sceneGeom(date, w, h);
    const seaH = g.surfY - g.skyBot;
    const pick = (id) => svg.getElementById ? svg.getElementById(id) : svg.querySelector("#" + id);
    const bloom = pick("sh-bloom"), sheen1 = pick("sh-sheen1"), sheen2 = pick("sh-sheen2"),
      fill = pick("sh-surf-fill"), line = pick("sh-surf-line"), mark = pick("sh-mark");
    const SPEED = 3; // one knob for the whole breath's pace (higher = livelier)
    const t0 = global.performance ? global.performance.now() : 0;
    function frame(now) {
      const t = (now - t0) / 1000 * SPEED;
      // two summed sines of unrelated periods → organic, no obvious loop
      const breathe = Math.sin(t / 9) * 0.7 + Math.sin(t / 5.3) * 0.3; // ~[-1,1]
      const sy = g.surfY + breathe * h * 0.009;                        // surf eases in/out
      const surfPhase = g.hour * 1.3 + t * 0.08;
      if (sheen1) sheen1.setAttribute("d", wavePath(w, g.skyBot + seaH * 0.34 + Math.sin(t / 6) * h * 0.002, h * 0.004, w * 0.5, g.hour * 0.6 + t * 0.06));
      if (sheen2) sheen2.setAttribute("d", wavePath(w, g.skyBot + seaH * 0.66 + Math.sin(t / 7.5 + 1) * h * 0.002, h * 0.005, w * 0.42, g.hour + t * 0.05));
      if (fill) fill.setAttribute("d", wavePath(w, sy, h * 0.012, w * 0.34, surfPhase, sy + h * 0.05));
      if (line) line.setAttribute("d", wavePath(w, sy, h * 0.012, w * 0.34, surfPhase));
      if (mark) mark.setAttribute("d", wavePath(w, sy - h * 0.07, h * 0.01, w * 0.4, g.hour * 0.9 + t * 0.04));
      if (bloom) {
        bloom.setAttribute("cx", (g.bodyX + Math.sin(t / 13) * 5).toFixed(1));
        bloom.setAttribute("cy", (g.bodyY + Math.sin(t / 11 + 2) * 4).toFixed(1));
        bloom.setAttribute("opacity", (0.92 + Math.sin(t / 6) * 0.08).toFixed(3));
      }
      container.__shoreRAF = global.requestAnimationFrame(frame);
    }
    container.__shoreRAF = global.requestAnimationFrame(frame);
  }

  // A minimalist, warm tideline (DESIGN §10.2): not a colour block but a few
  // lines — the marks a receding tide leaves on the sand — over a wash that
  // melts straight into the page. Deliberately warm-only (gold by day, ember by
  // evening, never blue or grey); the day/night sky lives in the full shore.
  const STRIP_GOLD = [205, 170, 122];
  const STRIP_EMBER = [176, 116, 72];
  function stripSVG(date, w, h) {
    const hour = date.getHours() + date.getMinutes() / 60;
    const tide = tideAt(date);
    const evening = clamp(Math.abs(hour - 13) / 9, 0, 1); // 0 midday → 1 deep evening
    const warm = lerpRGB(STRIP_GOLD, STRIP_EMBER, evening);
    const surfY = h * (0.6 - (tide - 0.5) * 0.3);          // the active surf rides with the tide
    const l2 = surfY - h * 0.16;                           // the last wave's mark
    const l3 = surfY - h * 0.3;                            // an older, fainter mark
    return `
<svg viewBox="0 0 ${w} ${h}" width="100%" height="100%" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="cl-wash" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${css(warm, 0)}"/><stop offset="1" stop-color="${css(warm, 0.16)}"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="${w}" height="${h}" fill="url(#cl-wash)"/>
  <path d="${wavePath(w, l3, h * 0.05, w * 0.44, hour * 0.7)}" fill="none" stroke="${css(warm, 0.26)}" stroke-width="1.5"/>
  <path d="${wavePath(w, l2, h * 0.06, w * 0.36, hour)}" fill="none" stroke="${css(warm, 0.42)}" stroke-width="1.75"/>
  <path d="${wavePath(w, surfY, h * 0.07, w * 0.3, hour * 1.3)}" fill="none" stroke="${css([255, 250, 242], 0.78)}" stroke-width="2"/>
</svg>`;
  }

  function labelTime(hour) {
    const h = Math.floor(hour), m = Math.floor((hour - h) * 60);
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
  }

  // Resolve the moment to draw: device clock, or an override for travel / demo
  // / screenshots — ?h=18.5 (hour) or ?t=ISO, optional ?day=YYYY-MM-DD.
  function resolveDate(opts) {
    opts = opts || {};
    if (opts.date) return opts.date;
    const p = new URLSearchParams(global.location ? global.location.search : "");
    if (p.has("t")) { const d = new Date(p.get("t")); if (!isNaN(d.getTime())) return d; }
    const base = p.has("day") ? new Date(p.get("day") + "T12:00:00") : new Date();
    if (p.has("h")) {
      const hf = parseFloat(p.get("h"));
      if (!isNaN(hf)) { base.setHours(Math.floor(hf), Math.round((hf % 1) * 60), 0, 0); }
    }
    return base;
  }

  function render(container, opts) {
    const date = resolveDate(opts);
    const rect = container.getBoundingClientRect ? container.getBoundingClientRect() : null;
    const w = Math.max(1, Math.round((rect && rect.width) || container.clientWidth || (global.innerWidth || 1000)));
    const h = Math.max(1, Math.round((rect && rect.height) || container.clientHeight || (global.innerHeight || 1000)));
    container.innerHTML = sceneSVG(date, w, h);
    startBreathing(container, date);
    return { date, tide: tideAt(date), phase: moonPhase(date), w, h };
  }

  // --- creatures: what the tide has left ashore (DESIGN §10.5) -------------
  // Relation type is something you can SEE rather than a toggle: a shell = a
  // concept cluster (synonyms), a crab = a theme (a remembered scene),
  // sea-glass = a single card. Drawn in the SAME language as the shore — warm,
  // rounded LINES, never colour blocks (§10.2) — small and calm, a scattered
  // few (never a wall; that restraint is what fixes overload). Each is a real
  // focusable button (§10.8), laid in its own overlay layer so the breathing
  // repaint of the scene never wipes it.

  // Each glyph is line art in a 0..48 box; `stroke="currentColor"` so the warm
  // ink is set once on the button, and a faint same-colour fill lifts it off
  // the contour field without ever becoming a block. Rounded joins = soft, a
  // little cute, hand-drawn rather than iconographic.
  const GLYPHS = {
    // a scallop: a little fan, ribs radiating from the hinge
    shell:
      '<path d="M24 41C12 38 7 24 8.5 15.5 24 8 39.5 15.5 39.5 15.5 41 24 36 38 24 41Z" fill="currentColor" fill-opacity="0.2" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>' +
      '<path d="M24 41 13 18M24 41 19 13.5M24 41 24 12M24 41 29 13.5M24 41 35 18" fill="none" stroke="currentColor" stroke-width="1.3" stroke-opacity="0.7" stroke-linecap="round"/>',
    // a round little crab: a domed shell, two dot eyes, raised claws, legs
    crab:
      '<path d="M11 30c0-7.5 6-12 13-12s13 4.5 13 12c-2 3-24 3-26 0Z" fill="currentColor" fill-opacity="0.2" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>' +
      '<path d="M20 18.5v-3M28 18.5v-3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>' +
      '<circle cx="20" cy="13.5" r="1.7" fill="currentColor"/><circle cx="28" cy="13.5" r="1.7" fill="currentColor"/>' +
      '<path d="M11.5 25c-4-1.5-6.5 0.5-6 4M36.5 25c4-1.5 6.5 0.5 6 4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>' +
      '<path d="M13 31l-5 4.5M15.5 33l-4 5.5M35 31l5 4.5M32.5 33l4 5.5" stroke="currentColor" stroke-width="1.3" stroke-opacity="0.8" stroke-linecap="round"/>',
    // sea-glass: a soft frosted pebble with one inner gleam
    glass:
      '<path d="M17 14Q31 10 37 20 41 32 28 36 14 38 12 26 11 17 17 14Z" fill="currentColor" fill-opacity="0.22" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>' +
      '<path d="M18 20.5Q23 17.5 27 20.5" fill="none" stroke="currentColor" stroke-width="1.3" stroke-opacity="0.65" stroke-linecap="round"/>',
  };
  const CREATURE_NOUN = { shell: "贝壳", crab: "螃蟹", glass: "海玻璃" };

  // A tiny deterministic hash → a fraction in [0,1). Same id+salt always gives
  // the same number, so a repaint/resize never makes the scatter jump.
  function hashFrac(str, salt) {
    let h = (2166136261 ^ (salt || 0)) >>> 0;
    for (let i = 0; i < str.length; i++) h = Math.imul(h ^ str.charCodeAt(i), 16777619) >>> 0;
    return (h % 100000) / 100000;
  }

  // Lay the ashore creatures over the scene as focusable buttons (§10.8). They
  // settle in the near sand — the open beach below the surf, where it's pale —
  // spread into even columns with per-item jitter (deterministic by id), each
  // softly rotated. A freshly-arrived one carries a faint glint (§10.2): an
  // in-app ambient cue, never a badge or count.
  function renderCreatures(host, creatures, opts) {
    opts = opts || {};
    creatures = creatures || [];
    const date = opts.date || resolveDate(opts);
    const rect = host.getBoundingClientRect ? host.getBoundingClientRect() : null;
    const w = Math.max(1, Math.round((rect && rect.width) || host.clientWidth || 1000));
    const h = Math.max(1, Math.round((rect && rect.height) || host.clientHeight || 1000));
    const g = sceneGeom(date, w, h);
    // the near-sand band: a little below the surf, down toward your feet
    const top = clamp(g.surfY / h + 0.06, 0.52, 0.72);
    const bottom = 0.88;
    const minSide = Math.min(w, h);
    // warm ink that reads against the pale near-sand: a deep warm brown,
    // lifted a touch so the line art stays calm but never invisible (§10.5).
    // EVERY creature shares this ink — a fresh arrival is NOT a paler/glowing
    // shape (that washed the color out); its freshness is a small Zelda-style
    // sparkle that twinkles at one point on it (added below), nothing more.
    const ink = css(lerpRGB(g.s.hor, [78, 48, 34], 0.72));
    const n = Math.max(1, creatures.length);
    // keep the scatter inset from the frame so a shell — and the name under it —
    // never crowds or clips an edge; the clamp + corner dodge below also steer
    // clear of the bottom-right, where the compose button rests.
    const mx = 0.12;
    // a name never spills past its own column — at rest it ellipsizes to fit
    // (brief is fine), opening to the full title on hover / keyboard focus.
    const capMax = Math.max(56, Math.round(0.9 * (1 - 2 * mx) * w / n));
    let html = "";
    creatures.forEach((c, i) => {
      const id = c.id || String(i);
      const depth = hashFrac(id, 2);                       // 0 = far (up), 1 = near (down)
      const px = Math.round((0.07 + depth * 0.05) * minSide);  // nearer reads larger
      let x = (mx + ((i + 0.5) / n) * (1 - 2 * mx)) * 100  // even columns, inset
            + (hashFrac(id, 1) - 0.5) * (0.5 / n) * 100;   // gentle per-item jitter
      let y = (top + depth * (bottom - top)) * 100;
      const rot = (hashFrac(id, 3) - 0.5) * 26;            // ±13°
      // keep the whole glyph (and its name) on screen, then lift any that would
      // land in the compose button's corner.
      const half = (px / 2 / w) * 100;
      x = clamp(x, half + 1.5, 100 - half - 1.5);
      if (x > 70 && y > 80) y = 80;
      const kind = GLYPHS[c.kind] ? c.kind : "glass";
      const label = (CREATURE_NOUN[kind] || "") + (c.label ? " · " + c.label : "");
      html +=
        `<button type="button" class="shore-shell kind-${kind}${c.fresh ? " is-new" : ""}"` +
        ` style="left:${x.toFixed(2)}%;top:${y.toFixed(2)}%;width:${px}px;--rot:${rot.toFixed(1)}deg;--cap-max:${capMax}px;color:${ink}"` +
        ` data-id="${id}" data-kind="${kind}" aria-label="${label}">` +
        `<svg viewBox="0 0 48 48" aria-hidden="true">${GLYPHS[kind]}</svg>` +
        (c.fresh
          ? '<span class="shell-spark" aria-hidden="true"><svg viewBox="0 0 24 24">' +
            '<path d="M12 0 Q13 11 24 12 Q13 13 12 24 Q11 13 0 12 Q11 11 12 0 Z"/>' +
            '</svg></span>'
          : "") +
        `<span class="shell-cap">${c.label || CREATURE_NOUN[kind] || ""}</span>` +
        `</button>`;
    });
    host.innerHTML = html;
    return creatures.length;
  }

  // Render just the coastline band (DESIGN §10.2) into a short container.
  function renderStrip(container, opts) {
    const date = resolveDate(opts);
    const rect = container.getBoundingClientRect ? container.getBoundingClientRect() : null;
    const w = Math.max(1, Math.round((rect && rect.width) || container.clientWidth || (global.innerWidth || 360)));
    const h = Math.max(1, Math.round((rect && rect.height) || container.clientHeight || 116));
    container.innerHTML = stripSVG(date, w, h);
    return { date, tide: tideAt(date) };
  }

  global.Shore = { render, renderStrip, renderCreatures, skyAt, tideAt, moonPhase, bodyAt, resolveDate, labelTime };
})(typeof window !== "undefined" ? window : globalThis);
