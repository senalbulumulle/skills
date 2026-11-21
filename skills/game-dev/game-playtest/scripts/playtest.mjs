#!/usr/bin/env node
// Automated smoke playtest for browser games, using Playwright.
//
// Loads the game, starts it, mashes a deterministic key sequence, restarts several times, and reports
// console errors, uncaught exceptions, frame rate, and (if the game exposes window.__game) state.
//
// Setup (once): copy this file into the game project (Node resolves Playwright from the script's folder),
// then run there:  npm install --no-save playwright-core
// Usage:
//   node playtest.mjs http://localhost:8000/ [--chrome PATH] [--seconds 10] [--keys Space,ArrowLeft,ArrowRight]
//                     [--start Space] [--restart KeyR] [--restarts 3] [--min-fps 50] [--screenshot out.png]
// --chrome: a local Chrome/Chromium executable; omit to use Playwright's own browser (npx playwright install chromium).
// Exit codes: 0 pass, 1 problems found, 2 setup or usage error.

const args = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && i + 1 < args.length ? args[i + 1] : fallback;
};
const url = args[0];
if (!url || url.startsWith("--")) {
  console.error("usage: node playtest.mjs URL [--chrome PATH] [--seconds 10] [--keys K1,K2] [--start Space] " +
                "[--restart KeyR] [--restarts 3] [--min-fps 50] [--screenshot out.png]");
  process.exit(2);
}
const seconds = Number(opt("seconds", "10"));
const keys = opt("keys", "ArrowUp,ArrowDown,ArrowLeft,ArrowRight,Space").split(",");
const startKey = opt("start", "Space");
const restartKey = opt("restart", "KeyR");
const restarts = Number(opt("restarts", "3"));
const minFps = Number(opt("min-fps", "50"));
const screenshot = opt("screenshot", null);
const chromePath = opt("chrome", null);

let chromium;
for (const name of ["playwright", "playwright-core"]) {
  try { ({ chromium } = await import(name)); break; } catch { /* try the next package */ }
}
if (!chromium) {
  console.error("error: Playwright not found. Run: npm install --no-save playwright-core");
  process.exit(2);
}

// Keys use Playwright names: Space, Enter, ArrowLeft, KeyR, Digit1, ...
const problems = [];
const errors = [];
const browser = await chromium.launch(chromePath ? { executablePath: chromePath } : {});
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  page.on("console", (m) => { if (m.type() === "error") errors.push(`console: ${m.text()}`); });
  page.on("pageerror", (e) => errors.push(`exception: ${e.message}`));

  const response = await page.goto(url, { waitUntil: "load" });
  if (!response || !response.ok()) problems.push(`page load failed: HTTP ${response ? response.status() : "no response"}`);

  // Count animation frames from inside the page.
  await page.evaluate(() => {
    window.__playtestFrames = [];
    const tick = (t) => { window.__playtestFrames.push(t); requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  });
  const state = () => page.evaluate(() => {
    const g = window.__game && window.__game.game;
    return g ? { scene: g.scene, score: g.score, time: g.time, paused: g.paused } : null;
  });

  await page.mouse.click(640, 360); // focus the page and count as a user gesture for audio
  await page.keyboard.press(startKey);
  await page.waitForTimeout(300);
  const started = await state();

  // Deterministic mashing: hold each key for a varying, repeatable time.
  const end = Date.now() + seconds * 1000;
  let i = 0;
  while (Date.now() < end) {
    const key = keys[i % keys.length];
    await page.keyboard.down(key);
    await page.waitForTimeout(60 + ((i * 37) % 140));
    await page.keyboard.up(key);
    i++;
  }
  const afterPlay = await state();

  const frames = await page.evaluate(() => window.__playtestFrames.slice());
  const deltas = frames.slice(1).map((t, k) => t - frames[k]).filter((d) => d > 0);
  const avgMs = deltas.reduce((a, b) => a + b, 0) / Math.max(1, deltas.length);
  const fps = avgMs > 0 ? 1000 / avgMs : 0;
  const sorted = deltas.slice().sort((a, b) => a - b);
  const p99 = sorted.length ? sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.99))] : 0;
  if (fps < minFps) problems.push(`average fps ${fps.toFixed(1)} is below ${minFps}`);

  const restartStates = [];
  for (let r = 0; r < restarts; r++) {
    await page.keyboard.press(restartKey);
    await page.waitForTimeout(150);
    restartStates.push(await state());
  }
  if (restartStates[0]) {
    restartStates.forEach((s, r) => {
      if (s.scene !== "play" || s.score !== 0 || s.time > 0.5) {
        problems.push(`restart ${r + 1} did not reset state: ${JSON.stringify(s)}`);
      }
    });
  }

  if (screenshot) await page.screenshot({ path: screenshot });
  problems.push(...errors);

  const report = {
    url,
    pass: problems.length === 0,
    problems,
    fps: Number(fps.toFixed(1)),
    worstFrameMs99: Number(p99.toFixed(1)),
    frames: frames.length,
    keyPresses: i,
    state: { started, afterPlay, restarts: restartStates },
    screenshot,
  };
  console.log(JSON.stringify(report, null, 2));
  process.exitCode = report.pass ? 0 : 1;
} finally {
  await browser.close();
}
