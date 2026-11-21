// sfx.js: tiny Web Audio sound-effect synth with presets, voice limits, pitch variation, and buses.
// Exposes a global `Sfx` in browsers and module.exports in Node (for tests with a mock AudioContext).
//
//   const sfx = Sfx.create();
//   addEventListener("pointerdown", () => sfx.unlock());   // browsers block audio until a user gesture
//   addEventListener("keydown", () => sfx.unlock());
//   sfx.play("jump");                                     // optional: { pitch: 1.2, volume: 0.5, vary: 0 }
//   sfx.setVolume("sfx", 0.7); sfx.setMuted(true);
(function (root) {
  "use strict";

  // Preset fields: wave (sine|square|triangle|sawtooth|noise), freq [start, end] Hz, dur s, attack s,
  // volume 0-1, slide "exp" | "linear" | "step" (jump to end freq at stepAt × dur),
  // filter { type, freq: [start, end] }, vibrato { rate Hz, depth fraction }, maxVoices.
  const PRESETS = {
    jump:      { wave: "square",   freq: [220, 660],   dur: 0.18, attack: 0.005, volume: 0.25 },
    coin:      { wave: "square",   freq: [988, 1319],  dur: 0.25, attack: 0.003, volume: 0.2, slide: "step", stepAt: 0.25 },
    hit:       { wave: "noise",    freq: [1, 1],       dur: 0.15, attack: 0.002, volume: 0.45, filter: { type: "lowpass", freq: [3000, 300] } },
    explosion: { wave: "noise",    freq: [1, 1],       dur: 0.6,  attack: 0.005, volume: 0.55, filter: { type: "lowpass", freq: [1200, 80] }, maxVoices: 3 },
    laser:     { wave: "sawtooth", freq: [1200, 200],  dur: 0.15, attack: 0.002, volume: 0.15 },
    powerup:   { wave: "triangle", freq: [300, 1200],  dur: 0.4,  attack: 0.01,  volume: 0.3, vibrato: { rate: 12, depth: 0.04 } },
    hurt:      { wave: "sawtooth", freq: [400, 120],   dur: 0.25, attack: 0.003, volume: 0.25, filter: { type: "lowpass", freq: [2000, 600] } },
    click:     { wave: "sine",     freq: [1000, 800],  dur: 0.04, attack: 0.001, volume: 0.2 },
    select:    { wave: "square",   freq: [660, 660],   dur: 0.06, attack: 0.002, volume: 0.15, slide: "linear" },
  };

  const MIN = 0.0001; // exponential ramps can't reach 0

  function create({ presets = {}, rng = Math.random, AudioContextClass } = {}) {
    const all = { ...PRESETS, ...presets };
    const voices = {};
    const volumes = { master: 0.8, sfx: 1, music: 0.6 };
    let ctx = null, nodes = null, noiseBuffer = null, muted = false;

    function build() {
      const Ctx = AudioContextClass || root.AudioContext || root.webkitAudioContext;
      if (!Ctx) return false;
      ctx = new Ctx();
      const compressor = ctx.createDynamicsCompressor(); // keeps stacked sounds from clipping
      const master = ctx.createGain(), sfx = ctx.createGain(), music = ctx.createGain();
      sfx.connect(master); music.connect(master); master.connect(compressor); compressor.connect(ctx.destination);
      nodes = { master, sfx, music };
      applyVolumes();
      noiseBuffer = ctx.createBuffer(1, Math.floor(ctx.sampleRate), ctx.sampleRate);
      const data = noiseBuffer.getChannelData(0);
      for (let i = 0; i < data.length; i++) data[i] = rng() * 2 - 1;
      return true;
    }

    function applyVolumes() {
      if (!nodes) return;
      const t = ctx.currentTime;
      nodes.master.gain.setValueAtTime(muted ? 0 : volumes.master, t);
      nodes.sfx.gain.setValueAtTime(volumes.sfx, t);
      nodes.music.gain.setValueAtTime(volumes.music, t);
    }

    const api = {
      presets: all,
      get context() { return ctx; },
      get musicBus() { return nodes && nodes.music; }, // connect music sources here
      // Call from a user gesture handler (pointerdown, keydown, touchend).
      unlock() {
        if (!ctx && !build()) return false;
        if (ctx.state === "suspended") ctx.resume();
        return true;
      },
      setVolume(bus, value) {
        if (!(bus in volumes)) throw new Error(`unknown bus: ${bus}`);
        volumes[bus] = Math.max(0, Math.min(1, value));
        applyVolumes();
      },
      setMuted(value) { muted = !!value; applyVolumes(); },
      get muted() { return muted; },
      // Returns true if the sound started; false if audio is locked, unavailable, or the voice limit is hit.
      play(name, { pitch = 1, volume = 1, vary = 0.06 } = {}) {
        const p = all[name];
        if (!p) throw new Error(`unknown sound: ${name}`);
        if (!ctx || ctx.state !== "running" || muted) return false;
        if ((voices[name] || 0) >= (p.maxVoices || 4)) return false;

        const t = ctx.currentTime;
        const dur = Math.max(p.dur, 0.01);
        const attack = Math.min(p.attack || 0.005, dur / 2);
        const k = pitch * (1 + (rng() * 2 - 1) * vary);
        const peak = Math.max(MIN * 2, (p.volume || 0.3) * volume);

        const env = ctx.createGain();
        env.gain.setValueAtTime(MIN, t);
        env.gain.exponentialRampToValueAtTime(peak, t + attack);
        env.gain.exponentialRampToValueAtTime(MIN, t + dur);

        let source;
        if (p.wave === "noise") {
          source = ctx.createBufferSource();
          source.buffer = noiseBuffer;
          source.loop = true;
          source.playbackRate.setValueAtTime(k, t);
        } else {
          source = ctx.createOscillator();
          source.type = p.wave;
          const f0 = p.freq[0] * k, f1 = p.freq[1] * k;
          source.frequency.setValueAtTime(f0, t);
          if (p.slide === "step") source.frequency.setValueAtTime(f1, t + dur * (p.stepAt || 0.5));
          else if (p.slide === "linear") source.frequency.linearRampToValueAtTime(f1, t + dur);
          else source.frequency.exponentialRampToValueAtTime(Math.max(f1, 1), t + dur);
          if (p.vibrato) {
            const lfo = ctx.createOscillator(), depth = ctx.createGain();
            lfo.frequency.setValueAtTime(p.vibrato.rate, t);
            depth.gain.setValueAtTime(f0 * p.vibrato.depth, t);
            lfo.connect(depth); depth.connect(source.frequency);
            lfo.start(t); lfo.stop(t + dur + 0.05);
          }
        }

        let tail = source;
        if (p.filter) {
          const filter = ctx.createBiquadFilter();
          filter.type = p.filter.type;
          filter.frequency.setValueAtTime(p.filter.freq[0], t);
          filter.frequency.exponentialRampToValueAtTime(Math.max(p.filter.freq[1], 1), t + dur);
          source.connect(filter);
          tail = filter;
        }
        tail.connect(env);
        env.connect(nodes.sfx);

        voices[name] = (voices[name] || 0) + 1;
        source.onended = () => {
          voices[name] -= 1;
          env.disconnect();
        };
        source.start(t);
        source.stop(t + dur + 0.05);
        return true;
      },
    };
    return api;
  }

  const Sfx = { create, PRESETS };
  if (typeof module !== "undefined" && module.exports) module.exports = Sfx;
  else root.Sfx = Sfx;
})(typeof globalThis !== "undefined" ? globalThis : this);
