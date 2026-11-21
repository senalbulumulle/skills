// <mf-tilt-card>: a card that tilts toward the pointer in 3D on a spring, with an optional glare (motion-forge).
// Elements inside with data-depth="24" rise toward the viewer by that many pixels while the card is active.
// Responds to mouse and pen only, lifts on keyboard focus, and stays flat under prefers-reduced-motion.

const TAG = "mf-tilt-card";
const Base = typeof HTMLElement === "undefined" ? class {} : HTMLElement;

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

// Pointer position inside a width x height box -> rotation in degrees and glare position in percent.
export function tiltAngles(x, y, width, height, max) {
  const nx = clamp((x / Math.max(1, width)) * 2 - 1, -1, 1);
  const ny = clamp((y / Math.max(1, height)) * 2 - 1, -1, 1);
  return { rx: -ny * max, ry: nx * max, gx: (nx + 1) * 50, gy: (ny + 1) * 50 };
}

// One semi-implicit Euler step of a damped spring; `s` is { x, v } and is updated in place.
export function springStep(s, target, dt, stiffness = 170, damping = 20) {
  s.v += (stiffness * (target - s.x) - damping * s.v) * dt;
  s.x += s.v * dt;
  return s;
}

const settled = (s, target) => Math.abs(target - s.x) < 0.001 && Math.abs(s.v) < 0.001;

const STYLE = `
:host { display: block; perspective: var(--mf-tilt-perspective, 900px); }
:host([hidden]) { display: none; }
.card { position: relative; height: 100%; border-radius: inherit; transform-style: preserve-3d; }
.glare {
  position: absolute; inset: 0; border-radius: inherit; pointer-events: none; opacity: var(--mf-glare, 0);
  background: radial-gradient(circle at var(--mf-gx, 50%) var(--mf-gy, 50%),
    rgb(255 255 255 / var(--mf-tilt-glare-strength, .3)), transparent 60%);
  transform: translateZ(1px);
}
:host(:not([glare])) .glare { display: none; }
`;

export class TiltCard extends Base {
  static observedAttributes = ["max", "scale", "glare"];

  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = `<style>${STYLE}</style><div class="card" part="card"><slot></slot><div class="glare" part="glare"></div></div>`;
    this._card = root.querySelector(".card");
    root.querySelector("slot").addEventListener("slotchange", () => this.refresh());
    this._rx = { x: 0, v: 0 };
    this._ry = { x: 0, v: 0 };
    this._lift = { x: 0, v: 0 };
    this._goal = { rx: 0, ry: 0, lift: 0 };
    this._raf = 0;
  }

  connectedCallback() {
    this._motion = matchMedia("(prefers-reduced-motion: reduce)");
    this._motion.addEventListener("change", this._onMotion);
    this.addEventListener("pointerenter", this._onEnter);
    this.addEventListener("pointermove", this._onMove, { passive: true });
    this.addEventListener("pointerleave", this._onLeave);
    this.addEventListener("focusin", this._onFocus);
    this.addEventListener("focusout", this._onBlur);
    this.refresh();
  }

  disconnectedCallback() {
    cancelAnimationFrame(this._raf);
    this._raf = 0;
    this._motion.removeEventListener("change", this._onMotion);
    this.removeEventListener("pointerenter", this._onEnter);
    this.removeEventListener("pointermove", this._onMove);
    this.removeEventListener("pointerleave", this._onLeave);
    this.removeEventListener("focusin", this._onFocus);
    this.removeEventListener("focusout", this._onBlur);
  }

  attributeChangedCallback() {
    if (this.isConnected) this._kick();
  }

  // Re-reads [data-depth] elements; call it after adding depth elements below the card's direct children.
  refresh() {
    for (const el of this.querySelectorAll("[data-depth]")) {
      const depth = parseFloat(el.dataset.depth) || 0;
      el.style.translate = `0 0 calc(${depth}px * var(--mf-lift, 0))`;
      for (let p = el.parentElement; p && p !== this; p = p.parentElement) p.style.transformStyle = "preserve-3d";
    }
  }

  _number(name, fallback, lo, hi) {
    const v = parseFloat(this.getAttribute(name));
    return Number.isFinite(v) ? clamp(v, lo, hi) : fallback;
  }

  _onMotion = () => {
    this._goal = { rx: 0, ry: 0, lift: 0 };
    if (!this._motion.matches) return this._kick();
    cancelAnimationFrame(this._raf);
    this._raf = 0;
    for (const s of [this._rx, this._ry, this._lift]) Object.assign(s, { x: 0, v: 0 });
    this._card.style.transform = "";
    this.style.removeProperty("--mf-lift");
    this.style.removeProperty("--mf-glare");
  };

  _onEnter = (e) => {
    if (e.pointerType === "touch" || this._motion.matches) return;
    this._rect = this.getBoundingClientRect();
    this._goal.lift = 1;
    this._kick();
  };

  _onMove = (e) => {
    if (e.pointerType === "touch" || this._motion.matches) return;
    const r = this._rect || (this._rect = this.getBoundingClientRect());
    const a = tiltAngles(e.clientX - r.left, e.clientY - r.top, r.width, r.height, this._number("max", 8, 0, 30));
    this._goal = { rx: a.rx, ry: a.ry, lift: 1 };
    this.style.setProperty("--mf-gx", `${a.gx.toFixed(1)}%`);
    this.style.setProperty("--mf-gy", `${a.gy.toFixed(1)}%`);
    this._kick();
  };

  _onLeave = () => {
    this._rect = null;
    this._goal = { rx: 0, ry: 0, lift: this.matches(":focus-within") ? 1 : 0 };
    this._kick();
  };

  _onFocus = () => {
    if (this._motion.matches) return;
    this._goal.lift = 1;
    this._kick();
  };

  _onBlur = (e) => {
    if (this.contains(e.relatedTarget)) return;
    if (!this._rect) this._goal = { rx: 0, ry: 0, lift: 0 };
    this._kick();
  };

  _kick() {
    if (!this._raf) {
      this._last = performance.now();
      this._raf = requestAnimationFrame(this._frame);
    }
  }

  _frame = (now) => {
    const dt = Math.min((now - this._last) / 1000, 1 / 30);
    this._last = now;
    const g = this._goal;
    springStep(this._rx, g.rx, dt);
    springStep(this._ry, g.ry, dt);
    springStep(this._lift, g.lift, dt, 120, 18);
    const lift = Math.max(0, this._lift.x);
    const scale = 1 + (this._number("scale", 1.03, 1, 1.2) - 1) * lift;
    const rest = settled(this._rx, g.rx) && settled(this._ry, g.ry) && settled(this._lift, g.lift);
    if (rest && g.lift === 0 && g.rx === 0 && g.ry === 0) {
      this._card.style.transform = "";
      this.style.removeProperty("--mf-lift");
      this.style.removeProperty("--mf-glare");
      this._raf = 0;
      return;
    }
    this._card.style.transform =
      `rotateX(${this._rx.x.toFixed(3)}deg) rotateY(${this._ry.x.toFixed(3)}deg) scale(${scale.toFixed(4)})`;
    this.style.setProperty("--mf-lift", lift.toFixed(4));
    this.style.setProperty("--mf-glare", lift.toFixed(4));
    this._raf = rest ? 0 : requestAnimationFrame(this._frame);
  };
}

if (typeof customElements !== "undefined" && !customElements.get(TAG)) customElements.define(TAG, TiltCard);
