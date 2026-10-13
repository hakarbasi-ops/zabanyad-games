// Sound effects made in the browser with Web Audio (no files to download, works offline).
// ZG.sfx.<name>() is safe to call any time: silent when muted or before the first tap unlocks audio.
(function () {
  const { store } = window.ZG;
  let ctx = null;
  let muted = store.get("zg:muted") === true;
  let noiseBuf = null;

  function audio() {
    if (muted) return null;
    if (!ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      ctx = new AC();
    }
    if (ctx.state === "suspended") ctx.resume();
    return ctx;
  }
  // browsers only allow sound after a tap: unlock on the first one
  ["pointerdown", "keydown", "touchstart"].forEach((ev) =>
    window.addEventListener(ev, () => audio(), { once: true, passive: true }));

  function tone(freq, start, dur, { type = "sine", gain = 0.2, to = null, attack = 0.005 } = {}) {
    const a = audio();
    if (!a) return;
    const t = a.currentTime + start;
    const o = a.createOscillator();
    const g = a.createGain();
    o.type = type;
    o.frequency.setValueAtTime(freq, t);
    if (to) o.frequency.exponentialRampToValueAtTime(to, t + dur);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain, t + attack);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(a.destination);
    o.start(t);
    o.stop(t + dur + 0.02);
  }

  function noise(start, dur, { gain = 0.15, freq = 1800, q = 0.8, type = "bandpass" } = {}) {
    const a = audio();
    if (!a) return null;
    if (!noiseBuf) {
      noiseBuf = a.createBuffer(1, a.sampleRate, a.sampleRate);
      const d = noiseBuf.getChannelData(0);
      for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    }
    const t = a.currentTime + start;
    const src = a.createBufferSource();
    src.buffer = noiseBuf;
    src.loop = true;
    const f = a.createBiquadFilter();
    f.type = type;
    f.frequency.value = freq;
    f.Q.value = q;
    const g = a.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    src.connect(f).connect(g).connect(a.destination);
    src.start(t);
    src.stop(t + dur + 0.05);
    return src;
  }

  const notes = (list, step, opts) => list.forEach((f, i) => tone(f, i * step, opts.dur || step * 1.6, opts));

  const sfx = {
    tap() { tone(660, 0, 0.06, { type: "triangle", gain: 0.12 }); },
    tick() { tone(1400, 0, 0.03, { type: "square", gain: 0.05 }); },
    spin() { noise(0, 0.6, { gain: 0.08, freq: 700, q: 0.6 }); tone(220, 0, 0.5, { type: "sawtooth", gain: 0.04, to: 520 }); },
    scratch() { noise(0, 0.09, { gain: 0.06, freq: 3200, q: 1.5 }); },
    flip() { tone(500, 0, 0.12, { type: "triangle", gain: 0.12, to: 900 }); },
    open() { noise(0, 0.25, { gain: 0.1, freq: 900 }); notes([523, 784, 1047], 0.07, { type: "triangle", gain: 0.14 }); },
    reel() { tone(320, 0, 0.05, { type: "square", gain: 0.04 }); },
    stop() { tone(180, 0, 0.12, { type: "square", gain: 0.1 }); noise(0, 0.08, { gain: 0.06, freq: 500 }); },
    lever() { tone(140, 0, 0.25, { type: "sawtooth", gain: 0.08, to: 60 }); },
    key() { tone(900, 0, 0.04, { type: "triangle", gain: 0.06 }); },
    good() { notes([660, 880], 0.08, { type: "triangle", gain: 0.12 }); },
    bad() { tone(200, 0, 0.18, { type: "square", gain: 0.06, to: 150 }); },
    countdown() { tone(1000, 0, 0.05, { type: "sine", gain: 0.08 }); },
    // winning: bright arpeggio + sparkle; big wins (40%+) get a longer fanfare
    win(big) {
      const base = [523, 659, 784, 1047];
      notes(base, 0.09, { type: "triangle", gain: 0.16, dur: 0.3 });
      notes([1319, 1568, 2093], 0.06, { type: "sine", gain: 0.06, dur: 0.25 });
      if (big) {
        setTimeout(() => notes([784, 988, 1175, 1568, 2093], 0.1, { type: "square", gain: 0.06, dur: 0.35 }), 420);
        setTimeout(() => { tone(1047, 0, 0.9, { type: "triangle", gain: 0.12 }); tone(1319, 0, 0.9, { type: "triangle", gain: 0.08 }); tone(1568, 0, 0.9, { type: "triangle", gain: 0.06 }); }, 950);
      }
    },
    meh() { notes([523, 494, 440], 0.12, { type: "triangle", gain: 0.1 }); },
    isMuted: () => muted,
    setMuted(v) {
      muted = v;
      store.set("zg:muted", v);
      if (!v) sfx.tap();
    },
  };

  window.ZG.sfx = sfx;
})();
