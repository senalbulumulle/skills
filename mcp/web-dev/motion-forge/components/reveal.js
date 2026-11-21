// <mf-reveal>: reveals its direct children one after another as they scroll into view (motion-forge).
// effect: rise (default), fade, scale, blur, or clip. Hidden content stays in the accessibility tree,
// prints visible, and shows at once under prefers-reduced-motion. Add `repeat` to hide again on exit.

const TAG = "mf-reveal";
const STYLE_ID = "mf-reveal-style";
const MAX_STAGGERED = 12;
const Base = typeof HTMLElement === "undefined" ? class {} : HTMLElement;

const STYLE = `
:where(mf-reveal) { display: block; }
:where(mf-reveal) > * {
  transition-property: opacity, translate, scale, filter, clip-path;
  transition-duration: var(--mf-reveal-duration, 700ms);
  transition-timing-function: var(--mf-reveal-ease, cubic-bezier(.2, .7, .2, 1));
  transition-delay: var(--mf-delay, 0ms);
}
:where(mf-reveal[effect="clip"]) > * { clip-path: inset(0 0 0 0); }
:where(mf-reveal[data-state="hidden"]) > * { opacity: 0; }
:where(mf-reveal[data-state="hidden"]:not([effect]), mf-reveal[data-state="hidden"][effect="rise"]) > * { translate: 0 1.5rem; }
:where(mf-reveal[data-state="hidden"][effect="scale"]) > * { scale: .94; }
:where(mf-reveal[data-state="hidden"][effect="blur"]) > * { filter: blur(12px); translate: 0 .75rem; }
:where(mf-reveal[data-state="hidden"][effect="clip"]) > * { opacity: 1; clip-path: inset(0 0 100% 0); }
:where(mf-reveal[data-init]) > * { transition: none; }
@media (prefers-reduced-motion: reduce) { :where(mf-reveal) > * { transition: none; } }
@media print { :where(mf-reveal) > * { opacity: 1 !important; translate: none !important; scale: none !important; filter: none !important; clip-path: none !important; } }
`;

// Delay for the i-th child: `stagger` ms apart, with children past the twelfth sharing the last delay.
export function staggerDelay(index, stagger, cap = MAX_STAGGERED) {
  return Math.min(Math.max(0, index), cap) * Math.max(0, stagger);
}

function injectStyle() {
  if (typeof document === "undefined" || document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = STYLE;
  document.head.append(style);
}

export class Reveal extends Base {
  static observedAttributes = ["stagger", "duration"];

  connectedCallback() {
    injectStyle();
    this._motion = matchMedia("(prefers-reduced-motion: reduce)");
    this._motion.addEventListener("change", this._onMotion);
    this._mo = new MutationObserver(() => this._index());
    this._mo.observe(this, { childList: true });
    this._index();
    this._ready = false;
    this._pending = false;
    if (this._motion.matches) {
      this.dataset.state = "shown";
    } else {
      this.toggleAttribute("data-init", true);
      this.dataset.state = "hidden";
      this._raf = requestAnimationFrame(() => {
        this._raf = requestAnimationFrame(() => {
          this._raf = 0;
          this.removeAttribute("data-init");
          this._ready = true;
          if (this._pending) this._show();
        });
      });
    }
    this._io = new IntersectionObserver(this._onIntersect, { threshold: 0.15, rootMargin: "0px 0px -8% 0px" });
    this._io.observe(this);
  }

  disconnectedCallback() {
    cancelAnimationFrame(this._raf);
    this._raf = 0;
    this._motion.removeEventListener("change", this._onMotion);
    this._mo.disconnect();
    this._io.disconnect();
  }

  attributeChangedCallback() {
    if (this.isConnected) this._index();
  }

  _index() {
    const stagger = parseFloat(this.getAttribute("stagger"));
    const step = Number.isFinite(stagger) ? stagger : 80;
    const duration = parseFloat(this.getAttribute("duration"));
    if (Number.isFinite(duration) && duration >= 0) this.style.setProperty("--mf-reveal-duration", `${duration}ms`);
    else this.style.removeProperty("--mf-reveal-duration");
    [...this.children].forEach((child, i) => child.style.setProperty("--mf-delay", `${staggerDelay(i, step)}ms`));
  }

  _onIntersect = ([entry]) => {
    if (entry.isIntersecting) {
      if (this._ready || this._motion.matches) this._show();
      else this._pending = true;
    } else if (this.hasAttribute("repeat") && !this._motion.matches && entry.boundingClientRect.top > 0) {
      this._pending = false;
      this.dataset.state = "hidden";
    }
  };

  _show() {
    this._pending = false;
    this.dataset.state = "shown";
    if (!this.hasAttribute("repeat")) this._io.disconnect();
  }

  _onMotion = () => {
    if (this._motion.matches) {
      this.dataset.state = "shown";
      this.removeAttribute("data-init");
    }
  };
}

if (typeof customElements !== "undefined" && !customElements.get(TAG)) customElements.define(TAG, Reveal);
