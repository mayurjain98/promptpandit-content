/* Shared Reel engine.
   render_reel.py calls:
     window.setup(spec, timeline)   once
     window.seek(t)                 once per frame (t in seconds)
   Every animation is a pure function of t (no CSS transitions or timers),
   so each frame is deterministic.

   A style page defines window.STYLE = { build(spec, tl, stage), update(t, spec, tl) }. */

const PP = (() => {
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const easeOut = x => 1 - Math.pow(1 - clamp(x), 3);
  const easeInOut = x => { x = clamp(x); return x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; };
  const prog = (t, start, dur) => clamp((t - start) / dur);
  const lerp = (a, b, k) => a + (b - a) * k;

  // Escape HTML; *word* -> glossy lime; [x] -> placeholder; \n -> line break.
  function fmt(s) {
    if (!s) return "";
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/\*(.+?)\*/g, '<span class="lime">$1</span>')
      .replace(/\[(.+?)\]/g, '<span class="ph">[$1]</span>')
      .replace(/\n/g, "<br>");
  }

  // ---- captions -------------------------------------------------------
  // Piper gives no word timings, so we spread words across the voice clip
  // in proportion to their length. Close enough for short lines.
  let CAP = [];
  function buildCaptions(spec, tl) {
    CAP = spec.scenes.map((sc, i) => {
      const words = (sc.caption || sc.voice).replace(/[*\[\]]/g, "").split(/\s+/).filter(Boolean);
      const { start, voice } = tl.scenes[i];
      const total = words.reduce((n, w) => n + w.length + 1, 0);
      let t = start;
      const timed = words.map(w => { const d = voice * 0.96 * (w.length + 1) / total; const o = { w, t0: t }; t += d; return o; });
      // Chunks of up to 4 words / ~20 chars so captions stay on 1-2 lines.
      const chunks = []; let cur = [];
      timed.forEach(o => {
        const len = cur.reduce((n, x) => n + x.w.length + 1, 0);
        if (cur.length && (cur.length >= 4 || len + o.w.length > 20)) { chunks.push(cur); cur = []; }
        cur.push(o);
      });
      if (cur.length) chunks.push(cur);
      // Don't leave a lonely last word on screen: merge it into the previous chunk.
      if (chunks.length > 1 && chunks[chunks.length - 1].length === 1) chunks[chunks.length - 2].push(chunks.pop()[0]);
      return chunks;
    });
  }
  function updateCaptions(t, tl, el) {
    const i = tl.scenes.findIndex(s => t >= s.start && t < s.end);
    if (i < 0 || t > tl.scenes[i].start + tl.scenes[i].voice + 0.25) { el.innerHTML = ""; return; }
    const chunks = CAP[i];
    let c = chunks.findIndex((ch, k) => t >= ch[0].t0 && (k === chunks.length - 1 || t < chunks[k + 1][0].t0));
    if (c < 0) c = 0;
    el.innerHTML = chunks[c].map((o, k) => {
      const next = chunks[c][k + 1];
      const on = t >= o.t0 && (!next || t < next.t0);
      return `<span class="${on ? "on" : ""}">${fmt(o.w)}</span>`;
    }).join(" ");
  }

  // ---- scaffold ----------------------------------------------------------
  let els = {};
  function setup(spec, tl) {
    const root = document.getElementById("reel");
    root.innerHTML = `
      <div class="spot"></div>
      <div class="progress"><i></i></div>
      <div class="stage"></div>
      <div class="captions"></div>
      <div class="outro">
        <img src="../brand/promptpandit_final_wordmark_black.png">
        <span class="pill">Follow @promptpandit.in</span>
        <p>Roz naye AI prompts &amp; tools</p>
      </div>
      <img class="watermark" src="../brand/watermark_trimmed.png">`;
    els = {
      spot: root.querySelector(".spot"), bar: root.querySelector(".progress i"),
      stage: root.querySelector(".stage"), caps: root.querySelector(".captions"),
      outro: root.querySelector(".outro"),
    };
    buildCaptions(spec, tl);
    const styleReady = window.STYLE.build(spec, tl, els.stage);  // may return a Promise (e.g. image load)
    window.__spec = spec; window.__tl = tl;
    return Promise.all([document.fonts.ready, styleReady]);
  }

  function seek(t) {
    const tl = window.__tl;
    els.spot.style.transform = `translate(${Math.sin(t * 0.35) * 60}px, ${Math.cos(t * 0.27) * 80}px)`;
    els.bar.style.width = `${clamp(t / tl.outroStart) * 100}%`;
    window.STYLE.update(t, window.__spec, tl);
    updateCaptions(t, tl, els.caps);
    // Outro fades in, and lifts slightly.
    const k = easeOut(prog(t, tl.outroStart, 0.5));
    els.outro.style.opacity = k;
    els.outro.style.transform = `translateY(${(1 - k) * 40}px)`;
  }

  return { setup, seek, clamp, easeOut, easeInOut, prog, lerp, fmt };
})();

window.setup = PP.setup;
window.seek = PP.seek;
