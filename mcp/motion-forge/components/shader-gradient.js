// <mf-shader-gradient>: a slow, domain-warped WebGL color field for hero backgrounds (motion-forge).
// Content inside renders above the field. The field bends away from the pointer, pauses offscreen and in
// hidden tabs, draws one still frame under prefers-reduced-motion, and shows a CSS gradient without WebGL.

const TAG = "mf-shader-gradient";
const DEFAULT_COLORS = "#0b1d26, #16425b, #2f6f73, #d9a05b, #f2e3c6";
const MAX_COLORS = 5;
const MAX_DPR = 1.5;
const Base = typeof HTMLElement === "undefined" ? class {} : HTMLElement;

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

// "#0b1d26, #f2e3c6" -> [[r, g, b], ...] in 0..1. Keeps 2 to 5 valid hex colors, else the defaults.
export function parseColors(value) {
  const colors = [];
  for (const part of String(value ?? "").split(",")) {
    const hex = part.trim().replace(/^#/, "");
    if (!/^(?:[0-9a-f]{3}|[0-9a-f]{6})$/i.test(hex)) continue;
    const full = hex.length === 3 ? [...hex].map((c) => c + c).join("") : hex;
    colors.push([0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16) / 255));
    if (colors.length === MAX_COLORS) break;
  }
  return colors.length >= 2 ? colors : parseColors(DEFAULT_COLORS);
}

// The CSS gradient shown before the first frame and when WebGL is unavailable.
export function fallbackGradient(colors) {
  const stops = colors.map((c, i) => {
    const [r, g, b] = c.map((v) => Math.round(v * 255));
    return `rgb(${r} ${g} ${b}) ${Math.round((i / (colors.length - 1)) * 100)}%`;
  });
  return `linear-gradient(135deg, ${stops.join(", ")})`;
}

// Pointer position in CSS pixels (from the top left) -> the shader's square, centered, y-up space.
export function pointerToField(x, y, width, height) {
  const unit = Math.max(1, Math.min(width, height));
  return [(x - width / 2) / unit, (height / 2 - y) / unit];
}

const VERTEX = `attribute vec2 a_pos;
void main() { gl_Position = vec4(a_pos, 0.0, 1.0); }`;

const FRAGMENT = `#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
uniform vec2 u_res;
uniform float u_time;
uniform vec2 u_pointer;
uniform float u_influence;
uniform float u_grain;
uniform vec3 u_colors[${MAX_COLORS}];
uniform int u_count;

float hash(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
             mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}

float fbm(vec2 p) {
  float v = 0.0;
  float a = 0.5;
  mat2 m = mat2(1.6, 1.2, -1.2, 1.6);
  for (int i = 0; i < 4; i++) {
    v += a * noise(p);
    p = m * p;
    a *= 0.5;
  }
  return v;
}

vec3 ramp(float t) {
  float s = t * float(u_count - 1);
  vec3 c = u_colors[0];
  for (int i = 0; i < ${MAX_COLORS - 1}; i++) {
    if (i >= u_count - 1) break;
    c = mix(c, u_colors[i + 1], smoothstep(float(i), float(i) + 1.0, s));
  }
  return c;
}

void main() {
  vec2 p = (gl_FragCoord.xy - 0.5 * u_res) / min(u_res.x, u_res.y);
  float t = u_time;
  vec2 d = p - u_pointer;
  vec2 q = vec2(fbm(p * 0.9 + vec2(0.0, t * 0.5)), fbm(p * 0.9 + vec2(5.2, -t * 0.4)));
  q += u_influence * 0.6 * exp(-dot(d, d) * 3.0) * d;
  float f = fbm(p * 0.8 + 1.8 * q + vec2(t * 0.1, -t * 0.07));
  float tone = clamp((f - 0.3) * 2.0 + 0.2 * (q.x - 0.5), 0.0, 1.0);
  vec3 col = ramp(pow(tone, 1.6));
  col += (hash(gl_FragCoord.xy + fract(t) * 91.7) - 0.5) * u_grain;
  gl_FragColor = vec4(col, 1.0);
}`;

const STYLE = `
:host { display: block; position: relative; isolation: isolate; overflow: hidden; background: var(--mf-fallback); }
:host([hidden]) { display: none; }
canvas { position: absolute; inset: 0; z-index: -1; display: block; width: 100%; height: 100%; opacity: 0; transition: opacity .8s ease; }
canvas.ready { opacity: 1; }
@media (prefers-reduced-motion: reduce) { canvas { transition: none; } }
`;

