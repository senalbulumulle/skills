// <mf-spotlight>: one light follows the pointer across a group of cards, lighting each card's border and
// surface where it passes (motion-forge). Each direct child becomes a lit card: it gets position: relative
// and uses its ::before and ::after. Keyboard focus lights the focused card. Mouse and pen only.

const TAG = "mf-spotlight";
const STYLE_ID = "mf-spotlight-style";
const Base = typeof HTMLElement === "undefined" ? class {} : HTMLElement;

const STYLE = `
:where(mf-spotlight) { display: block; }
:where(mf-spotlight) > * { position: relative; }
:where(mf-spotlight) > *::before, :where(mf-spotlight) > *::after {
  content: ""; position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
  opacity: var(--mf-spotlight-on, 0); transition: opacity .35s ease;
}
:where(mf-spotlight) > *::before {
  background: radial-gradient(calc(var(--mf-spotlight-size, 280px) * 1.6) circle at var(--mf-x, -999px) var(--mf-y, -999px),
    var(--mf-spotlight-fill, rgb(255 255 255 / .06)), transparent 70%);
}
:where(mf-spotlight) > *::after {
  padding: var(--mf-spotlight-border, 1px);
  background: radial-gradient(var(--mf-spotlight-size, 280px) circle at var(--mf-x, -999px) var(--mf-y, -999px),
    var(--mf-spotlight-color, rgb(255 255 255 / .55)), transparent 70%);
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  mask-composite: exclude;
}
@media (prefers-reduced-motion: reduce) { :where(mf-spotlight) > *::before, :where(mf-spotlight) > *::after { transition: none; } }
`;

// The light's position inside each card: pointer (px, py) minus each card's left and top.
export function spotlightPositions(px, py, rects) {
  return rects.map((r) => ({ x: px - r.left, y: py - r.top }));
}

function injectStyle() {
  if (typeof document === "undefined" || document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = STYLE;
  document.head.append(style);
}

export class Spotlight extends Base {
  constructor() {
    super();
    this._raf = 0;
    this._point = null;
  }

  connectedCallback() {
    injectStyle();
    this.addEventListener("pointerenter", this._onEnter);
    this.addEventListener("pointermove", this._onMove, { passive: true });
    this.addEventListener("pointerleave", this._onLeave);
    this.addEventListener("focusin", this._onFocus);
    this.addEventListener("focusout", this._onBlur);
  }

  disconnectedCallback() {
    cancelAnimationFrame(this._raf);
    this._raf = 0;
    this.removeEventListener("pointerenter", this._onEnter);
    this.removeEventListener("pointermove", this._onMove);
    this.removeEventListener("pointerleave", this._onLeave);
    this.removeEventListener("focusin", this._onFocus);
    this.removeEventListener("focusout", this._onBlur);
  }

  _onEnter = (e) => {
    if (e.pointerType === "touch") return;
    this.style.setProperty("--mf-spotlight-on", "1");
  };

  _onMove = (e) => {
    if (e.pointerType === "touch") return;
    this._point = [e.clientX, e.clientY];
    if (!this._raf) this._raf = requestAnimationFrame(this._update);
  };

  _onLeave = () => {
    this._point = null;
    if (!this.matches(":focus-within")) this.style.setProperty("--mf-spotlight-on", "0");
  };

  _onFocus = (e) => {
    const card = [...this.children].find((child) => child.contains(e.target));
    if (!card) return;
    for (const child of this.children) {
      if (child === card) {
        child.style.setProperty("--mf-x", "50%");
        child.style.setProperty("--mf-y", "50%");
      } else {
        child.style.removeProperty("--mf-x");
        child.style.removeProperty("--mf-y");
      }
    }
    this.style.setProperty("--mf-spotlight-on", "1");
  };

  _onBlur = (e) => {
    if (!this.contains(e.relatedTarget) && !this._point) this.style.setProperty("--mf-spotlight-on", "0");
  };

  _update = () => {
    this._raf = 0;
    if (!this._point) return;
    const cards = [...this.children];
    const positions = spotlightPositions(this._point[0], this._point[1], cards.map((c) => c.getBoundingClientRect()));
    cards.forEach((card, i) => {
      card.style.setProperty("--mf-x", `${positions[i].x.toFixed(1)}px`);
      card.style.setProperty("--mf-y", `${positions[i].y.toFixed(1)}px`);
    });
  };
}

if (typeof customElements !== "undefined" && !customElements.get(TAG)) customElements.define(TAG, Spotlight);
