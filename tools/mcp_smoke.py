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
MOTION = MCP / "web-dev" / "motion-forge" / "server.py"
MOTION_TOOLS = {"list_components", "get_component", "install_components", "build_showcase", "audit_motion"}


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


async def motion_forge():
    async with stdio_client(launch(MOTION)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name: t for t in (await session.list_tools()).tools}
            assert MOTION_TOOLS <= set(tools), f"missing tools: {MOTION_TOOLS - set(tools)}"
            assert tools["audit_motion"].annotations.read_only_hint is True
            assert tools["install_components"].annotations.read_only_hint is False

            count = len(payload(await session.call_tool("list_components", {}))["components"])
            listed = payload(await session.call_tool("list_components", {"category": "hero-text"}))
            assert [c["name"] for c in listed["components"]] == ["text-scramble", "split-text"], listed
            component = payload(await session.call_tool("get_component", {"name": "parallax"}))
            assert component["ok"] and "data-speed" in component["example"] and "class Parallax" in component["source"]
            with tempfile.TemporaryDirectory() as tmp:
                installed = payload(await session.call_tool("install_components", {"names": ["all"], "out": tmp}))
                assert installed["ok"] and len(installed["files"]) == count, installed
                page = payload(await session.call_tool("build_showcase", {"out": tmp}))
                assert page["ok"] and page["hero"], page
                audit = payload(await session.call_tool("audit_motion", {"paths": [tmp]}))
                assert audit["ok"] and audit["files"] == count + 1 and not audit["findings"], audit  # modules + showcase
                (Path(tmp) / "bad.css").write_text(".a { transition: all .2s; }\n")
                bad = payload(await session.call_tool("audit_motion", {"paths": [tmp]}))
                assert not bad["ok"] and bad["findings"][0]["rule"] == "transition-all", bad
            print(f"motion-forge smoke test passed: {len(tools)} tools, {count} components")


async def main():
    await motion_forge()


if __name__ == "__main__":
    asyncio.run(main())
