// <mf-parallax>: scroll parallax for layered scenes (motion-forge). Give any element inside data-speed:
// 1 scrolls normally, 0.5 at half speed (far away), 0 stays put, 1.3 faster (close up). data-speed-x adds
// sideways drift in pixels per scrolled pixel. Layers rest where you laid them out when the section is
// centered in the viewport. Listens to scroll only near the viewport; still under prefers-reduced-motion.

const TAG = "mf-parallax";
const STYLE_ID = "mf-parallax-style";
const Base = typeof HTMLElement === "undefined" ? class {} : HTMLElement;

const STYLE = `
:where(mf-parallax) { display: block; position: relative; overflow: hidden; overflow: clip; }
:where(mf-parallax [data-speed], mf-parallax [data-speed-x]) { will-change: translate; }
`;

// Offset in pixels for a layer, given the section's position: rectTop and rectHeight from
// getBoundingClientRect(), the viewport height, and the layer's speed and sideways drift.
export function parallaxOffset(rectTop, rectHeight, viewportHeight, speed = 1, drift = 0) {
  const fromCenter = rectTop + rectHeight / 2 - viewportHeight / 2;
  return { x: -fromCenter * drift, y: fromCenter * (speed - 1) };
}

function injectStyle() {
  if (typeof document === "undefined" || document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = STYLE;
  document.head.append(style);
}

export class Parallax extends Base {
  constructor() {
    super();
    this._raf = 0;
    this._layers = [];
  }

  connectedCallback() {
    injectStyle();
    this._motion = matchMedia("(prefers-reduced-motion: reduce)");
    this._motion.addEventListener("change", this._onMotion);
    this._mo = new MutationObserver(() => this._collect());
    this._mo.observe(this, { subtree: true, childList: true, attributes: true, attributeFilter: ["data-speed", "data-speed-x"] });
    this._io = new IntersectionObserver(([entry]) => this._listen(entry.isIntersecting), { rootMargin: "25% 0px" });
    this._io.observe(this);
    this._collect();
  }

  disconnectedCallback() {
    this._listen(false);
    this._motion.removeEventListener("change", this._onMotion);
    this._mo.disconnect();
    this._io.disconnect();
  }

  _collect() {
    for (const layer of this._layers) layer.el.style.translate = "";
    this._layers = [...this.querySelectorAll("[data-speed], [data-speed-x]")].map((el) => ({
      el,
      speed: Number.isFinite(parseFloat(el.dataset.speed)) ? parseFloat(el.dataset.speed) : 1,
      drift: parseFloat(el.dataset.speedX) || 0,
    }));
    this._schedule();
  }

  _listen(on) {
    if (on === this._listening) return;
    this._listening = on;
    const method = on ? "addEventListener" : "removeEventListener";
    window[method]("scroll", this._schedule, { passive: true });
    window[method]("resize", this._schedule, { passive: true });
    if (on) this._schedule();
    else {
      cancelAnimationFrame(this._raf);
      this._raf = 0;
    }
  }

  _onMotion = () => this._collect();

  _schedule = () => {
    if (!this._raf) this._raf = requestAnimationFrame(this._update);
  };

  _update = () => {
    this._raf = 0;
    if (this._motion.matches) {
      for (const layer of this._layers) layer.el.style.translate = "";
      return;
    }
    const r = this.getBoundingClientRect();
    const vh = window.innerHeight;
    for (const layer of this._layers) {
      const o = parallaxOffset(r.top, r.height, vh, layer.speed, layer.drift);
      layer.el.style.translate = `${o.x.toFixed(2)}px ${o.y.toFixed(2)}px`;
    }
  };
}

if (typeof customElements !== "undefined" && !customElements.get(TAG)) customElements.define(TAG, Parallax);
