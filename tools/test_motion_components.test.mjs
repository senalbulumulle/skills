// Tests for the pure helpers exported by mcp/web-dev/motion-forge/components. Run: node --test tools/
// Importing a component in Node defines nothing: the custom element registers only where customElements exists.
import { test } from "node:test";
import assert from "node:assert/strict";

const dir = "../mcp/web-dev/motion-forge/components";
const Shader = await import(`${dir}/shader-gradient.js`);
const Tilt = await import(`${dir}/tilt-card.js`);
const Parallax = await import(`${dir}/parallax.js`);
const Scene = await import(`${dir}/scroll-scene.js`);
const Reveal = await import(`${dir}/reveal.js`);
const Magnetic = await import(`${dir}/magnetic.js`);
const Spotlight = await import(`${dir}/spotlight.js`);
const Scramble = await import(`${dir}/text-scramble.js`);
const Split = await import(`${dir}/split-text.js`);

const close = (a, b, eps = 1e-9) => assert.ok(Math.abs(a - b) < eps, `${a} != ${b}`);

test("shader-gradient: parses 2 to 5 hex colors, else the defaults", () => {
  assert.deepEqual(Shader.parseColors("#000, #fff"), [[0, 0, 0], [1, 1, 1]]);
  assert.deepEqual(Shader.parseColors("#f00, 00ff00, bogus")[1], [0, 1, 0]);
  assert.equal(Shader.parseColors("#111,#222,#333,#444,#555,#666").length, 5);
  const defaults = Shader.parseColors(null);
  assert.equal(defaults.length, 5);
  assert.deepEqual(Shader.parseColors("#123"), defaults);
});

test("shader-gradient: fallback gradient and pointer space", () => {
  assert.equal(Shader.fallbackGradient([[0, 0, 0], [1, 1, 1]]), "linear-gradient(135deg, rgb(0 0 0) 0%, rgb(255 255 255) 100%)");
  assert.deepEqual(Shader.pointerToField(200, 100, 400, 200), [0, 0]);
  assert.deepEqual(Shader.pointerToField(400, 0, 400, 200), [1, 0.5]); // top right, y up, unit = shorter side
});

test("tilt-card: angles follow the pointer and clamp at the edges", () => {
  const center = Tilt.tiltAngles(150, 100, 300, 200, 10);
  close(center.rx, 0); close(center.ry, 0);
  assert.equal(center.gx, 50);
  const topRight = Tilt.tiltAngles(300, 0, 300, 200, 10);
  assert.deepEqual([topRight.rx, topRight.ry, topRight.gx, topRight.gy], [10, 10, 100, 0]);
  const outside = Tilt.tiltAngles(900, -50, 300, 200, 10);
  assert.deepEqual([outside.rx, outside.ry], [10, 10]);
});

test("springs settle on their target without blowing up", () => {
  for (const step of [Tilt.springStep, Magnetic.springStep]) {
    const s = { x: 0, v: 0 };
    let peak = 0;
    for (let i = 0; i < 120; i++) { step(s, 10, 1 / 60); peak = Math.max(peak, s.x); }
    close(s.x, 10, 0.05);
    assert.ok(peak < 13, `overshoot ${peak}`);
  }
});

test("parallax: layers rest when the section is centered and move at their speed", () => {
  const centered = Parallax.parallaxOffset(100, 600, 800, 0.5, 0.2);
  close(centered.x, 0); close(centered.y, 0);
  const below = Parallax.parallaxOffset(400, 600, 800, 0.5, 0.1); // center 300px below the viewport's
  assert.deepEqual(below, { x: -30, y: -150 });
  // A 0.5 layer moves half as far as the page: scrolling 100px shifts it back by 50px.
  const a = Parallax.parallaxOffset(400, 600, 800, 0.5).y, b = Parallax.parallaxOffset(300, 600, 800, 0.5).y;
  assert.equal(b - a, 50);
  assert.equal(Parallax.parallaxOffset(400, 600, 800).y, 0);
});

test("scroll-scene: scene and window progress", () => {
  assert.equal(Scene.sceneProgress(100, 2400, 800), 0);
  assert.equal(Scene.sceneProgress(-800, 2400, 800), 0.5);
  assert.equal(Scene.sceneProgress(-5000, 2400, 800), 1);
  assert.equal(Scene.sceneProgress(0, 800, 800), 1);
  assert.equal(Scene.localProgress(0.5, 0.25, 0.75), 0.5);
  assert.equal(Scene.localProgress(0.1, 0.25, 0.75), 0);
  assert.equal(Scene.localProgress(0.9, 0.25, 0.75), 1);
  assert.equal(Scene.localProgress(0.6, 0.5, 0.5), 1);
});

test("reveal: stagger delays cap after twelve children", () => {
  assert.deepEqual([0, 1, 12, 40].map((i) => Reveal.staggerDelay(i, 80)), [0, 80, 960, 960]);
  assert.equal(Reveal.staggerDelay(-1, 80), 0);
});

test("magnetic: pulls inside the radius only", () => {
  const box = [100, 100, 100, 40];
  assert.deepEqual(Magnetic.magnetTarget(150, 120, ...box, 60, 0.5), { x: 0, y: 0, active: true });
  assert.deepEqual(Magnetic.magnetTarget(250, 120, ...box, 60, 0.5), { x: 50, y: 0, active: true });
  assert.equal(Magnetic.magnetTarget(300, 120, ...box, 60, 0.5).active, false);
  assert.equal(Magnetic.magnetTarget(150, 300, ...box, 60, 0.5).x, 0);
});

test("spotlight: light position relative to each card", () => {
  assert.deepEqual(Spotlight.spotlightPositions(50, 60, [{ left: 0, top: 0 }, { left: 100, top: 40 }]),
    [{ x: 50, y: 60 }, { x: -50, y: 20 }]);
});

test("text-scramble: thresholds, settled text, and kept whitespace", () => {
  const t = Scramble.revealThresholds(5, () => 0);
  assert.deepEqual(t, [0, 0.1875, 0.375, 0.5625, 0.75]);
  assert.ok(Scramble.revealThresholds(20).every((v) => v >= 0 && v < 1));
  const chars = Array.from("Kp 5");
  const thresholds = Scramble.revealThresholds(chars.length, () => 0.5);
  assert.equal(Scramble.scrambleFrame(chars, thresholds, 1, ["#"]), "Kp 5");
  assert.equal(Scramble.scrambleFrame(chars, thresholds, 0, ["#"]), "## #");
});

test("split-text: graphemes, words, and stagger cap", () => {
  assert.deepEqual(Split.graphemes("Tromsø"), ["T", "r", "o", "m", "s", "ø"]);
  assert.equal(Split.graphemes("👩‍👩‍👧 é").length, 3);
  assert.deepEqual(Split.splitWords("  The   sky "), [["T", "h", "e"], ["s", "k", "y"]]);
  assert.deepEqual(Split.splitWords(""), []);
  assert.equal(Split.staggerFor(10, 30), 30);
  assert.equal(Split.staggerFor(101, 30), 12);
  assert.equal(Split.staggerFor(1, 30), 30);
});

test("components register nothing outside a browser", () => {
  assert.equal(typeof globalThis.customElements, "undefined");
  for (const Cls of [Shader.ShaderGradient, Tilt.TiltCard, Parallax.Parallax, Scene.ScrollScene, Reveal.Reveal,
    Magnetic.Magnetic, Spotlight.Spotlight, Scramble.TextScramble, Split.SplitText]) {
    assert.equal(typeof Cls, "function");
  }
});
