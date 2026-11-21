// <mf-split-text>: splits a headline into letters or words that rise, fade, or unblur into place one after
// another when it scrolls into view (motion-forge). by: chars (default) or words. effect: rise (default,
// masked), fade, or blur. Words never break across lines, letters are split by grapheme so emoji and
// accents stay whole, and screen readers read the text once. Shows the text at once under
// prefers-reduced-motion. Call play() to run it again.

const TAG = "mf-split-text";
const MAX_TOTAL_STAGGER_MS = 1200;
const Base = typeof HTMLElement === "undefined" ? class {} : HTMLElement;

// User-perceived characters (grapheme clusters) of a string.
export function graphemes(text) {
  if (typeof Intl !== "undefined" && Intl.Segmenter) {
    return Array.from(new Intl.Segmenter(undefined, { granularity: "grapheme" }).segment(text), (s) => s.segment);
  }
  return Array.from(text);
}

// "Hello  world" -> [["H","e","l","l","o"], ["w","o","r","l","d"]]: words split into graphemes.
export function splitWords(text) {
  return String(text).split(/\s+/).filter(Boolean).map(graphemes);
}

// Milliseconds between units, shrunk so the last unit starts within MAX_TOTAL_STAGGER_MS.
export function staggerFor(count, stagger, maxTotal = MAX_TOTAL_STAGGER_MS) {
  if (count <= 1) return Math.max(0, stagger);
  return Math.max(0, Math.min(stagger, maxTotal / (count - 1)));
}

const STYLE = `
:host { display: inline; }
:host([hidden]) { display: none; }
.sr { position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden; clip: rect(0 0 0 0); clip-path: inset(50%); white-space: nowrap; border: 0; }
.word { display: inline-block; white-space: nowrap; vertical-align: top; }
:host(:not([effect])) .word, :host([effect="rise"]) .word { overflow: hidden; padding-block: .08em .14em; margin-block: -.08em -.14em; }
.u {
  display: inline-block;
  transition-property: translate, opacity, filter;
  transition-duration: var(--mf-split-duration, 800ms);
  transition-timing-function: var(--mf-split-ease, cubic-bezier(.2, .8, .2, 1));
  transition-delay: calc(var(--i) * var(--mf-split-step, 30ms));
}
:host([data-state="hidden"]:not([effect])) .u, :host([data-state="hidden"][effect="rise"]) .u { translate: 0 110%; }
:host([data-state="hidden"][effect="fade"]) .u { opacity: 0; }
:host([data-state="hidden"][effect="blur"]) .u { opacity: 0; filter: blur(8px); translate: 0 .25em; }
:host([data-init]) .u { transition: none; }
@media (prefers-reduced-motion: reduce) { .u { transition: none; } }
@media print { .u { translate: none !important; opacity: 1 !important; filter: none !important; } }
`;

export class SplitText extends Base {
  static observedAttributes = ["by", "stagger", "duration"];

  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = `<style>${STYLE}</style><span class="sr"></span><span class="split" part="text" aria-hidden="true"></span>`;
    this._sr = root.querySelector(".sr");
    this._split = root.querySelector(".split");
    this._raf = 0;
  }

  connectedCallback() {
    this._motion = matchMedia("(prefers-reduced-motion: reduce)");
    this._motion.addEventListener("change", this._onMotion);
    this._render();
    this._mo = new MutationObserver(() => this._render());
    this._mo.observe(this, { subtree: true, childList: true, characterData: true });
    this._io = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) {
        if (this.hasAttribute("repeat") && entry.boundingClientRect.top > 0) this._hide();
        return;
      }
      if (!this.hasAttribute("repeat")) this._io.disconnect();
      this._reveal();
    }, { threshold: 0.3 });
    this._io.observe(this);
  }

  disconnectedCallback() {
    cancelAnimationFrame(this._raf);
    this._raf = 0;
    this._motion.removeEventListener("change", this._onMotion);
    this._mo.disconnect();
    this._io.disconnect();
    this._motion = null;
  }

  attributeChangedCallback() {
    if (this._motion) this._render();
  }

  // Hide the text and reveal it again.
  play() {
    this._hide();
    this._reveal();
  }

  _render() {
    const text = this.textContent.replace(/\s+/g, " ").trim();
    const byWords = this.getAttribute("by") === "words";
    const words = splitWords(text);
    this._sr.textContent = text;
    const frag = document.createDocumentFragment();
    let i = 0;
    words.forEach((chars, w) => {
      if (w > 0) frag.append(" ");
      const word = document.createElement("span");
      word.className = "word";
      for (const unit of byWords ? [chars.join("")] : chars) {
        const u = document.createElement("span");
        u.className = "u";
        u.style.setProperty("--i", String(i++));
        u.textContent = unit;
        word.append(u);
      }
      frag.append(word);
    });
    this._split.replaceChildren(frag);
    const stagger = parseFloat(this.getAttribute("stagger"));
    const step = staggerFor(i, Number.isFinite(stagger) ? stagger : byWords ? 70 : 30);
    this.style.setProperty("--mf-split-step", `${step.toFixed(1)}ms`);
    const duration = parseFloat(this.getAttribute("duration"));
    if (Number.isFinite(duration) && duration >= 0) this.style.setProperty("--mf-split-duration", `${duration}ms`);
    else this.style.removeProperty("--mf-split-duration");
    if (this.dataset.state !== "shown") this._hide();
  }

  _hide() {
    cancelAnimationFrame(this._raf);
    this._raf = 0;
    if (this._motion.matches) {
      this.dataset.state = "shown";
      return;
    }
    this.toggleAttribute("data-init", true);
    this.dataset.state = "hidden";
  }

  _reveal() {
    if (this._motion.matches || !this.hasAttribute("data-init")) {
      this.removeAttribute("data-init");
      this.dataset.state = "shown";
      return;
    }
    // Two frames: the hidden state must paint without transitions before the reveal can animate.
    this._raf = requestAnimationFrame(() => {
      this._raf = requestAnimationFrame(() => {
        this._raf = 0;
        this.removeAttribute("data-init");
        this.dataset.state = "shown";
      });
    });
  }

  _onMotion = () => {
    if (this._motion.matches) {
      cancelAnimationFrame(this._raf);
      this._raf = 0;
      this.removeAttribute("data-init");
      this.dataset.state = "shown";
    }
  };
}

if (typeof customElements !== "undefined" && !customElements.get(TAG)) customElements.define(TAG, SplitText);
