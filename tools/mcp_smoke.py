"""End-to-end smoke test for this repo's MCP servers over stdio, using the official MCP client.

Run: uv run --python 3.12 --with mcp==2.3.0 python tools/mcp_smoke.py
Exits non-zero on any failure.
"""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

MCP = Path(__file__).resolve().parent.parent / "mcp"
SERVER = MCP / "roblox-forge" / "server.py"
EXPECTED = {"create_project", "check_project", "map_remotes", "audit_remotes", "audit_feel", "audit_polish",
            "vfx_recipe", "review_story", "build_dialogue", "export_voiceover", "export_localization", "check_odds",
            "datastore_budget", "luau_check"}
EXAMPLE_DOCS = MCP.parent / "skills" / "roblox-narrative" / "assets" / "example" / "docs"
DIRECTOR = MCP / "creative-director" / "server.py"
DIRECTOR_TOOLS = {"concept_seeds", "review_design", "find_slop"}


def payload(result):
    if result.is_error:
        raise AssertionError(f"tool error: {result.content}")
    if result.structured_content is not None:
        data = result.structured_content
        return data.get("result", data) if set(data) == {"result"} else data
    return json.loads(result.content[0].text)


def launch(server: Path) -> StdioServerParameters:
    # Launch exactly the way users register it: uv resolves Python and the pinned SDK from the script header.
    return StdioServerParameters(command="uv", args=["run", "--quiet", "--script", str(server)])


async def roblox_forge():
    async with stdio_client(launch(SERVER)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name: t for t in (await session.list_tools()).tools}
            assert EXPECTED <= set(tools), f"missing tools: {EXPECTED - set(tools)}"
            assert tools["check_project"].annotations.read_only_hint is True
            assert tools["create_project"].annotations.read_only_hint is False

            with tempfile.TemporaryDirectory() as tmp:
                game = str(Path(tmp) / "game")
                created = payload(await session.call_tool("create_project", {"path": game, "name": "Smoke"}))
                assert created["ok"], created
                checked = payload(await session.call_tool("check_project", {"path": game}))
                assert checked["ok"] and not checked["warnings"], checked
                audited = payload(await session.call_tool("audit_remotes", {"path": game}))
                assert audited["ok"] and audited["wrapped"] == 1, audited
                mapped = payload(await session.call_tool("map_remotes", {"path": game}))
                assert mapped["ok"] and [r["name"] for r in mapped["remotes"]] == ["ClaimDaily"], mapped
                feel = payload(await session.call_tool("audit_feel", {"path": game}))
                assert feel["ok"] and feel["with_feedback"] == 1, feel
                polish = payload(await session.call_tool("audit_polish", {"path": game}))
                assert polish["ok"] and not polish["findings"], polish
                docs = str(EXAMPLE_DOCS)
                story = payload(await session.call_tool("review_story", {"path": docs}))
                assert story["ok"] and story["lines"] == 9, story
                built = payload(await session.call_tool("build_dialogue", {
                    "path": docs, "out": str(Path(game) / "src" / "shared" / "Dialogue.luau")}))
                assert built["ok"] and built["runner"].startswith("wrote"), built
                vo = payload(await session.call_tool("export_voiceover", {"path": docs, "out": str(Path(tmp) / "vo.md")}))
                assert vo["ok"], vo
                loc = payload(await session.call_tool("export_localization", {
                    "path": docs, "out": str(Path(tmp) / "loc.csv"), "locales": ["es"]}))
                assert loc["ok"] and loc["rows"] == 19, loc
                built_check = payload(await session.call_tool("check_project", {"path": game}))
                assert built_check["ok"], built_check

            odds = payload(await session.call_tool("check_odds", {"outcomes": [
                {"name": "Common", "percent": 90}, {"name": "Rare", "percent": 10}]}))
            assert odds["ok"], odds
            recipe = payload(await session.call_tool("vfx_recipe", {"effect": "hit_spark", "color": "#ff8800"}))
            assert recipe["ok"] and "ColorSequence.new" in recipe["code"], recipe
            budget = payload(await session.call_tool("datastore_budget", {"players": 20}))
            assert budget["budget_per_minute"] == 860, budget
            print(f"roblox-forge smoke test passed: {len(tools)} tools; rojo_build={checked['rojo_build']}")


async def creative_director():
    async with stdio_client(launch(DIRECTOR)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name: t for t in (await session.list_tools()).tools}
            assert DIRECTOR_TOOLS <= set(tools), f"missing tools: {DIRECTOR_TOOLS - set(tools)}"
            assert tools["find_slop"].annotations.read_only_hint is True

            seeds = payload(await session.call_tool("concept_seeds", {"count": 2, "seed": 7}))
            assert seeds["ok"] and seeds["seed"] == 7 and len(seeds["concepts"]) == 2, seeds
            review = payload(await session.call_tool("review_design", {"text": "# Pitch\nA game.\n"}))
            assert not review["ok"] and review["sections"]["fantasy"] == "Pitch", review
            brief = payload(await session.call_tool("review_design", {"text": "**Hook:** x\n", "platform": "roblox"}))
            assert brief["sections"]["hook"] == "Hook" and "social" in [m["section"] for m in brief["missing"]], brief
            with tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / "ui.js").write_text('title = "My ' + 'Game";\n')
                slop = payload(await session.call_tool("find_slop", {"paths": [tmp]}))
            assert [f["rule"] for f in slop["findings"]] == ["generic-title"], slop
            print(f"creative-director smoke test passed: {len(tools)} tools")


async def main():
    await roblox_forge()
    await creative_director()


if __name__ == "__main__":
    asyncio.run(main())
