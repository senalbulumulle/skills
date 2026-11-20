#!/usr/bin/env python3
"""Build roblox-forge's catalog of effect, sound, and UI classes from a local Roblox Studio install.

  studio_catalog.py                 read /Applications/RobloxStudio.app and rewrite catalog.json and
                                    skills/roblox-gameplay/references/effects-catalog.md
  studio_catalog.py --studio PATH   read another install: RobloxStudio.app, or a folder that holds
                                    ReflectionMetadata.xml and content/
  studio_catalog.py --check         exit 1 if the committed files differ from what the install gives

Sources: member names from content/api_docs/en-us.json, editor ranges and deprecations from
ReflectionMetadata.xml, and the file lists of content/textures/particles and content/sounds. Only names,
numbers, and paths are kept (no documentation text, no asset files), so the output can be committed.
Run it again after a Studio update. Standard library only, Python 3.9+.
"""
from __future__ import annotations

import argparse
import json
import plistlib
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CATALOG = HERE / "catalog.json"
REFERENCE = REPO / "skills" / "roblox-gameplay" / "references" / "effects-catalog.md"
DEFAULT_STUDIO = Path("/Applications/RobloxStudio.app")

# The API docs list each class's own members only, so the inheritance chain is written out here.
# extract() fails if a class is missing from the docs; tools/test_roblox_forge.py checks that the template's
# UI code resolves through these parents.
PARENTS = {
    "Instance": None,
    "Attachment": "Instance", "Beam": "Instance", "Trail": "Instance", "ParticleEmitter": "Instance",
    "Highlight": "Instance", "Sound": "Instance", "SoundGroup": "Instance", "Folder": "Instance",
    "Light": "Instance", "PointLight": "Light", "SpotLight": "Light", "SurfaceLight": "Light",
    "GuiBase": "Instance", "GuiBase2d": "GuiBase", "GuiObject": "GuiBase2d", "LayerCollector": "GuiBase2d",
    "ScreenGui": "LayerCollector", "BillboardGui": "LayerCollector", "SurfaceGuiBase": "LayerCollector",
    "SurfaceGui": "SurfaceGuiBase",
    "Frame": "GuiObject", "ScrollingFrame": "GuiObject", "TextBox": "GuiObject", "ViewportFrame": "GuiObject",
    "CanvasGroup": "GuiObject", "GuiLabel": "GuiObject", "TextLabel": "GuiLabel", "ImageLabel": "GuiLabel",
    "GuiButton": "GuiObject", "TextButton": "GuiButton", "ImageButton": "GuiButton",
    "UIBase": "Instance", "UIComponent": "UIBase", "UIConstraint": "UIComponent",
    "UIAspectRatioConstraint": "UIConstraint", "UISizeConstraint": "UIConstraint",
    "UITextSizeConstraint": "UIConstraint", "UILayout": "UIComponent", "UIGridStyleLayout": "UILayout",
    "UIListLayout": "UIGridStyleLayout", "UIGridLayout": "UIGridStyleLayout", "UICorner": "UIComponent",
    "UIStroke": "UIComponent", "UIGradient": "UIComponent", "UIScale": "UIComponent", "UIPadding": "UIComponent",
    "UIFlexItem": "UIComponent",
}
# Classes whose editor ranges go into the skill reference.
EFFECT_CLASSES = ("ParticleEmitter", "Beam", "Trail", "Highlight", "PointLight", "SpotLight", "Sound", "UIStroke",
                  "UIGradient")
ASSET_DIRS = {"particle_textures": "textures/particles", "sounds": "sounds"}


def resources(studio: Path) -> Path:
    """The folder that holds ReflectionMetadata.xml and content/."""
    for candidate in (studio / "Contents" / "Resources", studio):
        if (candidate / "ReflectionMetadata.xml").is_file():
            return candidate
    raise SystemExit(f"no ReflectionMetadata.xml under {studio}: pass --studio with a Roblox Studio install")


def studio_version(studio: Path, res: Path) -> str:
    plist = studio / "Contents" / "Info.plist"
    if plist.is_file():
        with plist.open("rb") as f:
            version = plistlib.load(f).get("CFBundleShortVersionString")
        if isinstance(version, str):
            return version
    return res.name if res.name.startswith("version-") else "unknown"


def _fields(item: ET.Element) -> dict:
    props = item.find("Properties")
    return {p.get("name"): (p.text or "") for p in (props if props is not None else [])}


def _metadata(path: Path) -> dict:
    """{class: {"deprecated": bool, "members": {name: {"min", "max", "deprecated"}}}} from ReflectionMetadata."""
    out = {}
    for cls in ET.parse(path).getroot().iter("Item"):
        if cls.get("class") != "ReflectionMetadataClass":
            continue
        fields = _fields(cls)
        members = {}
        for group in cls.findall("Item"):
            for member in group.findall("Item"):
                if member.get("class") != "ReflectionMetadataMember":
                    continue
                f = _fields(member)
                if f.get("Name"):
                    members[f["Name"]] = {"min": f.get("UIMinimum"), "max": f.get("UIMaximum"),
                                          "deprecated": f.get("Deprecated") == "true"}
        out[fields.get("Name")] = {"deprecated": fields.get("Deprecated") == "true", "members": members}
    return out


