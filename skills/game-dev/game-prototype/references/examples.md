# Taste anchors: prototypes

Each pair shows a default a generator reaches for and a choice that fits a specific game.

## Title screen copy

- **Generic:** `<title>My Game</title>`, a "Start Game" button, and "Welcome to the game!"
- **Specific:** `<title>Tidelock</title>`, a "Cast off" button, and one line of world: "The harbor floods at dawn. Get the ferry out."

## Palette

- **Generic:** `background: linear-gradient(135deg, #667eea 0%, #764ba2 100%)` behind white Inter text.
- **Specific:** three colors from the world (wet slate `#2b3a42`, buoy orange `#ff7a1a`, foam `#e8f1ee`), with the brightest one kept for what the player must notice.

## Tunables

- **Generic:** `speed = 5; // TODO tweak` scattered through the update loop.
- **Specific:** `CONFIG.ferry = { maxSpeed: 220, accel: 900, drag: 0.86 }` in one place, units in pixels per second, so a playtest note maps to one number.
