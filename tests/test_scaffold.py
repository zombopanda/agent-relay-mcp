from agent_relay_mcp import __version__
from agent_relay_mcp.server import mcp


def test_package_has_version():
    assert __version__ == "0.1.3"


def test_server_is_named_agents():
    assert mcp.name == "agents"
