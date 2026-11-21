// Tests for the JavaScript libraries shipped inside skills. Run: node --test tools/
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const Juice = require("../skills/game-dev/game-feel/assets/juice.js");
const Procgen = require("../skills/game-dev/game-procgen/assets/procgen.js");
const AI = require("../skills/game-dev/game-ai/assets/ai.js");
const Sfx = require("../skills/game-dev/game-audio/assets/sfx.js");
const PixelSprite = require("../skills/game-dev/game-art/assets/pixel-sprite.js");

const step = (fn, seconds, dt = 1 / 60) => { for (let t = 0; t < seconds; t += dt) fn(dt); };

test("juice: easing endpoints", () => {
  for (const [name, f] of Object.entries(Juice.ease)) {
    assert.ok(Math.abs(f(0)) < 1e-9, `${name}(0)`);
    assert.ok(Math.abs(f(1) - 1) < 1e-9, `${name}(1)`);
  }
});

test("juice: tween reaches target and calls onDone", () => {
  const tw = new Juice.Tweens(), obj = { x: 0 };
  let done = false;
  tw.to(obj, { x: 10 }, 0.2, Juice.ease.linear, () => { done = true; });
  step((dt) => tw.update(dt), 0.25);
  assert.equal(obj.x, 10);
  assert.ok(done);
  assert.equal(tw.list.length, 0);
});

test("juice: hit stop freezes then returns leftover time", () => {
  const hs = new Juice.HitStop();
  hs.trigger(0.04); // 2.4 frames at 60 fps: two frozen steps, then a partial one
  const dts = [0, 0, 0].map(() => hs.scale(1 / 60));
  assert.deepEqual(dts.slice(0, 2), [0, 0]);
  assert.ok(Math.abs(dts[2] - (3 / 60 - 0.04)) < 1e-9);
  assert.equal(hs.scale(1 / 60), 1 / 60);
});

test("juice: shake decays to rest; squash springs back", () => {
  const sh = new Juice.Shake({ rng: () => 0.5 });
  sh.add(1);
  step((dt) => sh.update(dt), 1);
  assert.equal(sh.trauma, 0);
  assert.equal(Math.abs(sh.x), 0); // may be -0
  const sq = new Juice.Squash();
  sq.kick(0.3);
  step((dt) => sq.update(dt), 1);
  assert.ok(Math.abs(sq.amount) < 0.01);
  assert.ok(Math.abs(sq.scaleX * sq.scaleY - 1) < 0.02);
});

test("juice: particles are pooled and expire", () => {
  const ps = new Juice.Particles(10, () => 0.5);
  assert.equal(ps.burst(0, 0, { count: 25 }), 10);
  step((dt) => ps.update(dt), 1);
  assert.equal(ps.count, 0);
});

test("juice: jump assist honours coyote time and buffer", () => {
  const ja = new Juice.JumpAssist({ coyote: 0.1, buffer: 0.1 });
  ja.update(1 / 60, true, false);
  ja.update(0.05, false, true); // pressed 0.05 s after leaving the ledge
  assert.ok(ja.shouldJump());
  assert.ok(!ja.shouldJump()); // consumed
  ja.update(0.2, false, true); // too late after leaving the ground
  assert.ok(!ja.shouldJump());
});

test("procgen: same seed, same output", () => {
  const a = Procgen.caves(40, 20, Procgen.makeRng(11));
  const b = Procgen.caves(40, 20, Procgen.makeRng(11));
  assert.equal(Procgen.toText(a), Procgen.toText(b));
});

test("procgen: caves and rooms are one connected space over many seeds", () => {
  for (let seed = 0; seed < 100; seed++) {
    const cave = Procgen.caves(48, 24, Procgen.makeRng(seed));
    Procgen.keepLargestRegion(cave);
    assert.ok(Procgen.regions(cave).length <= 1, `cave seed ${seed}`);
    const { grid, rooms } = Procgen.rooms(48, 24, Procgen.makeRng(seed));
    assert.ok(rooms.length > 0);
    assert.equal(Procgen.regions(grid).length, 1, `rooms seed ${seed}`);
  }
});

test("procgen: noise in range, poisson spacing, weighted odds", () => {
  const noise = Procgen.makeNoise2D(3);
  for (let i = 0; i < 5000; i++) {
    const v = Procgen.fbm(noise, i * 0.031, i * 0.017);
    assert.ok(v >= 0 && v < 1);
  }
  const pts = Procgen.poissonDisk(200, 120, 12, Procgen.makeRng(4));
  for (let i = 0; i < pts.length; i++)
    for (let j = i + 1; j < pts.length; j++)
      assert.ok(Math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]) >= 12);
  const rng = Procgen.makeRng(9), counts = { a: 0, b: 0 };
  for (let i = 0; i < 40000; i++) counts[rng.weighted([{ id: "a", weight: 3 }, { id: "b", weight: 1 }]).id]++;
  assert.ok(Math.abs(counts.a / 40000 - 0.75) < 0.01);
  assert.equal(rng.weighted([{ weight: 0 }]), null);
});

