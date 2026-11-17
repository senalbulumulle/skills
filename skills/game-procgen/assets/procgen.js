// procgen.js: seeded procedural generation helpers. No dependencies.
// Exposes a global `Procgen` in browsers and module.exports in Node (for tests and offline tools).
// Grids are { w, h, cells } with cells a Uint8Array in row-major order: 1 = wall, 0 = floor.
(function (root) {
  "use strict";

  // ---- Seeded RNG (mulberry32) with helpers. Same seed, same sequence. ----
  function makeRng(seed) {
    let a = seed >>> 0;
    const next = () => {
      a = (a + 0x6D2B79F5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
    const rng = {
      next,
      range: (min, max) => min + (max - min) * next(),
      int: (min, max) => Math.floor(min + (max - min + 1) * next()), // inclusive
      chance: (p) => next() < p,
      pick: (list) => list[Math.floor(next() * list.length)],
      // items: [{ weight: 3, ... }, ...]; returns one item, null if total weight is 0.
      weighted(items) {
        let total = 0;
        for (const it of items) total += Math.max(0, it.weight);
        if (total <= 0) return null;
        let r = next() * total;
        for (const it of items) {
          r -= Math.max(0, it.weight);
          if (r < 0) return it;
        }
        return items[items.length - 1];
      },
      shuffle(list) { // in place, Fisher-Yates
        for (let i = list.length - 1; i > 0; i--) {
          const j = Math.floor(next() * (i + 1));
          [list[i], list[j]] = [list[j], list[i]];
        }
        return list;
      },
      // Independent child generator for one subsystem, so adding rolls elsewhere doesn't change it.
      fork: (salt) => makeRng((Math.floor(next() * 4294967296) ^ Math.imul(salt >>> 0, 0x9E3779B1)) >>> 0),
    };
    return rng;
  }

  // ---- 2D value noise in [0, 1) and fractal Brownian motion ----
  function makeNoise2D(seed) {
    const rng = makeRng(seed);
    const p = rng.shuffle(Array.from({ length: 256 }, (_, i) => i));
    const perm = new Uint8Array(512);
    for (let i = 0; i < 512; i++) perm[i] = p[i & 255];
    const values = Float32Array.from({ length: 256 }, () => rng.next());
    const lattice = (ix, iy) => values[perm[perm[ix & 255] + (iy & 255)]];
    const smooth = (t) => t * t * (3 - 2 * t);
    return function noise(x, y) {
      const x0 = Math.floor(x), y0 = Math.floor(y);
      const sx = smooth(x - x0), sy = smooth(y - y0);
      const top = lattice(x0, y0) + (lattice(x0 + 1, y0) - lattice(x0, y0)) * sx;
      const bottom = lattice(x0, y0 + 1) + (lattice(x0 + 1, y0 + 1) - lattice(x0, y0 + 1)) * sx;
      return top + (bottom - top) * sy;
    };
  }

  // Layered noise: octaves add detail; result stays in [0, 1).
  function fbm(noise, x, y, { octaves = 5, lacunarity = 2, gain = 0.5 } = {}) {
    let sum = 0, amp = 1, freq = 1, norm = 0;
    for (let i = 0; i < octaves; i++) {
      sum += amp * noise(x * freq, y * freq);
      norm += amp;
      amp *= gain;
      freq *= lacunarity;
    }
    return sum / norm;
  }

  // ---- Grid helpers ----
  function makeGrid(w, h, fill = 1) {
    return { w, h, cells: new Uint8Array(w * h).fill(fill) };
  }
  const idx = (g, x, y) => y * g.w + x;
  const get = (g, x, y) => (x < 0 || y < 0 || x >= g.w || y >= g.h ? 1 : g.cells[idx(g, x, y)]); // outside = wall

  // ---- Caves with cellular automata (wall stays with ≥ survive wall neighbours; floor turns wall with ≥ birth) ----
  function caves(w, h, rng, { fill = 0.45, steps = 5, birth = 5, survive = 4 } = {}) {
    let g = makeGrid(w, h, 1);
    for (let y = 1; y < h - 1; y++) for (let x = 1; x < w - 1; x++) g.cells[idx(g, x, y)] = rng.chance(fill) ? 1 : 0;
    for (let s = 0; s < steps; s++) {
      const next = makeGrid(w, h, 1);
      for (let y = 1; y < h - 1; y++) {
        for (let x = 1; x < w - 1; x++) {
          let n = 0;
          for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) if (dx || dy) n += get(g, x + dx, y + dy);
          const wall = get(g, x, y) === 1;
          next.cells[idx(next, x, y)] = (wall && n >= survive) || (!wall && n >= birth) ? 1 : 0;
        }
      }
      g = next;
    }
    return g;
  }

  // ---- Connected floor regions (4-way). Returns arrays of cell indices, largest first. ----
  function regions(g) {
    const seen = new Uint8Array(g.w * g.h);
    const out = [];
    for (let start = 0; start < g.cells.length; start++) {
      if (g.cells[start] !== 0 || seen[start]) continue;
      const region = [];
      const stack = [start];
      seen[start] = 1;
      while (stack.length) {
        const i = stack.pop();
        region.push(i);
        const x = i % g.w, y = (i - x) / g.w;
        for (const [nx, ny] of [[x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1]]) {
          if (get(g, nx, ny) !== 0) continue;
          const j = idx(g, nx, ny);
          if (!seen[j]) { seen[j] = 1; stack.push(j); }
        }
      }
      out.push(region);
    }
    return out.sort((a, b) => b.length - a.length);
  }

  // Fill every floor region except the largest, guaranteeing one connected space. Returns the largest region.
  function keepLargestRegion(g) {
    const all = regions(g);
    for (let r = 1; r < all.length; r++) for (const i of all[r]) g.cells[i] = 1;
    return all[0] || [];
  }

  // ---- Rooms and corridors: non-overlapping rooms joined in a chain by L-shaped corridors ----
  function rooms(w, h, rng, { count = 12, minSize = 4, maxSize = 9, tries = 300 } = {}) {
    const g = makeGrid(w, h, 1);
    const list = [];
    for (let t = 0; t < tries && list.length < count; t++) {
      const rw = rng.int(minSize, maxSize), rh = rng.int(minSize, maxSize);
      if (rw > w - 2 || rh > h - 2) continue;
      const r = { x: rng.int(1, w - rw - 1), y: rng.int(1, h - rh - 1), w: rw, h: rh };
      // Keep a one-tile wall between rooms.
      if (list.some((o) => r.x - 1 < o.x + o.w && r.x + r.w + 1 > o.x && r.y - 1 < o.y + o.h && r.y + r.h + 1 > o.y)) continue;
      list.push(r);
    }
    for (const r of list) {
      r.cx = r.x + Math.floor(r.w / 2);
      r.cy = r.y + Math.floor(r.h / 2);
      for (let y = r.y; y < r.y + r.h; y++) for (let x = r.x; x < r.x + r.w; x++) g.cells[idx(g, x, y)] = 0;
    }
    list.sort((a, b) => a.cx - b.cx); // left to right keeps corridors from crossing the whole map
    const carveH = (x1, x2, y) => { for (let x = Math.min(x1, x2); x <= Math.max(x1, x2); x++) g.cells[idx(g, x, y)] = 0; };
    const carveV = (y1, y2, x) => { for (let y = Math.min(y1, y2); y <= Math.max(y1, y2); y++) g.cells[idx(g, x, y)] = 0; };
    for (let i = 1; i < list.length; i++) {
      const a = list[i - 1], b = list[i];
      if (rng.chance(0.5)) { carveH(a.cx, b.cx, a.cy); carveV(a.cy, b.cy, b.cx); }
      else { carveV(a.cy, b.cy, a.cx); carveH(a.cx, b.cx, b.cy); }
    }
    return { grid: g, rooms: list };
  }

  // ---- Poisson disk sampling: evenly spread points at least `radius` apart (Bridson's algorithm) ----
  function poissonDisk(w, h, radius, rng, k = 30) {
    const cell = radius / Math.SQRT2;
    const gw = Math.ceil(w / cell), gh = Math.ceil(h / cell);
    const grid = new Int32Array(gw * gh).fill(-1);
    const points = [], active = [];
    const add = (x, y) => {
      points.push([x, y]);
      active.push(points.length - 1);
      grid[Math.floor(y / cell) * gw + Math.floor(x / cell)] = points.length - 1;
    };
    const fits = (x, y) => {
      if (x < 0 || y < 0 || x >= w || y >= h) return false;
      const gx = Math.floor(x / cell), gy = Math.floor(y / cell);
      for (let yy = Math.max(0, gy - 2); yy <= Math.min(gh - 1, gy + 2); yy++) {
        for (let xx = Math.max(0, gx - 2); xx <= Math.min(gw - 1, gx + 2); xx++) {
          const i = grid[yy * gw + xx];
          if (i >= 0) {
            const dx = points[i][0] - x, dy = points[i][1] - y;
            if (dx * dx + dy * dy < radius * radius) return false;
          }
        }
      }
      return true;
    };
    add(rng.range(0, w), rng.range(0, h));
    while (active.length) {
      const a = Math.floor(rng.next() * active.length);
      const [px, py] = points[active[a]];
      let placed = false;
      for (let i = 0; i < k; i++) {
        const ang = rng.range(0, Math.PI * 2), dist = rng.range(radius, radius * 2);
        const x = px + Math.cos(ang) * dist, y = py + Math.sin(ang) * dist;
        if (fits(x, y)) { add(x, y); placed = true; break; }
      }
      if (!placed) active.splice(a, 1);
    }
    return points;
  }

  // Render a grid as text for logs and tests ('#' wall, '.' floor).
  function toText(g) {
    let s = "";
    for (let y = 0; y < g.h; y++) {
      for (let x = 0; x < g.w; x++) s += g.cells[idx(g, x, y)] ? "#" : ".";
      s += "\n";
    }
    return s;
  }

  const Procgen = { makeRng, makeNoise2D, fbm, makeGrid, get, caves, regions, keepLargestRegion, rooms, poissonDisk, toText };
  if (typeof module !== "undefined" && module.exports) module.exports = Procgen;
  else root.Procgen = Procgen;
})(typeof globalThis !== "undefined" ? globalThis : this);
