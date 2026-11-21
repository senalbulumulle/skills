// <mf-scroll-scene>: a pinned, scroll-scrubbed stage for motion graphics (motion-forge). The scene is
// `length` viewports tall; its content sticks to the viewport while --mf-progress runs from 0 to 1. Children
// with data-start and data-end (0..1) also get their own --mf-p for that slice of the scroll, so CSS like
// `opacity: var(--mf-p)` choreographs each part. Under prefers-reduced-motion the scene unpins and shows
// progress `reduced-progress` (default 1).

const TAG = "mf-scroll-scene";
const Base = typeof HTMLElement === "undefined" ? class {} : HTMLElement;

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

// Scene progress from its getBoundingClientRect() top and height and the pinned stage's height.
export function sceneProgress(rectTop, rectHeight, stageHeight) {
  const distance = rectHeight - stageHeight;
  return distance > 0 ? clamp(-rectTop / distance, 0, 1) : 1;
}

// Progress inside one child's [start, end] window of the scene.
export function localProgress(progress, start = 0, end = 1) {
  if (end <= start) return progress >= end ? 1 : 0;
  return clamp((progress - start) / (end - start), 0, 1);
}

const STYLE = `
:host { display: block; position: relative; height: calc(var(--mf-scene-length, 3) * 100vh); }
:host([hidden]) { display: none; }
.stage { position: sticky; top: 0; height: 100vh; height: 100svh; overflow: hidden; overflow: clip; }
:host([data-reduced]) { height: auto; }
:host([data-reduced]) .stage { position: relative; height: auto; min-height: 100svh; }
`;

export class ScrollScene extends Base {
  static observedAttributes = ["length", "reduced-progress"];

  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = `<style>${STYLE}</style><div class="stage" part="stage"><slot></slot></div>`;
    this._stage = root.querySelector(".stage");
    this._raf = 0;
    this._progress = -1;
    this._parts = [];
  }

  get progress() {
    return Math.max(0, this._progress);
  }

  connectedCallback() {
    this._motion = matchMedia("(prefers-reduced-motion: reduce)");
    this._motion.addEventListener("change", this._schedule);
    this._mo = new MutationObserver(() => this._collect());
    this._mo.observe(this, { subtree: true, childList: true, attributes: true, attributeFilter: ["data-start", "data-end"] });
    this._io = new IntersectionObserver(([entry]) => this._listen(entry.isIntersecting), { rootMargin: "10% 0px" });
    this._io.observe(this);
    this._collect();
  }

  disconnectedCallback() {
    this._listen(false);
    cancelAnimationFrame(this._raf);
    this._raf = 0;
    this._motion.removeEventListener("change", this._schedule);
    this._mo.disconnect();
    this._io.disconnect();
    this._motion = null;
  }

  attributeChangedCallback(name) {
    if (name === "length") {
      const length = parseFloat(this.getAttribute("length"));
      if (Number.isFinite(length) && length >= 1) this.style.setProperty("--mf-scene-length", String(length));
      else this.style.removeProperty("--mf-scene-length");
    }
    this._progress = -1;
    if (this._motion) this._schedule();
  }

  _collect() {
    this._parts = [...this.querySelectorAll("[data-start], [data-end]")].map((el) => ({
      el,
      start: Number.isFinite(parseFloat(el.dataset.start)) ? parseFloat(el.dataset.start) : 0,
      end: Number.isFinite(parseFloat(el.dataset.end)) ? parseFloat(el.dataset.end) : 1,
    }));
    this._progress = -1;
    this._schedule();
  }

  _listen(on) {
    if (on === this._listening) return;
    this._listening = on;
    const method = on ? "addEventListener" : "removeEventListener";
    window[method]("scroll", this._schedule, { passive: true });
    window[method]("resize", this._schedule, { passive: true });
    if (on) this._schedule();
  }

  _schedule = () => {
    if (!this._raf) this._raf = requestAnimationFrame(this._update);
  };

  _update = () => {
    this._raf = 0;
    const reduced = this._motion.matches;
    this.toggleAttribute("data-reduced", reduced);
    let p;
    if (reduced) {
      const rest = parseFloat(this.getAttribute("reduced-progress"));
      p = Number.isFinite(rest) ? clamp(rest, 0, 1) : 1;
    } else {
      const r = this.getBoundingClientRect();
      p = sceneProgress(r.top, r.height, this._stage.offsetHeight);
    }
    if (p === this._progress) return;
    this._progress = p;
    this.style.setProperty("--mf-progress", p.toFixed(4));
    for (const part of this._parts) part.el.style.setProperty("--mf-p", localProgress(p, part.start, part.end).toFixed(4));
    this.dispatchEvent(new CustomEvent("mf-progress", { detail: { progress: p } }));
  };
}

if (typeof customElements !== "undefined" && !customElements.get(TAG)) customElements.define(TAG, ScrollScene);