test("ai: A* path lengths match BFS shortest paths", () => {
  for (let seed = 0; seed < 60; seed++) {
    const g = Procgen.caves(40, 25, Procgen.makeRng(seed));
    const region = Procgen.keepLargestRegion(g);
    if (region.length < 2) continue;
    const a = region[0], b = region[region.length - 1];
    const path = AI.findPath(g, a % g.w, (a / g.w) | 0, b % g.w, (b / g.w) | 0);
    const dist = new Int32Array(g.w * g.h).fill(-1);
    dist[a] = 0;
    const queue = [a];
    for (let i = 0; i < queue.length; i++) {
      const c = queue[i], x = c % g.w, y = (c / g.w) | 0;
      for (const [nx, ny] of [[x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1]]) {
        if (Procgen.get(g, nx, ny) !== 0) continue;
        const j = ny * g.w + nx;
        if (dist[j] < 0) { dist[j] = dist[c] + 1; queue.push(j); }
      }
    }
    assert.equal(path.length - 1, dist[b], `seed ${seed}`);
  }
});

test("ai: no diagonal corner cutting; unreachable returns null", () => {
  const grid = { w: 3, h: 3, cells: Uint8Array.from([0, 1, 1, 1, 0, 1, 1, 1, 0]) };
  assert.equal(AI.findPath(grid, 0, 0, 2, 2, { diagonal: true }), null);
  const open = { w: 3, h: 3, cells: new Uint8Array(9) };
  assert.equal(AI.findPath(open, 0, 0, 2, 2, { diagonal: true }).length, 3);
});

test("ai: state machine, tokens, line of sight", () => {
  const log = [];
  const fsm = new AI.StateMachine({}, {
    idle: { enter: () => log.push("in:idle"), update: (o, dt, m) => (m.time > 0.1 ? "attack" : null), exit: () => log.push("out:idle") },
    attack: { enter: () => log.push("in:attack") },
  }, "idle");
  step((dt) => fsm.update(dt), 0.2);
  assert.equal(fsm.current, "attack");
  assert.deepEqual(log, ["in:idle", "out:idle", "in:attack"]);
  assert.throws(() => fsm.change("nope"));
  const tokens = new AI.AttackTokens(1);
  assert.ok(tokens.request("a"));
  assert.ok(!tokens.request("b"));
  tokens.release("a");
  assert.ok(tokens.request("b"));
  const wall = { w: 5, h: 1, cells: Uint8Array.from([0, 0, 1, 0, 0]) };
  assert.ok(AI.lineOfSight(wall, 0, 0, 1, 0));
  assert.ok(!AI.lineOfSight(wall, 0, 0, 4, 0));
});

test("ai: arrive slows near the target", () => {
  const far = AI.arrive({ x: 0, y: 0 }, { x: 0, y: 0 }, { x: 500, y: 0 }, 100, 50);
  const near = AI.arrive({ x: 0, y: 0 }, { x: 0, y: 0 }, { x: 5, y: 0 }, 100, 50);
  assert.equal(far.x, 100);
  assert.ok(Math.abs(near.x - 10) < 1e-9);
});

// Minimal Web Audio mock: enough surface for sfx.js, with onended fired manually.
function mockAudio() {
  const sources = [];
  const param = () => ({ setValueAtTime() {}, linearRampToValueAtTime() {}, exponentialRampToValueAtTime(v) { if (v <= 0) throw new RangeError("exp ramp to <= 0"); } });
  const node = (extra = {}) => ({ connect() {}, disconnect() {}, ...extra });
  class Ctx {
    constructor() { this.state = "suspended"; this.currentTime = 0; this.sampleRate = 8000; this.destination = node(); }
    resume() { this.state = "running"; return Promise.resolve(); }
    createGain() { return node({ gain: param() }); }
    createDynamicsCompressor() { return node(); }
    createBiquadFilter() { return node({ frequency: param() }); }
    createBuffer(ch, len) { const data = new Float32Array(len); return { getChannelData: () => data }; }
    createOscillator() { const s = node({ frequency: param(), start() {}, stop() {} }); sources.push(s); return s; }
    createBufferSource() { const s = node({ playbackRate: param(), start() {}, stop() {} }); sources.push(s); return s; }
  }
  return { Ctx, sources };
}

test("sfx: locked until unlock, voice limits, mute, voices freed on end", () => {
  const { Ctx, sources } = mockAudio();
  const sfx = Sfx.create({ AudioContextClass: Ctx, rng: () => 0.5 });
  assert.equal(sfx.play("jump"), false);
  assert.ok(sfx.unlock());
  for (const name of Object.keys(Sfx.PRESETS)) assert.equal(sfx.play(name), true, name);
  assert.deepEqual([1, 2, 3].map(() => sfx.play("explosion")), [true, true, false]);
  sfx.setMuted(true);
  assert.equal(sfx.play("jump"), false);
  sfx.setMuted(false);
  for (const s of sources) if (s.onended) s.onended();
  assert.equal(sfx.play("explosion"), true);
  assert.throws(() => sfx.play("nope"));
  assert.throws(() => sfx.setVolume("nope", 1));
});

test("pixel-sprite: runs, flipping, palette errors", () => {
  const s = PixelSprite.parse(["aab.", "..bb"], { a: "#f00", b: "#00f" });
  const calls = [];
  const ctx = { set fillStyle(v) { this.c = v; }, fillRect(x, y, w, h) { calls.push([this.c, x, y, w, h].join()); } };
  PixelSprite.draw(ctx, s, 10, 20, 2);
  assert.deepEqual(calls, ["#f00,10,20,4,2", "#00f,14,20,2,2", "#00f,14,22,4,2"]);
  calls.length = 0;
  PixelSprite.draw(ctx, s, 0, 0, 1, { flipX: true });
  assert.deepEqual(calls, ["#f00,2,0,2,1", "#00f,1,0,1,1", "#00f,0,1,2,1"]);
  assert.throws(() => PixelSprite.parse(["x"], {}), /not in the palette/);
});