def _number(text: str | None) -> float | int | None:
    if text is None or text == "":
        return None
    value = float(text)
    return int(value) if value.is_integer() else value


def extract(studio: Path) -> dict:
    res = resources(studio)
    docs = json.loads((res / "content" / "api_docs" / "en-us.json").read_text(encoding="utf-8"))
    meta = _metadata(res / "ReflectionMetadata.xml")
    # A class entry's "keys" lists properties and methods; events only have their own entries
    # ("@roblox/globaltype/GuiButton.Activated"), so collect member names from both.
    own: dict[str, set] = {}
    for key in docs:
        if key.startswith("@roblox/globaltype/"):
            cls, _, rest = key[len("@roblox/globaltype/"):].partition(".")
            if cls in PARENTS and rest:
                own.setdefault(cls, set()).add(rest.split(".")[0].split("/")[0])
    classes = {}
    for name, parent in PARENTS.items():
        entry = docs.get(f"@roblox/globaltype/{name}")
        if not isinstance(entry, dict):
            raise SystemExit(f"{name} is not in this Studio's API docs: update PARENTS in {Path(__file__).name}")
        info = meta.get(name, {"members": {}})
        ranges = {m: [_number(v["min"]), _number(v["max"])] for m, v in sorted(info["members"].items())
                  if v["min"] not in (None, "") and v["max"] not in (None, "")}
        members = own.get(name, set()) | set(entry.get("keys", {}))
        classes[name] = {"parent": parent, "members": sorted(members), "ranges": ranges,
                         "deprecated": sorted(m for m, v in info["members"].items() if v["deprecated"])}
    assets = {}
    for key, rel in ASSET_DIRS.items():
        folder = res / "content" / rel
        assets[key] = sorted(f"rbxasset://{rel}/{f.name}" for f in folder.iterdir() if f.is_file()) \
            if folder.is_dir() else []
    return {"studio_version": studio_version(studio, res),
            "source": "Generated by mcp/roblox-forge/studio_catalog.py from a Roblox Studio install: member names "
                      "(content/api_docs), editor ranges and deprecations (ReflectionMetadata.xml), built-in file "
                      "paths (content/). Names, numbers, and paths only.",
            "classes": classes, "builtin_assets": assets}


def _fmt(n: float | int | None) -> str:
    return "?" if n is None else str(n)


def reference(catalog: dict) -> str:
    lines = [
        "# Effects catalog",
        "",
        f"Generated from Roblox Studio {catalog['studio_version']} by `mcp/roblox-forge/studio_catalog.py`; "
        "don't edit by hand.",
        "",
        "## Built-in files",
        "",
        "These ship with Roblox, so they load without an upload. Use them as starting points, then replace them "
        "with your own uploads or Creator Store assets that fit the game.",
        "",
    ]
    for key, label in (("particle_textures", "Particle textures (`ParticleEmitter.Texture`)"),
                       ("sounds", "Sounds (`Sound.SoundId`)")):
        lines += [f"{label}:", ""] + [f"- `{a}`" for a in catalog["builtin_assets"][key]] + [""]
    lines += [
        "## Editor ranges",
        "",
        "The slider range Studio's Properties window offers. Values outside it may be allowed, but rarely look "
        "right.",
        "",
        "| Class | Property | Range |",
        "|---|---|---|",
    ]
    for cls in EFFECT_CLASSES:
        for prop, (lo, hi) in catalog["classes"][cls]["ranges"].items():
            lines.append(f"| {cls} | {prop} | {_fmt(lo)} to {_fmt(hi)} |")
    deprecated = [f"{cls}.{m}" for cls in EFFECT_CLASSES for m in catalog["classes"][cls]["deprecated"]]
    if deprecated:
        lines += ["", "## Deprecated, don't use", "", ", ".join(f"`{d}`" for d in deprecated)]
    return "\n".join(lines) + "\n"


def outputs(catalog: dict) -> dict[Path, str]:
    return {CATALOG: json.dumps(catalog, indent=1, sort_keys=True) + "\n", REFERENCE: reference(catalog)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--studio", type=Path, default=DEFAULT_STUDIO, help="Roblox Studio install to read")
    parser.add_argument("--check", action="store_true", help="compare instead of writing")
    args = parser.parse_args(argv)
    catalog = extract(args.studio.expanduser())
    stale = []
    for path, text in outputs(catalog).items():
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == text:
            continue
        if args.check:
            stale.append(path)
        else:
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path.relative_to(REPO)}")
    if stale:
        print("out of date: " + ", ".join(str(p.relative_to(REPO)) for p in stale), file=sys.stderr)
        return 1
    print(f"catalog matches Roblox Studio {catalog['studio_version']}" if args.check
          else f"catalog from Roblox Studio {catalog['studio_version']}: {len(catalog['classes'])} classes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
