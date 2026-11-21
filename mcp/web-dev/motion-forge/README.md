# motion-forge MCP server

Reusable Web Components for motion-rich web UI, and checks for the motion code around them. Each component is one dependency-free ES module that works in plain HTML, React, Vue, Svelte, and Angular. Each one handles `prefers-reduced-motion`, pauses offscreen, animates only compositor-friendly properties, and removes its listeners when it leaves the page.

| Component | Category | What it does |
| --- | --- | --- |
| `<mf-shader-gradient>` | WebGL and 3D | Slow, domain-warped WebGL color field for hero backgrounds; bends away from the pointer, falls back to a CSS gradient |
| `<mf-tilt-card>` | WebGL and 3D | Card that tilts toward the pointer on a spring, with a glare and inner layers that rise toward the viewer |
| `<mf-parallax>` | Scroll and motion graphics | Layered scroll parallax; each layer moves at its own `data-speed` |
| `<mf-scroll-scene>` | Scroll and motion graphics | Pinned, scroll-scrubbed stage; CSS reads `--mf-progress` and each part's own `--mf-p` |
| `<mf-reveal>` | Scroll and motion graphics | Staggered reveal of children on scroll: rise, fade, scale, blur, or clip |
| `<mf-magnetic>` | Tactile and micro-interactions | Pulls a button toward a nearby pointer and presses it in on click |
| `<mf-spotlight>` | Tactile and micro-interactions | One light follows the pointer across a group of cards, lighting borders and surfaces |
| `<mf-text-scramble>` | Expressive hero and text | Text decodes from shuffling glyphs into its real words |
| `<mf-split-text>` | Expressive hero and text | Headline letters or words rise, fade, or unblur into place one after another |

| Tool | What it does | Changes files? |
| --- | --- | --- |
| `list_components` | Lists the components, optionally for one category | no |
| `get_component` | A component's attributes, CSS custom properties, data attributes, API, notes, example markup, framework notes, and source | no |
| `install_components` | Copies component modules into a project folder; leaves a different existing file alone unless told to overwrite | yes, the output folder |
| `build_showcase` | Writes a self-contained, offline HTML page that demonstrates the chosen components next to their markup | yes, the output file (only a page it wrote before) |
| `audit_motion` | Scans CSS, HTML, JS/TS, Vue, Svelte, and Astro for motion problems: no reduced-motion handling, layout-property transitions and keyframes, `transition: all`, scroll-blocking wheel and touch listeners, animation loops that never stop, WebGL without context-loss handling or with an uncapped pixel ratio, hover effects with no focus style, `will-change` overuse, and layout writes in animation code (heuristic) | no |

Using a component:

```html
<script type="module" src="./components/split-text.js"></script>
<h1><mf-split-text>The sky is moving tonight</mf-split-text></h1>
```

## Requirements

- [uv](https://docs.astral.sh/uv/). On first launch it installs Python 3.10+ (if needed) and the pinned MCP SDK (`mcp==2.3.0`) from the script header.
- The components need a browser with Custom Elements, Shadow DOM, and the CSS `translate` and `scale` properties (Chrome 104, Safari 14.1, Firefox 78, or later).

Use absolute paths in tool calls. Replace `/path/to/skills` below with this repository's location.

## Claude Code

```sh
claude mcp add --scope user motion-forge -- uv run --quiet --script /path/to/skills/mcp/web-dev/motion-forge/server.py
```

## Codex

```sh
scripts/codex/install-codex-mcp.sh   # registers this repo's servers and downloads the SDK ahead of the first session
```

Or by hand:
```sh
codex mcp add motion-forge -- uv run --quiet --script /path/to/skills/mcp/web-dev/motion-forge/server.py
```
Check with `codex mcp list`, or `/mcp` inside a session.

## Gemini CLI

Add the server to `~/.gemini/settings.json` (all projects) or `.gemini/settings.json` (one project):

```json
{
  "mcpServers": {
    "motion-forge": {
      "command": "uv",
      "args": ["run", "--quiet", "--script", "/path/to/skills/mcp/web-dev/motion-forge/server.py"],
      "timeout": 60000
    }
  }
}
```
Check with `/mcp` inside a session.

## Development

- Tool logic lives in `motion.py` (standard library only); `server.py` only registers tools.
- Components live in `components/`, their metadata in `catalog.json`, and their example markup in `examples/`. A component's exported helper functions are pure, so Node can test them without a browser.
- Tests: `python3 -m unittest tools/test_motion_forge.py` (catalog and tool logic),
  `node --test tools/test_motion_components.test.mjs` (component helpers), and
  `uv run --python 3.12 --with mcp==2.3.0 python tools/mcp_smoke.py` (real stdio session).
