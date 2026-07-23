from agent_crossbar import __version__
from agent_crossbar.server import mcp


def test_package_has_version():
    assert __version__ == "0.2.0"


def test_server_is_named_agents():
    assert mcp.name == "agents"
