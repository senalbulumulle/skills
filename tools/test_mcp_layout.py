"""Checks the mcp/<category>/<name>/ layout. Run: python3 -m unittest discover -s tools"""
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MCP = REPO / "mcp"


def dirs(folder: Path):
    return sorted(p for p in folder.iterdir() if p.is_dir() and not p.name.startswith(".") and p.name != "__pycache__")


SERVERS = [s for c in dirs(MCP) for s in dirs(c)]


class McpLayout(unittest.TestCase):
    def test_servers_sit_inside_a_category(self):
        self.assertTrue(SERVERS)
        for folder in dirs(MCP):
            self.assertFalse((folder / "server.py").exists(), f"mcp/{folder.name} is a server outside any category")
            self.assertTrue(dirs(folder), f"mcp/{folder.name} has no servers")

    def test_each_server_has_server_py_and_readme(self):
        for s in SERVERS:
            rel = s.relative_to(REPO)
            self.assertTrue((s / "server.py").is_file(), f"{rel} has no server.py")
            self.assertTrue((s / "README.md").is_file(), f"{rel} has no README.md")

    def test_names_are_unique(self):
        names = [s.name for s in SERVERS]
        self.assertEqual(len(names), len(set(names)), names)

    def test_each_server_is_indexed_and_smoke_tested(self):
        index = (MCP / "README.md").read_text(encoding="utf-8")
        smoke = (REPO / "tools" / "mcp_smoke.py").read_text(encoding="utf-8")
        for s in SERVERS:
            category, name = s.parent.name, s.name
            self.assertIn(f"]({category}/{name}/README.md)", index, f"mcp/README.md does not list {category}/{name}")
            self.assertIn(f'MCP / "{category}" / "{name}"', smoke, f"tools/mcp_smoke.py does not start {category}/{name}")


if __name__ == "__main__":
    unittest.main()
