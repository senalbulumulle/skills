---
name: game-art
description: Give a game a cohesive, readable visual style without an art team, with a limited palette checked for contrast, shape language, silhouettes, visual hierarchy, code-drawn and pixel-art sprites, simple animation, and UI type. Use when a game needs art direction, placeholder or final sprites, a color palette, visual polish, or when it looks inconsistent, muddy, or hard to read.
---

# Game Art

Make the game readable first and beautiful second, with a style small enough to stay consistent.

## Steps

1. **Define the style in a few constraints** and write them to `docs/art-style.md`: three words for the mood, palette size (4-16 colors), resolution or pixel scale, outlines (yes or no, width), light direction, and shape language. Constraints keep code-drawn art consistent.
2. **Build the palette by role.** Name colors by job, not hue: `bg`, `player`, `enemy`, `pickup`, `hazard`, and UI roles prefixed `ui-` or `text`. Then run:
   ```sh
   scripts/palette_check.py bg=#1b1b2f player=#f4d35e enemy=#ee6c4d pickup=#4361ee text=#f5f5f5
   ```
   It checks contrast against the background (3:1 for objects, 4.5:1 for text) and flags gameplay colors that look alike in grayscale. Fix every problem it reports.
3. **Apply shape language.** Friendly things round, dangerous things sharp and angular, solid or stable things square. A player should identify friend or foe from the silhouette alone.
4. **Set the visual hierarchy:** player > threats > interactables > background. Backgrounds get lower contrast and saturation; the player gets the highest contrast. Details from [style-guide.md](references/style-guide.md).
5. **Make the sprites.** Pick one method and keep it for the whole game:
   - Code-drawn shapes (canvas paths, SVG): fastest, scales cleanly.
   - Pixel art from text rows with [pixel-sprite.js](assets/pixel-sprite.js): `parse`, `bake` once, then `drawImage`; `recolor` for variants and hit flashes.
   - Provided image assets: check that their palette and pixel scale match the style constraints.
6. **Animate the essentials**: idle (2-4 frames or a gentle bob), movement, attack with anticipation, hit reaction, death. Motion reads before detail does.
7. **Check readability.** View a screenshot in grayscale (or desaturated) and shrunk to half size. The player, threats, and pickups must still be obvious.

## Rules

- Fewer colors, used consistently, beat many colors used randomly.
- One pixel scale for the whole game; don't mix sizes (no "mixels").
- One font family for the UI (two at most); pixel fonts only at whole-number scales.
- Never rely on color alone for gameplay information; pair it with shape, icon, or motion.

## Done when

- [ ] `docs/art-style.md` records the constraints and the palette with roles.
- [ ] `scripts/palette_check.py` reports 0 problems for the palette.
- [ ] Friend, foe, and pickup are distinguishable in a grayscale, half-size screenshot.
- [ ] Every sprite uses the same method, pixel scale, outline rule, and light direction.
