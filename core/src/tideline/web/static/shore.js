// The living shore — a stylized, time-driven scene (DESIGN §10).
//
// Pure CSS/SVG/DOM, no game engine (§10.8). Given a moment in time it paints
// the sky (dawn / day / golden-hour / night), arcs the sun or moon across it
// with the right lunar phase, and sets the tide — semidiurnal, drifting ~50 min
// a day, breathing bigger at new/full moon (§10.3, §10.6). Slice 1 is the empty
// shore: no shells yet. The time is the device clock unless overridden by hand
// (§10.6), which is also how the scene is screenshotted across the day.

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

  // Sky keyframes around the clock. Each: the three sky stops (top→horizon),
  // the sea and sand tints under that light, plus the colour of the sun/moon's
  // glow. Hours wrap (21 → 24/0). Tuned so 18:00 lands on the shipped
  // golden-hour palette — that dusk frame is where the rest of the UI lives.
  const SKY = [
    { h: 0,    top: [24, 28, 52],   mid: [34, 40, 72],    hor: [52, 58, 92],    sea: [18, 26, 52],   sand: [70, 70, 86],    glow: [206, 214, 240] },
    { h: 5,    top: [40, 42, 80],   mid: [86, 76, 108],   hor: [156, 116, 124], sea: [46, 54, 86],   sand: [104, 96, 104],  glow: [240, 210, 200] },
    { h: 6.5,  top: [92, 104, 156], mid: [214, 152, 138], hor: [248, 200, 150], sea: [112, 122, 152], sand: [206, 180, 152], glow: [255, 222, 174] },
    { h: 9,    top: [122, 166, 212], mid: [182, 208, 232], hor: [228, 236, 242], sea: [120, 162, 188], sand: [228, 208, 178], glow: [255, 244, 214] },
    { h: 12,   top: [138, 184, 224], mid: [190, 216, 238], hor: [226, 238, 246], sea: [120, 170, 196], sand: [233, 214, 184], glow: [255, 250, 230] },
    { h: 16,   top: [150, 180, 216], mid: [210, 212, 222], hor: [246, 226, 200], sea: [130, 166, 186], sand: [232, 210, 178], glow: [255, 238, 206] },
    { h: 18,   top: [96, 112, 166], mid: [236, 162, 120], hor: [250, 200, 120], sea: [120, 110, 136], sand: [226, 182, 140], glow: [255, 192, 120] },
    { h: 19.5, top: [50, 56, 102],  mid: [122, 82, 112],  hor: [222, 122, 92],  sea: [62, 64, 98],   sand: [150, 122, 120], glow: [240, 158, 120] },
    { h: 21,   top: [28, 32, 60],   mid: [40, 46, 80],    hor: [60, 64, 100],   sea: [22, 30, 56],   sand: [78, 76, 90],    glow: [210, 216, 238] },
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

  function sceneSVG(date, w, h) {
    const hour = date.getHours() + date.getMinutes() / 60;
    const s = skyAt(hour);
    const body = bodyAt(hour);
    const tide = tideAt(date);
    const phase = moonPhase(date);

    const skyBot = h * 0.43;                          // horizon
    const sandMid = h * 0.66;                         // sea meets sand at mid tide
    const surfY = sandMid - (tide - 0.5) * (h * 0.14); // surf rides up/down with the tide

    // Sun/moon: disc + glow clamped inside the canvas at every aspect, so it
    // never spills off the top or the sides at the peak/edges of its arc.
    const r = clamp(Math.min(w, h) * 0.062, 26, 58);
    const glowR = r * 2.4;
    const peakY = Math.max(glowR + 6, h * 0.17);
    const bodyX = clamp(body.x * w, glowR + 4, w - glowR - 4);
    const bodyY = lerp(skyBot, peakY, body.lift);

    const starOpacity = clamp(1 - s.daylight, 0, 1) * 0.9;
    let stars = "";
    if (starOpacity > 0.05) {
      for (let i = 0; i < 60; i++) {
        const x = (i * 137.5) % w;
        const y = (i * 311.7) % (skyBot * 0.92);
        const rr = i % 5 === 0 ? 2.2 : 1.3;
        const tw = 0.4 + ((i * 53) % 60) / 100;
        stars += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${rr}" fill="#fff" opacity="${(starOpacity * tw).toFixed(2)}"/>`;
      }
    }

    const sunMoon =
      body.kind === "sun"
        ? `<circle cx="${bodyX.toFixed(1)}" cy="${bodyY.toFixed(1)}" r="${glowR.toFixed(1)}" fill="url(#glow)"/>
           <circle cx="${bodyX.toFixed(1)}" cy="${bodyY.toFixed(1)}" r="${r.toFixed(1)}" fill="${css(s.glow)}"/>`
        : `<circle cx="${bodyX.toFixed(1)}" cy="${bodyY.toFixed(1)}" r="${(glowR * 0.92).toFixed(1)}" fill="url(#glow)"/>
           ${moonSVG(bodyX, bodyY, r, phase, s)}`;

    return `
<svg viewBox="0 0 ${w} ${h}" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="A shore at ${labelTime(hour)}">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${css(s.top)}"/>
      <stop offset="0.55" stop-color="${css(s.mid)}"/>
      <stop offset="1" stop-color="${css(s.hor)}"/>
    </linearGradient>
    <linearGradient id="sea" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${css(s.hor)}"/>
      <stop offset="0.5" stop-color="${css(s.sea)}"/>
      <stop offset="1" stop-color="${css(lerpRGB(s.sea, s.sand, 0.4))}"/>
    </linearGradient>
    <linearGradient id="sand" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${css(lerpRGB(s.sand, s.sea, 0.25))}"/>
      <stop offset="0.18" stop-color="${css(s.sand)}"/>
      <stop offset="1" stop-color="${css(lerpRGB(s.sand, [40, 32, 28], 0.18))}"/>
    </linearGradient>
    <radialGradient id="glow">
      <stop offset="0" stop-color="${css(s.glow, 0.55)}"/>
      <stop offset="1" stop-color="${css(s.glow, 0)}"/>
    </radialGradient>
  </defs>

  <rect x="0" y="0" width="${w}" height="${skyBot.toFixed(1)}" fill="url(#sky)"/>
  ${stars}
  ${sunMoon}

  <!-- sea, from horizon down to the surf line -->
  <rect x="0" y="${skyBot.toFixed(1)}" width="${w}" height="${(surfY - skyBot).toFixed(1)}" fill="url(#sea)"/>
  <path d="${wavePath(w, skyBot + h * 0.07, h * 0.004, w * 0.26, hour)}" fill="none" stroke="${css(s.glow, 0.12)}" stroke-width="2"/>
  <path d="${wavePath(w, skyBot + h * 0.15, h * 0.005, w * 0.32, hour + 2)}" fill="none" stroke="${css(s.glow, 0.1)}" stroke-width="2"/>

  <!-- sand -->
  <rect x="0" y="${surfY.toFixed(1)}" width="${w}" height="${(h - surfY).toFixed(1)}" fill="url(#sand)"/>
  <!-- the surf: where the tide meets the sand, the shore's living edge -->
  <path d="${wavePath(w, surfY, h * 0.007, w * 0.24, hour * 1.3, h)}" fill="${css(lerpRGB(s.sea, [255, 255, 255], 0.35), 0.5)}"/>
  <path d="${wavePath(w, surfY + 4, h * 0.006, w * 0.24, hour * 1.3)}" fill="none" stroke="${css([255, 255, 255], 0.45)}" stroke-width="2.5"/>
</svg>`;
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

  // A stylized phase: lit disc carved by an elliptical terminator.
  function moonSVG(cx, cy, r, phase, s) {
    const lit = css([245, 243, 232]);
    const dark = css(lerpRGB(s.top, [70, 72, 96], 0.5));
    const k = 2 * phase.illum - 1; // -1 new .. 0 half .. 1 full
    const rx = Math.abs(k) * r;
    const top = `${cx.toFixed(1)} ${(cy - r).toFixed(1)}`;
    const bot = `${cx.toFixed(1)} ${(cy + r).toFixed(1)}`;
    // limb on the lit side (right if waxing), terminator ellipse back up
    const limbSweep = phase.waxing ? 1 : 0;
    const termSweep = (k >= 0) === phase.waxing ? 0 : 1;
    const litPath = `M ${top} A ${r} ${r} 0 0 ${limbSweep} ${bot} A ${rx} ${r} 0 0 ${termSweep} ${top} Z`;
    return `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${r}" fill="${dark}"/>
            <path d="${litPath}" fill="${lit}"/>`;
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
    return { date, tide: tideAt(date), phase: moonPhase(date), w, h };
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

  global.Shore = { render, renderStrip, skyAt, tideAt, moonPhase, bodyAt, resolveDate, labelTime };
})(typeof window !== "undefined" ? window : globalThis);
