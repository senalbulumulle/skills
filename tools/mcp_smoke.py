"""End-to-end smoke test for the roblox-forge MCP server over stdio, using the official MCP client.

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

SERVER = Path(__file__).resolve().parent.parent / "mcp" / "roblox-forge" / "server.py"
EXPECTED = {"create_project", "check_project", "audit_remotes", "check_odds", "datastore_budget", "luau_check"}


def payload(result):
    if result.is_error:
        raise AssertionError(f"tool error: {result.content}")
    if result.structured_content is not None:
        data = result.structured_content
        return data.get("result", data) if set(data) == {"result"} else data
    return json.loads(result.content[0].text)


async def main():
    # Launch exactly the way users register it: uv resolves Python and the pinned SDK from the script header.
    params = StdioServerParameters(command="uv", args=["run", "--quiet", "--script", str(SERVER)])
    async with stdio_client(params) as (read, write):
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

            odds = payload(await session.call_tool("check_odds", {"outcomes": [
                {"name": "Common", "percent": 90}, {"name": "Rare", "percent": 10}]}))
            assert odds["ok"], odds
            budget = payload(await session.call_tool("datastore_budget", {"players": 20}))
            assert budget["budget_per_minute"] == 860, budget
            print(f"roblox-forge smoke test passed: {len(tools)} tools; rojo_build={checked['rojo_build']}")


if __name__ == "__main__":
    asyncio.run(main())
