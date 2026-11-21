// <mf-magnetic>: pulls its content toward a nearby pointer on a spring and presses in when clicked
// (motion-forge). Wrap one button or link. Works with mouse and pen on hover-capable devices; under
// prefers-reduced-motion it keeps only the press.

const TAG = "mf-magnetic";
const STYLE_ID = "mf-magnetic-style";
const Base = typeof HTMLElement === "undefined" ? class {} : HTMLElement;

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

const STYLE = `
:where(mf-magnetic) { display: inline-block; transition: scale .22s cubic-bezier(.3, .7, .4, 1.5); }
:where(mf-magnetic):active { scale: .96; }
@media (prefers-reduced-motion: reduce) { :where(mf-magnetic) { transition: none; } }
`;

// Where the content should sit for a pointer at (px, py), given the element's untranslated box. Returns
// zero offset when the pointer is more than `radius` pixels outside the box.
export function magnetTarget(px, py, left, top, width, height, radius, strength) {
  const dx = Math.max(left - px, 0, px - (left + width));
  const dy = Math.max(top - py, 0, py - (top + height));
  if (Math.hypot(dx, dy) > radius) return { x: 0, y: 0, active: false };
  return { x: (px - (left + width / 2)) * strength, y: (py - (top + height / 2)) * strength, active: true };
}

// One semi-implicit Euler step of a damped spring; `s` is { x, v } and is updated in place.
export function springStep(s, target, dt, stiffness = 220, damping = 18) {
  s.v += (stiffness * (target - s.x) - damping * s.v) * dt;
  s.x += s.v * dt;
  return s;
}

function injectStyle() {
  if (typeof document === "undefined" || document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = STYLE;
  document.head.append(style);
}

export class Magnetic extends Base {
  constructor() {
    super();
    this._x = { x: 0, v: 0 };
    this._y = { x: 0, v: 0 };
    this._goal = { x: 0, y: 0 };
    this._raf = 0;
  }

  connectedCallback() {
    injectStyle();
    this._motion = matchMedia("(prefers-reduced-motion: reduce)");
    this._fine = matchMedia("(hover: hover) and (pointer: fine)");
    this._motion.addEventListener("change", this._sync);
    this._fine.addEventListener("change", this._sync);
    this._io = new IntersectionObserver(([entry]) => { this._visible = entry.isIntersecting; this._sync(); });
    this._io.observe(this);
  }

  disconnectedCallback() {
    this._listen(false);
    cancelAnimationFrame(this._raf);
    this._raf = 0;
    this._motion.removeEventListener("change", this._sync);
    this._fine.removeEventListener("change", this._sync);
    this._io.disconnect();
  }

  _number(name, fallback, lo, hi) {
    const v = parseFloat(this.getAttribute(name));
    return Number.isFinite(v) ? clamp(v, lo, hi) : fallback;
  }

  _sync = () => {
    const on = Boolean(this._visible) && this._fine.matches && !this._motion.matches;
    this._listen(on);
    if (!on) this._release();
  };

  _listen(on) {
    if (on === this._listening) return;
    this._listening = on;
    const method = on ? "addEventListener" : "removeEventListener";
    window[method]("pointermove", this._onMove, { passive: true });
    document.documentElement[method]("pointerleave", this._release);
    window[method]("blur", this._release);
  }

  _onMove = (e) => {
    if (e.pointerType === "touch") return;
    const r = this.getBoundingClientRect();
    const t = magnetTarget(e.clientX, e.clientY, r.left - this._x.x, r.top - this._y.x, r.width, r.height,
      this._number("radius", 60, 0, 400), this._number("strength", 0.35, 0, 1));
    this._goal = { x: t.x, y: t.y };
    this._kick();
  };

  _release = () => {
    this._goal = { x: 0, y: 0 };
    if (this._motion?.matches) {
      cancelAnimationFrame(this._raf);
      this._raf = 0;
      Object.assign(this._x, { x: 0, v: 0 });
      Object.assign(this._y, { x: 0, v: 0 });
      this.style.translate = "";
      return;
    }
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
    springStep(this._x, this._goal.x, dt);
    springStep(this._y, this._goal.y, dt);
    const rest = [[this._x, this._goal.x], [this._y, this._goal.y]]
      .every(([s, g]) => Math.abs(g - s.x) < 0.01 && Math.abs(s.v) < 0.01);
    if (rest) {
      this._x.x = this._goal.x;
      this._y.x = this._goal.y;
      this._x.v = this._y.v = 0;
    }
    this.style.translate = this._x.x || this._y.x ? `${this._x.x.toFixed(2)}px ${this._y.x.toFixed(2)}px` : "";
    this._raf = rest ? 0 : requestAnimationFrame(this._frame);
  };
}

if (typeof customElements !== "undefined" && !customElements.get(TAG)) customElements.define(TAG, Magnetic);
