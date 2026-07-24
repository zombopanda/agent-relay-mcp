import tomllib
from pathlib import Path

from agent_crossbar import __version__
from agent_crossbar.server import mcp

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_package_has_version():
    expected = tomllib.loads(PYPROJECT.read_text())["project"]["version"]
    assert __version__ == expected


def test_server_is_named_agents():
    assert mcp.name == "agents"
