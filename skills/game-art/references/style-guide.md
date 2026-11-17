# Visual style guide

## Palette
- Start from 4-8 colors: one background family (2 values), one per gameplay role, one accent for rewards.
- Separate roles by value (lightness) first and hue second; value is what the eye reads fastest and what survives color blindness.
- Shadows: shift hue toward cool (blue or purple) and lower value, rather than mixing in black. Highlights: shift toward warm and raise value.
- Saturation budget: background low, gameplay objects higher, the single most important thing highest.
- Red-green pairs are the most common color-blind confusion; if two roles differ only in red versus green, change value or shape too.

## Shape language
| Shape | Reads as | Use for |
| --- | --- | --- |
| Circle, soft curves | safe, friendly, collectible | player (in friendly games), pickups, allies |
| Triangle, spikes | danger, speed, aggression | enemies, hazards, projectiles |
| Square, blocks | stable, strong, solid | walls, platforms, tanks, shields |

Exaggerate: make the defining feature large enough to read at the smallest on-screen size.

## Readability
- Test sprites as a solid silhouette; if two characters' silhouettes match, change their shape.
- Keep interactive objects visually distinct from decoration (outline, glow, bob animation, or a consistent color).
- Hazards should read as dangerous before the player touches them.
- Background parallax layers: each farther layer lower contrast and closer to the sky or fog color.

## Pixel art
- Choose a base sprite size (8, 16, or 32 px) and a single scale factor for the whole game.
- Limit colors per sprite (3-5 plus outline).
- Avoid "pillow shading" (shading inward from every edge); pick one light direction.
- Clean lines: no stray single pixels that break a curve ("jaggies"); stair-step lines evenly.
- Render with smoothing off and whole-number scaling, or pixels blur and shimmer.

## Code-drawn art
- Build characters from a few primitives with a shared stroke width and corner radius.
- Use the palette roles directly from a `COLORS` object; never inline hex values in draw code.
- Juice works especially well here: squash and stretch, rotation, and color flashes are free.

## Animation basics
- Anticipation before big actions (crouch before jump, wind-up before strike).
- Follow-through after (overshoot, settle).
- Idle motion keeps characters alive: a 1-2 px bob on a 0.6-1 s loop.
- Frame timing: 8-12 fps is typical for pixel animation; hold key poses longer than in-betweens.

## UI
- Minimum text size about 16 px at 1080p equivalent for body text; larger on mobile.
- HUD in corners and edges, away from the action. Show only what the player acts on.
- Consistent iconography: same stroke width, corner style, and perspective.
- Group UI colors under `ui-` roles so they stay separate from gameplay colors.
