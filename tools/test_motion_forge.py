"""Tests for mcp/motion-forge/motion.py (catalog and tool logic; the MCP transport is covered by tools/mcp_smoke.py,
the components' JavaScript helpers by tools/test_motion_components.test.mjs).

Run: python3 -m unittest tools/test_motion_forge.py
"""
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FORGE = REPO / "mcp" / "motion-forge"
sys.path.insert(0, str(FORGE))
sys.path.insert(0, str(REPO / "mcp" / "creative-director"))
import director  # noqa: E402
import motion  # noqa: E402

CATALOG = json.loads((FORGE / "catalog.json").read_text())


class Catalog(unittest.TestCase):
    def test_every_component_file_has_one_entry(self):
        names = [c["name"] for c in CATALOG["components"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(sorted(names), sorted(p.stem for p in (FORGE / "components").glob("*.js")))
        self.assertEqual(sorted(names), sorted(p.stem for p in (FORGE / "examples").glob("*.html")))

    def test_entries_match_their_source(self):
        for c in CATALOG["components"]:
            with self.subTest(c["name"]):
                source = (FORGE / "components" / f"{c['name']}.js").read_text()
                example = (FORGE / "examples" / f"{c['name']}.html").read_text()
                self.assertIn(f'const TAG = "{c["tag"]}";', source)
                self.assertTrue(c["tag"].startswith("mf-"))
                self.assertIn(f"<{c['tag']}", example)
                self.assertIn(c["category"], CATALOG["categories"])
                self.assertIn("prefers-reduced-motion", source)
                self.assertIn("customElements.get(TAG)", source)
                for attr in c["attributes"]:  # read by getAttribute("x") or by a CSS [x] selector
                    self.assertTrue(f'"{attr["name"]}"' in source or f"[{attr['name']}" in source,
                                    f"attribute {attr['name']} is never read")
                for var in c["css"]:
                    self.assertTrue(var["name"] in source, f"CSS property {var['name']} is never used")
                for data in c["data"]:
                    self.assertTrue(data["name"] in source, f"{data['name']} is never read")

    def test_observed_attributes_are_documented(self):
        for c in CATALOG["components"]:
            source = (FORGE / "components" / f"{c['name']}.js").read_text()
            m = re.search(r"static observedAttributes = \[([^\]]*)\]", source)
            observed = re.findall(r'"([^"]+)"', m.group(1)) if m else []
            self.assertLessEqual(set(observed), {a["name"] for a in c["attributes"]}, c["name"])

    def test_every_category_has_a_component(self):
        self.assertEqual({c["category"] for c in CATALOG["components"]}, set(CATALOG["categories"]))


class Tools(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_list_components(self):
        everything = motion.list_components()
        self.assertTrue(everything["ok"])
        self.assertEqual(len(everything["components"]), len(CATALOG["components"]))
        tactile = motion.list_components("tactile")
        self.assertEqual({c["name"] for c in tactile["components"]}, {"magnetic", "spotlight"})
        self.assertFalse(motion.list_components("3d")["ok"])

    def test_get_component(self):
        c = motion.get_component("scroll-scene")
        self.assertTrue(c["ok"])
        self.assertIn("mf-scroll-scene", c["example"])
        self.assertIn("class ScrollScene", c["source"])
        self.assertNotIn("source", motion.get_component("scroll-scene", include_source=False))
        missing = motion.get_component("tilt")
        self.assertFalse(missing["ok"])
        self.assertIn("tilt-card", missing["error"])

    def test_install_components(self):
        out = self.tmp / "web" / "motion"
        first = motion.install_components(["reveal", "magnetic"], str(out))
        self.assertTrue(first["ok"])
        self.assertEqual([f["status"] for f in first["files"]], ["written", "written"])
        self.assertEqual((out / "reveal.js").read_text(), (FORGE / "components" / "reveal.js").read_text())
        self.assertEqual([f["status"] for f in motion.install_components(["reveal"], str(out))["files"]], ["unchanged"])
        (out / "reveal.js").write_text("// edited\n")
        kept = motion.install_components(["reveal"], str(out))
        self.assertFalse(kept["ok"])
        self.assertEqual((out / "reveal.js").read_text(), "// edited\n")
        replaced = motion.install_components(["reveal"], str(out), overwrite=True)
        self.assertEqual(replaced["files"][0]["status"], "replaced")
        self.assertEqual(len(motion.install_components(["all"], str(self.tmp / "all"))["files"]), len(CATALOG["components"]))
        self.assertFalse(motion.install_components([], str(out))["ok"])
        self.assertFalse(motion.install_components(["reveal", "nope"], str(self.tmp / "none"))["ok"])
        self.assertFalse((self.tmp / "none").exists())
        (self.tmp / "file").write_text("x")
        self.assertFalse(motion.install_components(["reveal"], str(self.tmp / "file"))["ok"])

    def test_build_showcase(self):
        built = motion.build_showcase(str(self.tmp))
        self.assertTrue(built["ok"] and built["hero"])
        page = Path(built["path"]).read_text()
        self.assertEqual(Path(built["path"]).name, motion.SHOWCASE_NAME)
        self.assertIn(motion.SHOWCASE_MARK, page)
        self.assertEqual(page.count('<script type="module">'), len(CATALOG["components"]))
        self.assertEqual(page.count("</script"), len(CATALOG["components"]))
        for c in CATALOG["components"]:
            self.assertIn(f'id="{c["name"]}"', page)
        self.assertTrue(motion.audit_motion([built["path"]])["ok"])

        partial = motion.build_showcase(str(self.tmp / "two.html"), ["parallax", "reveal"])
        self.assertFalse(partial["hero"])
        page = Path(partial["path"]).read_text()
        self.assertEqual(page.count('<script type="module">'), 2)
        self.assertNotIn("mf-shader-gradient", page)
        self.assertTrue(motion.build_showcase(str(self.tmp / "two.html"), ["reveal"])["ok"])  # its own page

        (self.tmp / "index.html").write_text("<p>mine</p>")
        refused = motion.build_showcase(str(self.tmp / "index.html"))
        self.assertFalse(refused["ok"])
        self.assertEqual((self.tmp / "index.html").read_text(), "<p>mine</p>")
        self.assertFalse(motion.build_showcase(str(self.tmp), ["nope"])["ok"])


class Audit(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def audit(self, files: dict[str, str]) -> dict:
        root = Path(tempfile.mkdtemp(dir=self.tmp))  # a fresh project per call
        for name, text in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        return motion.audit_motion([str(root)])

    def rules(self, files: dict[str, str]) -> list[str]:
        return [f["rule"] for f in self.audit(files)["findings"]]

    REDUCED = "@media (prefers-reduced-motion: reduce) { * { animation: none; } }\n"

    def test_components_pass_their_own_audit(self):
        result = motion.audit_motion([str(FORGE / "components")])
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["files"], len(CATALOG["components"]))

    def test_reduced_motion_is_project_wide(self):
        motion_css = ".a { animation: spin 2s infinite; }\n"
        result = self.audit({"a.css": motion_css})
        self.assertFalse(result["ok"])
        self.assertEqual([(f["rule"], f["where"]) for f in result["findings"]], [("reduced-motion", "a.css:1")])
        self.assertEqual(self.rules({"b.css": self.REDUCED}), [])
        self.assertEqual(self.rules({"plain.css": ".a { transition: color .2s; }\n"}), [])

    def test_layout_transitions_and_keyframes(self):
        css = self.REDUCED + (".a { transition: width .3s, opacity .2s; }\n.b { transition: all .2s; }\n"
                              "@keyframes grow { from { height: 0; } to { height: 10px; transform: scale(1); } }\n"
                              ".c { transition: transform .2s, opacity .2s; }\n")
        result = self.audit({"a.css": css})
        self.assertEqual([(f["rule"], f["where"]) for f in result["findings"]],
                         [("layout-transition", "a.css:2"), ("transition-all", "a.css:3"),
                          ("layout-keyframes", "a.css:4"), ("layout-keyframes", "a.css:4")])
        self.assertEqual(self.rules({"b.js": 'el.style.transition = "transform .2s";\nconst t = { transition: { duration: .3 } };\n'}), [])
        self.assertEqual(self.rules({"c.jsx": "const s = { transition: 'height 200ms' };\n"}), ["layout-transition"])

    def test_scroll_listeners(self):
        js = ('addEventListener("wheel", onWheel);\n'
              'addEventListener("touchmove", onMove, { passive: false });\n'
              'addEventListener("touchstart", onStart, { passive: true });\n')
        self.assertEqual(sorted(self.rules({"a.js": js})), ["non-passive-listener", "scroll-jacking"])
        self.assertEqual(self.rules({"b.js": 'window.addEventListener("scroll", () => { el.classList.add("x"); });\n'}),
                         ["unthrottled-scroll"])
        throttled = ('window.addEventListener("scroll", () => { raf = requestAnimationFrame(update); }, { passive: true });\n'
                     "cancelAnimationFrame(raf);\n")
        self.assertEqual(self.rules({"c.js": throttled, "d.css": self.REDUCED}), [])

    def test_animation_loops(self):
        loop = self.REDUCED.replace("@media", "/* @media") + "*/\nfunction tick() { draw(); requestAnimationFrame(tick); }\n"
        self.assertIn("endless-loop", self.rules({"a.js": loop}))
        stoppable = "const id = requestAnimationFrame(tick);\ncancelAnimationFrame(id);\n// prefers-reduced-motion handled in css\n"
        self.assertEqual(self.rules({"b.js": stoppable, "c.css": self.REDUCED}), [])

    def test_webgl(self):
        gl = ('const gl = canvas.getContext("webgl2");\ncanvas.width = innerWidth * devicePixelRatio;\n')
        self.assertEqual(sorted(self.rules({"a.js": gl})), ["uncapped-dpr", "webgl-context-loss"])
        ok = ('const gl = canvas.getContext("webgl");\ncanvas.addEventListener("webglcontextlost", (e) => e.preventDefault());\n'
              "const dpr = Math.min(devicePixelRatio, 2);\n")
        self.assertEqual(self.rules({"b.js": ok}), [])
        self.assertEqual(self.rules({"c.js": "renderer.setPixelRatio(window.devicePixelRatio);\n"}), ["uncapped-dpr"])
        self.assertEqual(self.rules({"d.js": "const scale = window.devicePixelRatio;\n"}), [])

    def test_hover_focus_and_will_change(self):
        self.assertEqual(self.rules({"a.css": ".btn:hover { color: red; }\n"}), ["hover-only"])
        self.assertEqual(self.rules({"b.css": ".btn:hover, .btn:focus-visible { color: red; }\n"}), [])
        self.assertEqual(self.rules({"c.css": "@media (hover: hover) { .x { color: red; } }\n"}), [])
        self.assertEqual(self.rules({"d.css": "* { will-change: transform; }\n"}), ["will-change-overuse"])
        many = "".join(f".a{i} {{ will-change: opacity; }}\n" for i in range(9))
        self.assertEqual(self.rules({"e.css": many}), ["will-change-overuse"])

    def test_layout_writes_in_animation_code(self):
        js = "function tick() { el.style.left = x + 'px'; id = requestAnimationFrame(tick); }\ncancelAnimationFrame(id);\n"
        self.assertEqual(self.rules({"a.js": js, "b.css": self.REDUCED}), ["layout-write"])
        self.assertEqual(self.rules({"c.js": "el.style.width = '10px';\n"}), [])

    def test_comments_and_skipped_folders(self):
        css = "/* transition: all 1s; */\n<!-- -->\n"
        self.assertEqual(self.rules({"a.css": css}), [])
        js = '// addEventListener("wheel", f);\nconst url = "https://example.com";\n'
        self.assertEqual(self.rules({"b.js": js}), [])
        self.assertEqual(self.rules({"node_modules/x/a.css": ".a { transition: all 1s; }\n",
                                     "dist/a.css": ".a { transition: all 1s; }\n",
                                     "lib.min.js": 'addEventListener("wheel", f);\n'}), [])
        self.assertFalse(motion.audit_motion([str(self.tmp / "missing")])["ok"])

    def test_finding_shape(self):
        finding = self.audit({"a.css": self.REDUCED + ".b { transition: all .2s; }\n"})["findings"][0]
        self.assertEqual(set(finding), {"severity", "rule", "where", "issue", "fix"})
        self.assertEqual(finding["severity"], "warn")


class Slop(unittest.TestCase):
    def test_no_unfinished_or_generic_content(self):
        self.assertEqual(director.find_slop([str(FORGE)])["findings"], [])


if __name__ == "__main__":
    unittest.main()
