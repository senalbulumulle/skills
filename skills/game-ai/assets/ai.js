// ai.js: enemy and NPC behavior helpers. No dependencies.
// Exposes a global `AI` in browsers and module.exports in Node (for tests).
// Vectors are plain { x, y }. Grids are { w, h, cells } with 1 = wall, 0 = floor (same as procgen.js).
(function (root) {
  "use strict";

  // ---- Finite state machine. states: { name: { enter?, update?, exit? } }; update returns the next state name to switch. ----
  class StateMachine {
    constructor(owner, states, initial) {
      this.owner = owner;
      this.states = states;
      this.current = null;
      this.time = 0; // seconds in the current state; use for telegraph and recovery timings
      this.change(initial);
    }
    change(name) {
      if (!this.states[name]) throw new Error(`unknown state: ${name}`);
      const prev = this.current && this.states[this.current];
      if (prev && prev.exit) prev.exit(this.owner, this);
      this.current = name;
      this.time = 0;
      const next = this.states[name];
      if (next.enter) next.enter(this.owner, this);
    }
    update(dt) {
      this.time += dt;
      const state = this.states[this.current];
      const next = state.update ? state.update(this.owner, dt, this) : undefined;
      if (next && next !== this.current) this.change(next);
    }
  }

  // ---- Vector helpers ----
  const len = (v) => Math.hypot(v.x, v.y);
  const sub = (a, b) => ({ x: a.x - b.x, y: a.y - b.y });
  const scale = (v, s) => ({ x: v.x * s, y: v.y * s });
  const normalize = (v) => { const l = len(v); return l > 1e-9 ? scale(v, 1 / l) : { x: 0, y: 0 }; };
  const limit = (v, max) => { const l = len(v); return l > max ? scale(v, max / l) : v; };

  // ---- Steering behaviors: each returns a steering force (desired velocity minus current velocity). ----
  // Apply: vel = limit(vel + limit(force, maxForce) * dt, maxSpeed); pos += vel * dt.
  function seek(pos, vel, target, maxSpeed) {
    return sub(scale(normalize(sub(target, pos)), maxSpeed), vel);
  }
  function flee(pos, vel, threat, maxSpeed) {
    return sub(scale(normalize(sub(pos, threat)), maxSpeed), vel);
  }
  // Like seek, but slows down inside slowRadius and stops at the target.
  function arrive(pos, vel, target, maxSpeed, slowRadius) {
    const offset = sub(target, pos);
    const dist = len(offset);
    const speed = maxSpeed * Math.min(1, dist / Math.max(slowRadius, 1e-9));
    return sub(scale(normalize(offset), speed), vel);
  }
  // Smooth random roaming. Keeps its own angle on `state`; rng() returns [0, 1); jitter is max radians per second.
  function wander(state, vel, maxSpeed, rng, dt, jitter = 3) {
    if (state.wanderAngle === undefined) state.wanderAngle = rng() * Math.PI * 2;
    state.wanderAngle += (rng() - 0.5) * 2 * jitter * dt;
    const desired = { x: Math.cos(state.wanderAngle) * maxSpeed, y: Math.sin(state.wanderAngle) * maxSpeed };
    return sub(desired, vel);
  }
  // Push away from neighbours closer than radius; stronger when closer. neighbors: [{ x, y }].
  function separation(pos, neighbors, radius) {
    let fx = 0, fy = 0;
    for (const n of neighbors) {
      const dx = pos.x - n.x, dy = pos.y - n.y;
      const d = Math.hypot(dx, dy);
      if (d > 0 && d < radius) {
        const strength = (radius - d) / radius;
        fx += (dx / d) * strength;
        fy += (dy / d) * strength;
      }
    }
    return { x: fx, y: fy };
  }

  // ---- A* on a grid. Returns [[x, y], ...] from start to goal inclusive, or null if unreachable. ----
  function findPath(grid, sx, sy, gx, gy, { diagonal = false } = {}) {
    const W = grid.w, H = grid.h;
    const free = (x, y) => x >= 0 && y >= 0 && x < W && y < H && grid.cells[y * W + x] === 0;
    if (!free(sx, sy) || !free(gx, gy)) return null;
    const start = sy * W + sx, goal = gy * W + gx;
    const h = diagonal
      ? (x, y) => { const dx = Math.abs(x - gx), dy = Math.abs(y - gy); return dx + dy + (Math.SQRT2 - 2) * Math.min(dx, dy); }
      : (x, y) => Math.abs(x - gx) + Math.abs(y - gy);
    const g = new Float64Array(W * H).fill(Infinity);
    const came = new Int32Array(W * H).fill(-1);
    const closed = new Uint8Array(W * H);
    const heap = []; // binary min-heap of [f, index]
    const push = (f, i) => {
      heap.push([f, i]);
      let c = heap.length - 1;
      while (c > 0) {
        const p = (c - 1) >> 1;
        if (heap[p][0] <= heap[c][0]) break;
        [heap[p], heap[c]] = [heap[c], heap[p]];
        c = p;
      }
    };
    const pop = () => {
      const top = heap[0], last = heap.pop();
      if (heap.length) {
        heap[0] = last;
        let p = 0;
        for (;;) {
          const l = 2 * p + 1, r = l + 1;
          let m = p;
          if (l < heap.length && heap[l][0] < heap[m][0]) m = l;
          if (r < heap.length && heap[r][0] < heap[m][0]) m = r;
          if (m === p) break;
          [heap[p], heap[m]] = [heap[m], heap[p]];
          p = m;
        }
      }
      return top;
    };
    const steps = [[1, 0, 1], [-1, 0, 1], [0, 1, 1], [0, -1, 1]];
    if (diagonal) steps.push([1, 1, Math.SQRT2], [1, -1, Math.SQRT2], [-1, 1, Math.SQRT2], [-1, -1, Math.SQRT2]);

    g[start] = 0;
    push(h(sx, sy), start);
    while (heap.length) {
      const [, cur] = pop();
      if (cur === goal) {
        const path = [];
        for (let i = goal; i !== -1; i = came[i]) path.push([i % W, (i / W) | 0]);
        return path.reverse();
      }
      if (closed[cur]) continue;
      closed[cur] = 1;
      const cx = cur % W, cy = (cur / W) | 0;
      for (const [dx, dy, cost] of steps) {
        const nx = cx + dx, ny = cy + dy;
        if (!free(nx, ny)) continue;
        if (dx && dy && (!free(cx + dx, cy) || !free(cx, cy + dy))) continue; // no corner cutting
        const ni = ny * W + nx;
        const ng = g[cur] + cost;
        if (ng < g[ni]) {
          g[ni] = ng;
          came[ni] = cur;
          push(ng + h(nx, ny), ni);
        }
      }
    }
    return null;
  }

  // ---- Attack tokens: cap how many enemies attack at once so crowds stay fair. ----
  class AttackTokens {
    constructor(max = 2) { this.max = max; this.holders = new Set(); }
    request(agent) {
      if (this.holders.has(agent)) return true;
      if (this.holders.size < this.max) { this.holders.add(agent); return true; }
      return false;
    }
    release(agent) { this.holders.delete(agent); }
    clear() { this.holders.clear(); }
  }

  // ---- Utility AI: pick the action with the highest score. actions: [{ name, score: (ctx) => number }] ----
  function chooseAction(actions, ctx, { rng = null, noise = 0 } = {}) {
    let best = null, bestScore = -Infinity;
    for (const a of actions) {
      const s = a.score(ctx) + (rng && noise ? (rng() - 0.5) * noise : 0);
      if (s > bestScore) { bestScore = s; best = a; }
    }
    return best;
  }

  // ---- Line of sight on a grid (Bresenham). True if no wall cell lies between the two cells. ----
  function lineOfSight(grid, x0, y0, x1, y1) {
    let dx = Math.abs(x1 - x0), dy = -Math.abs(y1 - y0);
    const sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
    let err = dx + dy, x = x0, y = y0;
    for (;;) {
      if ((x !== x0 || y !== y0) && (x !== x1 || y !== y1)) {
        if (x < 0 || y < 0 || x >= grid.w || y >= grid.h || grid.cells[y * grid.w + x] !== 0) return false;
      }
      if (x === x1 && y === y1) return true;
      const e2 = 2 * err;
      if (e2 >= dy) { err += dy; x += sx; }
      if (e2 <= dx) { err += dx; y += sy; }
    }
  }

  const AI = { StateMachine, seek, flee, arrive, wander, separation, limit, normalize, findPath, AttackTokens, chooseAction, lineOfSight };
  if (typeof module !== "undefined" && module.exports) module.exports = AI;
  else root.AI = AI;
})(typeof globalThis !== "undefined" ? globalThis : this);