export class ShaderGradient extends Base {
  static observedAttributes = ["colors", "speed", "grain", "pointer"];

  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = `<style>${STYLE}</style><canvas part="canvas" aria-hidden="true"></canvas><slot></slot>`;
    this._canvas = root.querySelector("canvas");
    this._gl = null;
    this._program = null;
    this._raf = 0;
    this._time = 12;
    this._visible = false;
    this._pointer = [0, 0];
    this._target = [0, 0];
    this._influence = 0;
    this._targetInfluence = 0;
    this._canvas.addEventListener("webglcontextlost", (e) => {
      e.preventDefault();
      this._stop();
      this._program = null;
      this._canvas.classList.remove("ready");
    });
    this._canvas.addEventListener("webglcontextrestored", () => { if (this.isConnected) this._init(); });
  }

  connectedCallback() {
    this._applyFallback();
    this._motion = matchMedia("(prefers-reduced-motion: reduce)");
    this._motion.addEventListener("change", this._sync);
    this._resize = new ResizeObserver(() => this._fit());
    this._resize.observe(this);
    this._io = new IntersectionObserver(([entry]) => { this._visible = entry.isIntersecting; this._sync(); });
    this._io.observe(this);
    document.addEventListener("visibilitychange", this._sync);
    this.addEventListener("pointermove", this._onPointer, { passive: true });
    this.addEventListener("pointerleave", this._onLeave);
    this.addEventListener("pointercancel", this._onLeave);
    if (!this._program) this._init();
  }

  disconnectedCallback() {
    this._stop();
    this._motion.removeEventListener("change", this._sync);
    this._resize.disconnect();
    this._io.disconnect();
    document.removeEventListener("visibilitychange", this._sync);
    this.removeEventListener("pointermove", this._onPointer);
    this.removeEventListener("pointerleave", this._onLeave);
    this.removeEventListener("pointercancel", this._onLeave);
    if (this._gl && this._program && !this._gl.isContextLost()) {
      this._gl.deleteProgram(this._program);
      this._gl.deleteBuffer(this._buffer);
    }
    this._program = null;
  }

  attributeChangedCallback(name) {
    if (name === "colors") {
      this._applyFallback();
      this._uploadColors();
    }
    if (name === "pointer" && this.getAttribute("pointer") === "off") this._onLeave();
    if (!this._raf) this._draw();
  }

  _number(name, fallback, lo, hi) {
    const v = parseFloat(this.getAttribute(name));
    return Number.isFinite(v) ? clamp(v, lo, hi) : fallback;
  }

  _applyFallback() {
    this.style.setProperty("--mf-fallback", fallbackGradient(parseColors(this.getAttribute("colors"))));
  }

  _init() {
    const gl = this._canvas.getContext("webgl", {
      alpha: false, antialias: false, depth: false, stencil: false, powerPreference: "low-power",
    });
    if (!gl) {
      this.setAttribute("data-fallback", "");
      return;
    }
    const program = gl.createProgram();
    for (const [type, source] of [[gl.VERTEX_SHADER, VERTEX], [gl.FRAGMENT_SHADER, FRAGMENT]]) {
      const shader = gl.createShader(type);
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      gl.attachShader(program, shader);
      gl.deleteShader(shader);
    }
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      if (!gl.isContextLost()) console.warn(`${TAG}: ${gl.getProgramInfoLog(program)}`);
      gl.deleteProgram(program);
      this.setAttribute("data-fallback", "");
      return;
    }
    this.removeAttribute("data-fallback");
    this._gl = gl;
    this._program = program;
    this._buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this._buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const position = gl.getAttribLocation(program, "a_pos");
    gl.enableVertexAttribArray(position);
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
    gl.useProgram(program);
    this._u = Object.fromEntries(["u_res", "u_time", "u_pointer", "u_influence", "u_grain", "u_colors", "u_count"]
      .map((n) => [n, gl.getUniformLocation(program, n)]));
    this._uploadColors();
    this._fit();
    this._canvas.classList.add("ready");
    this._sync();
  }

  _uploadColors() {
    if (!this._program) return;
    const colors = parseColors(this.getAttribute("colors"));
    const flat = new Float32Array(MAX_COLORS * 3);
    colors.forEach((c, i) => flat.set(c, i * 3));
    this._gl.useProgram(this._program);
    this._gl.uniform3fv(this._u.u_colors, flat);
    this._gl.uniform1i(this._u.u_count, colors.length);
  }

  _fit() {
    const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
    const w = Math.max(1, Math.round(this.clientWidth * dpr));
    const h = Math.max(1, Math.round(this.clientHeight * dpr));
    if (this._canvas.width !== w || this._canvas.height !== h) {
      this._canvas.width = w;
      this._canvas.height = h;
    }
    if (this._program) {
      this._gl.viewport(0, 0, w, h);
      this._draw();
    }
  }

  _sync = () => {
    const reduced = this._motion?.matches;
    const run = Boolean(this._program) && this._visible && !document.hidden && !reduced;
    if (run && !this._raf) {
      this._last = performance.now();
      this._raf = requestAnimationFrame(this._frame);
    } else if (!run) {
      this._stop();
      this._draw();
    }
  };

  _stop() {
    cancelAnimationFrame(this._raf);
    this._raf = 0;
  }

  _frame = (now) => {
    const dt = Math.min((now - this._last) / 1000, 0.05);
    this._last = now;
    this._time += dt * this._number("speed", 0.35, 0, 4);
    const ease = 1 - Math.exp(-dt * 4);
    this._pointer[0] += (this._target[0] - this._pointer[0]) * ease;
    this._pointer[1] += (this._target[1] - this._pointer[1]) * ease;
    this._influence += (this._targetInfluence - this._influence) * ease;
    this._draw();
    this._raf = requestAnimationFrame(this._frame);
  };

  _draw() {
    if (!this._program || this._gl.isContextLost()) return;
    const gl = this._gl;
    gl.useProgram(this._program);
    gl.uniform2f(this._u.u_res, this._canvas.width, this._canvas.height);
    gl.uniform1f(this._u.u_time, this._time);
    gl.uniform2f(this._u.u_pointer, this._pointer[0], this._pointer[1]);
    gl.uniform1f(this._u.u_influence, this._influence);
    gl.uniform1f(this._u.u_grain, this._number("grain", 0.04, 0, 0.3));
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  _onPointer = (e) => {
    if (this.getAttribute("pointer") === "off") return;
    const r = this.getBoundingClientRect();
    this._target = pointerToField(e.clientX - r.left, e.clientY - r.top, r.width, r.height);
    this._targetInfluence = 1;
  };

  _onLeave = () => {
    this._targetInfluence = 0;
  };
}

if (typeof customElements !== "undefined" && !customElements.get(TAG)) customElements.define(TAG, ShaderGradient);
