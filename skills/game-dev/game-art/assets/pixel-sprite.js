// pixel-sprite.js: draw pixel art defined as text rows, with a palette. No dependencies.
// Exposes a global `PixelSprite` in browsers and module.exports in Node (for tests).
//
//   const hero = PixelSprite.parse([
//     "..aa..",
//     ".abba.",
//     "aabbaa",
//     ".a..a.",
//   ], { a: "#f4d35e", b: "#1b1b2f" });           // '.' and ' ' are transparent
//   const img = PixelSprite.bake(hero, 4);           // pre-render once at 4x
//   ctx.drawImage(img, x, y);                        // draw every frame
//
// Keep ctx.imageSmoothingEnabled = false when scaling baked sprites so pixels stay sharp.
(function (root) {
  "use strict";

  function parse(rows, palette) {
    const h = rows.length;
    const w = rows.reduce((m, r) => Math.max(m, r.length), 0);
    for (let y = 0; y < h; y++) {
      for (const ch of rows[y]) {
        if (ch !== "." && ch !== " " && !(ch in palette)) {
          throw new Error(`pixel-sprite: row ${y} uses '${ch}', which is not in the palette`);
        }
      }
    }
    return { rows, palette, w, h };
  }

  // Draw directly: one fillRect per run of same-colored pixels on a row.
  function draw(ctx, sprite, x, y, scale = 1, { flipX = false } = {}) {
    for (let row = 0; row < sprite.h; row++) {
      const line = sprite.rows[row];
      let col = 0;
      while (col < sprite.w) {
        const ch = line[col] || ".";
        let end = col + 1;
        while (end < sprite.w && (line[end] || ".") === ch) end++;
        if (ch !== "." && ch !== " ") {
          const px = flipX ? sprite.w - end : col;
          ctx.fillStyle = sprite.palette[ch];
          ctx.fillRect(x + px * scale, y + row * scale, (end - col) * scale, scale);
        }
        col = end;
      }
    }
  }

  // Pre-render to an offscreen canvas once; drawing an image is much cheaper than many fillRects.
  function bake(sprite, scale = 1, options = {}) {
    const w = sprite.w * scale, h = sprite.h * scale;
    const canvas = typeof OffscreenCanvas !== "undefined"
      ? new OffscreenCanvas(w, h)
      : Object.assign(document.createElement("canvas"), { width: w, height: h });
    draw(canvas.getContext("2d"), sprite, 0, 0, scale, options);
    return canvas;
  }

  // Recolor: same shape, different palette (enemy variants, team colors, hit flash).
  function recolor(sprite, palette) {
    return parse(sprite.rows, { ...sprite.palette, ...palette });
  }

  const PixelSprite = { parse, draw, bake, recolor };
  if (typeof module !== "undefined" && module.exports) module.exports = PixelSprite;
  else root.PixelSprite = PixelSprite;
})(typeof globalThis !== "undefined" ? globalThis : this);
