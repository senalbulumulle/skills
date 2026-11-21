// juice.js: small, dependency-free game-feel helpers. Paste into a game or load with a script tag.
// Exposes a global `Juice` in browsers and module.exports in Node (for tests).
// Every helper is driven by update(dt) in seconds, so it works with a fixed-timestep loop.
(function (root) {
  "use strict";

  // ---- Easing: t in [0, 1] → [0, 1] (back/elastic overshoot on purpose) ----
  const ease = {
    linear: (t) => t,
    inQuad: (t) => t * t,
    outQuad: (t) => 1 - (1 - t) * (1 - t),
    inOutQuad: (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2),
    outCubic: (t) => 1 - Math.pow(1 - t, 3),
    inOutCubic: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
    outBack: (t) => {
      const c1 = 1.70158, c3 = c1 + 1;
      return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
    },
    outElastic: (t) => {
      if (t === 0 || t === 1) return t;
      return Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * ((2 * Math.PI) / 3)) + 1;
    },
  };

  const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);
  const lerp = (a, b, t) => a + (b - a) * t;

  // Frame-rate independent smoothing toward a target. rate: fraction remaining after 1 s (e.g. 0.001 = snappy).
  function damp(current, target, rate, dt) {
    return lerp(target, current, Math.pow(rate, dt));
  }

  // ---- Tweens: animate numeric properties of any object ----
  class Tweens {
    constructor() { this.list = []; }
    to(target, props, duration, easing = ease.outCubic, onDone = null) {
      const from = {};
      for (const k in props) from[k] = target[k];
      const tw = { target, from, props, duration: Math.max(duration, 1e-6), t: 0, easing, onDone };
      this.list.push(tw);
      return tw;
    }
    cancel(target) { this.list = this.list.filter((tw) => tw.target !== target); }
    update(dt) {
      for (let i = this.list.length - 1; i >= 0; i--) {
        const tw = this.list[i];
        tw.t = Math.min(tw.t + dt, tw.duration);
        const k = tw.easing(tw.t / tw.duration);
        for (const p in tw.props) tw.target[p] = lerp(tw.from[p], tw.props[p], k);
        if (tw.t >= tw.duration) {
          this.list.splice(i, 1);
          if (tw.onDone) tw.onDone(tw.target);
        }
      }
    }
  }

  // ---- Trauma-based screen shake: add trauma on events; offset scales with trauma squared ----
  class Shake {
    constructor({ maxOffset = 12, maxAngle = 0.05, decay = 1.6, frequency = 25, rng = Math.random } = {}) {
      Object.assign(this, { maxOffset, maxAngle, decay, frequency, rng });
      this.trauma = 0; this.time = 0; this.x = 0; this.y = 0; this.angle = 0;
      this.enabled = true;
      this.seeds = [rng() * 1000, rng() * 1000, rng() * 1000];
    }
    add(amount) { this.trauma = clamp01(this.trauma + amount); }
    update(dt) {
      this.time += dt;
      this.trauma = Math.max(0, this.trauma - this.decay * dt);
      const s = this.enabled ? this.trauma * this.trauma : 0;
      const f = this.time * this.frequency;
      // Sum of sines: smooth, non-repeating-looking motion without a noise library.
      const wave = (seed) => (Math.sin(f + seed) + Math.sin(f * 1.7 + seed * 2.3)) / 2;
      this.x = this.maxOffset * s * wave(this.seeds[0]);
      this.y = this.maxOffset * s * wave(this.seeds[1]);
      this.angle = this.maxAngle * s * wave(this.seeds[2]);
    }
    // Call around world drawing (not UI): ctx.save(); shake.apply(ctx, cx, cy); ...; ctx.restore();
    apply(ctx, cx = 0, cy = 0) {
      ctx.translate(cx + this.x, cy + this.y);
      ctx.rotate(this.angle);
      ctx.translate(-cx, -cy);
    }
  }

  // ---- Hit stop: freeze gameplay briefly on impact. Scale gameplay dt by hitstop.scale(dt) ----
  class HitStop {
    constructor() { this.remaining = 0; }
    trigger(seconds) { this.remaining = Math.max(this.remaining, seconds); }
    get active() { return this.remaining > 0; }
    // Returns the dt gameplay should use this step (0 while frozen). Keep UI and juice on the real dt.
    scale(dt) {
      if (this.remaining <= 0) return dt;
      this.remaining -= dt;
      return this.remaining < 0 ? -this.remaining : 0;
    }
  }

  // ---- Flash: brief white/colored overlay on an entity, 0..1 intensity ----
  class Flash {
    constructor(duration = 0.08) { this.duration = duration; this.t = 0; }
    trigger(duration = this.duration) { this.duration = duration; this.t = duration; }
    update(dt) { this.t = Math.max(0, this.t - dt); }
    get value() { return this.duration > 0 ? this.t / this.duration : 0; }
  }

  // ---- Squash and stretch, volume preserving: scaleX * scaleY stays 1 ----
  class Squash {
    constructor({ stiffness = 300, damping = 18 } = {}) {
      Object.assign(this, { stiffness, damping });
      this.amount = 0; this.velocity = 0;
    }
    // amount > 0 stretches vertically (jump), < 0 squashes (land). Try ±0.25.
    kick(amount) { this.amount = amount; this.velocity = 0; }
    update(dt) {
      // Damped spring back to 0, sub-stepped so large dt stays stable.
      const steps = Math.max(1, Math.ceil(dt / (1 / 240)));
      const h = dt / steps;
      for (let i = 0; i < steps; i++) {
        const accel = -this.stiffness * this.amount - this.damping * this.velocity;
        this.velocity += accel * h;
        this.amount += this.velocity * h;
      }
    }
    get scaleY() { return 1 + this.amount; }
    get scaleX() { return 1 / Math.max(0.05, 1 + this.amount); }
  }

  // ---- Particles: pooled, so bursts don't allocate after warm-up ----
  class Particles {
    constructor(max = 512, rng = Math.random) {
      this.rng = rng;
      this.pool = Array.from({ length: max }, () => ({ alive: false }));
    }
    burst(x, y, { count = 12, speed = [60, 180], life = [0.25, 0.6], size = [2, 5], color = "#fff",
                  gravity = 0, drag = 2, spread = Math.PI * 2, angle = 0 } = {}) {
      const r = (range) => range[0] + (range[1] - range[0]) * this.rng();
      let spawned = 0;
      for (const p of this.pool) {
        if (spawned >= count) break;
        if (p.alive) continue;
        const a = angle + (this.rng() - 0.5) * spread;
        const s = r(speed);
        Object.assign(p, { alive: true, x, y, vx: Math.cos(a) * s, vy: Math.sin(a) * s,
                           life: r(life), size: r(size), color, gravity, drag });
        p.maxLife = p.life;
        spawned++;
      }
      return spawned;
    }
    update(dt) {
      for (const p of this.pool) {
        if (!p.alive) continue;
        p.life -= dt;
        if (p.life <= 0) { p.alive = false; continue; }
        const k = Math.exp(-p.drag * dt);
        p.vx *= k; p.vy = p.vy * k + p.gravity * dt;
        p.x += p.vx * dt; p.y += p.vy * dt;
      }
    }
    draw(ctx) {
      for (const p of this.pool) {
        if (!p.alive) continue;
        const t = p.life / p.maxLife;
        ctx.globalAlpha = t;
        ctx.fillStyle = p.color;
        const s = p.size * (0.5 + 0.5 * t);
        ctx.fillRect(p.x - s / 2, p.y - s / 2, s, s);
      }
      ctx.globalAlpha = 1;
    }
    get count() { return this.pool.reduce((n, p) => n + (p.alive ? 1 : 0), 0); }
  }

  // ---- Floating text ("+10", "CRIT!") that rises and fades ----
  class Popups {
    constructor() { this.list = []; }
    add(text, x, y, { color = "#fff", size = 14, life = 0.7, rise = 40 } = {}) {
      this.list.push({ text, x, y, color, size, life, maxLife: life, rise });
    }
    update(dt) {
      for (let i = this.list.length - 1; i >= 0; i--) {
        const p = this.list[i];
        p.life -= dt;
        p.y -= p.rise * dt;
        if (p.life <= 0) this.list.splice(i, 1);
      }
    }
    draw(ctx) {
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      for (const p of this.list) {
        const t = p.life / p.maxLife;
        const pop = 1 + 0.4 * Math.max(0, (t - 0.8) / 0.2); // quick scale-in during the first 20%
        ctx.globalAlpha = Math.min(1, t * 2);
        ctx.fillStyle = p.color;
        ctx.font = `bold ${Math.round(p.size * pop)}px monospace`;
        ctx.fillText(p.text, p.x, p.y);
      }
      ctx.globalAlpha = 1;
    }
  }

  // ---- Input forgiveness timers for platformers ----
  // Coyote time: allow a jump shortly after leaving a ledge. Jump buffer: remember an early press.
  class JumpAssist {
    constructor({ coyote = 0.1, buffer = 0.12 } = {}) {
      Object.assign(this, { coyote, buffer });
      this.sinceGrounded = Infinity; this.sincePressed = Infinity;
    }
    // Call every step with grounded state and whether jump was pressed this step.
    update(dt, grounded, jumpPressed) {
      this.sinceGrounded = grounded ? 0 : this.sinceGrounded + dt;
      this.sincePressed = jumpPressed ? 0 : this.sincePressed + dt;
    }
    // True when a jump should start now. Consumes both timers so it fires once.
    shouldJump() {
      if (this.sincePressed <= this.buffer && this.sinceGrounded <= this.coyote) {
        this.sincePressed = this.sinceGrounded = Infinity;
        return true;
      }
      return false;
    }
  }

  const Juice = { ease, lerp, damp, clamp01, Tweens, Shake, HitStop, Flash, Squash, Particles, Popups, JumpAssist };
  if (typeof module !== "undefined" && module.exports) module.exports = Juice;
  else root.Juice = Juice;
})(typeof globalThis !== "undefined" ? globalThis : this);
