// <mf-text-scramble>: text that decodes from shuffling glyphs into its real words, left to right with a
// little randomness (motion-forge). trigger: visible (default, once), load, or hover (also on focus).
// Screen readers and copy-paste get the real text; the box keeps the final text's size while it runs.
// Set the `text` property to decode into new text. Shows the text at once under prefers-reduced-motion.

const TAG = "mf-text-scramble";
const DEFAULT_GLYPHS = "!<>-_\\/[]{}=+*^?#%&";
const FRAME_MS = 40;
const Base = typeof HTMLElement === "undefined" ? class {} : HTMLElement;

// When each character settles, in 0..1 of the run: mostly left to right, plus up to 0.25 of jitter.
export function revealThresholds(length, rand = Math.random) {
  return Array.from({ length }, (_, i) => (length > 1 ? (i / (length - 1)) * 0.75 : 0) + rand() * 0.25);
}

// The text at `progress`: settled characters and whitespace as written, the rest as random glyphs.
export function scrambleFrame(chars, thresholds, progress, glyphs, rand = Math.random) {
  return chars.map((c, i) => (progress >= thresholds[i] || /\s/.test(c) ? c : glyphs[Math.floor(rand() * glyphs.length)])).join("");
}

const STYLE = `
:host { display: inline-block; }
:host([hidden]) { display: none; }
.stack { display: inline-grid; }
.stack > * { grid-area: 1 / 1; }
.fx { white-space: pre-wrap; }
:host([data-running]) .text { color: transparent; }
:host(:not([data-running])) .fx { visibility: hidden; }
`;

export class TextScramble extends Base {
  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = `<style>${STYLE}</style><span class="stack"><span class="text" part="text"></span><span class="fx" part="glyphs" aria-hidden="true"></span></span>`;
    this._textEl = root.querySelector(".text");
    this._fx = root.querySelector(".fx");
    this._raf = 0;
    this._text = null;
  }

  get text() {
    return this._text ?? "";
  }

  set text(value) {
    this._text = String(value).replace(/\s+/g, " ").trim();
    this._textEl.textContent = this._text;
    if (this.isConnected) this.play();
  }

  connectedCallback() {
    if (Object.prototype.hasOwnProperty.call(this, "text")) {
      // A framework set `text` before this element upgraded; move it onto the setter.
      const value = this.text;
      delete this.text;
      this._text = String(value).replace(/\s+/g, " ").trim();
      this._textEl.textContent = this._text;
    }
    if (this._text === null) {
      this._text = this.textContent.replace(/\s+/g, " ").trim();
      this._textEl.textContent = this._text;
    }
    this._motion = matchMedia("(prefers-reduced-motion: reduce)");
    const trigger = this.getAttribute("trigger") || "visible";
    if (trigger === "load") this.play();
    else if (trigger === "hover") {
      this.addEventListener("pointerenter", this.play);
      this.addEventListener("focusin", this.play);
    } else {
      this._io = new IntersectionObserver(([entry]) => {
        if (!entry.isIntersecting) return;
        this._io.disconnect();
        this.play();
      }, { threshold: 0.6 });
      this._io.observe(this);
    }
  }

  disconnectedCallback() {
    this._finish();
    this._io?.disconnect();
    this.removeEventListener("pointerenter", this.play);
    this.removeEventListener("focusin", this.play);
  }

  play = () => {
    if (!this._motion || this._motion.matches || !this._text) return this._finish();
    if (this._raf) return;
    const glyphs = Array.from(this.getAttribute("glyphs") || DEFAULT_GLYPHS);
    const chars = Array.from(this._text);
    const thresholds = revealThresholds(chars.length);
    const duration = Math.max(100, parseFloat(this.getAttribute("duration")) || 900);
    const start = performance.now();
    let drawn = -Infinity;
    this.toggleAttribute("data-running", true);
    const frame = (now) => {
      const progress = Math.min(1, (now - start) / duration);
      if (progress >= 1) return this._finish();
      if (now - drawn >= FRAME_MS) {
        drawn = now;
        this._fx.textContent = scrambleFrame(chars, thresholds, progress, glyphs.length ? glyphs : [...DEFAULT_GLYPHS]);
      }
      this._raf = requestAnimationFrame(frame);
    };
    this._raf = requestAnimationFrame(frame);
  };

  _finish() {
    cancelAnimationFrame(this._raf);
    this._raf = 0;
    this._fx.textContent = "";
    this.removeAttribute("data-running");
  }
}

if (typeof customElements !== "undefined" && !customElements.get(TAG)) customElements.define(TAG, TextScramble);
