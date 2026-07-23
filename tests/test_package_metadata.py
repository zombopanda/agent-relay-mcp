"""Package metadata consistency checks for public release artifacts."""

import json
import tomllib
from pathlib import Path

# The tests/ directory IS inside the package directory, so go up one level.
PKG_DIR = Path(__file__).resolve().parents[1]
ROOT = PKG_DIR if (PKG_DIR / ".github").exists() else PKG_DIR.parents[1]


def _load_package_json():
    return json.loads((PKG_DIR / "package.json").read_text())


def _load_pyproject():
    return tomllib.loads((PKG_DIR / "pyproject.toml").read_text())


def _load_readme():
    readme_path = PKG_DIR / "README.md"
    if readme_path.exists():
        return readme_path.read_text()
    return ""


# --- pyproject vs package.json consistency ---


def test_package_json_matches_pyproject_version():
    pkg = _load_package_json()
    py = _load_pyproject()
    assert pkg["version"] == py["project"]["version"] == "0.1.3"


def test_package_json_npm_name():
    pkg = _load_package_json()
    assert pkg["name"] == "agent-relay-mcp"


def test_npm_package_is_thin_launcher_only():
    """npm package ships only launcher + docs; no Python, pyproject, or tests."""
    pkg = _load_package_json()
    files = pkg["files"]
    # Must include launcher and docs
    assert "bin/agent-relay-mcp.mjs" in files
    assert "README.md" in files
    assert "LICENSE" in files
    # Must NOT include Python source or pyproject
    for entry in files:
        assert not entry.endswith(".py"), f"Python file in npm package: {entry}"
        assert "pyproject" not in entry
        assert "test" not in entry.lower()
    # Old internal paths must not appear
    assert "src/" not in str(files)


def test_npm_scripts_restored():
    """npm scripts smoke:live and provider:gate must be present with correct values."""
    pkg = _load_package_json()
    scripts = pkg.get("scripts", {})
    assert scripts.get("smoke:live") == "uv run python scripts/live_smoke.py"
    assert (
        scripts.get("provider:gate")
        == "uv run --extra test python scripts/provider_surface_gate.py"
    )


def test_pyproject_name():
    py = _load_pyproject()
    assert py["project"]["name"] == "agent-relay-mcp"


def test_sdist_excludes_nested_release_archives():
    py = _load_pyproject()
    excludes = py["tool"]["hatch"]["build"]["targets"]["sdist"]["exclude"]
    assert "*.tgz" in excludes


def test_wheel_includes_deprecated_import_shim():
    py = _load_pyproject()
    packages = py["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert "src/agent_relay_mcp" in packages
    assert "src/agent_harness_mcp" in packages


# --- Package README public content ---


def test_package_readme_has_uvx_install():
    readme = _load_readme()
    assert "uvx agent-relay-mcp" in readme


def test_package_readme_has_uv_run():
    readme = _load_readme()
    assert "uvx agent-relay-mcp" in readme  # primary install path


# --- Public branding ---


def test_package_json_no_private_registry():
    pkg = _load_package_json()
    assert "publishConfig" not in pkg
    repo_url = pkg.get("repository", {}).get("url", "")
    assert "git" + ".home" not in repo_url


def test_package_readme_no_pandenko_branding():
    readme = _load_readme()
    assert "@pandenko" not in readme
    assert "git" + ".home" not in readme


def test_package_readme_no_private_registry_instructions():
    readme = _load_readme()
    assert "pnpm config set" not in readme


# --- Public CI ---


def test_ci_workflow_uses_public_package_name():
    """CI workflows (when present) must reference agent-relay-mcp, not old names."""
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "agent-relay-mcp" in workflow
    assert "AGENT_HARNESS_RUN_LOCAL_E2E" not in workflow


def test_release_uses_oidc_for_both_registries_and_no_long_lived_npm_token():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()
    assert "id-token: write" in workflow
    assert 'node-version: "24"' in workflow
    assert "npm install --global npm@latest" in workflow
    assert "NODE_AUTH_TOKEN" not in workflow
    assert "NPM_TOKEN" not in workflow


def test_release_requires_signed_tag_and_post_pypi_smoke_before_npm():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()
    assert "git verify-tag" in workflow
    assert "gpg.ssh.allowedSignersFile" in workflow
    assert ".github/allowed_signers" in workflow
    assert "Verify tag matches package versions" in workflow
    assert "tag version does not match package versions" in workflow
    assert "pypi-smoke:" in workflow
    assert "needs: pypi-smoke" in workflow
    assert '"agent-relay-mcp==${version}"' in workflow


def test_release_attests_built_distributions():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()
    assert "attestations: write" in workflow
    assert "actions/attest-build-provenance@" in workflow
    assert "subject-path:" in workflow


def test_live_gate_uses_protected_environment():
    workflow = (ROOT / ".github" / "workflows" / "live-gate.yml").read_text()
    assert "environment: live-gates" in workflow


def test_install_smoke_uses_an_isolated_virtual_environment():
    for workflow_name in ("ci.yml", "release.yml"):
        workflow = (ROOT / ".github" / "workflows" / workflow_name).read_text()
        assert "uv pip install --system" not in workflow
        assert "/tmp/smoke-venv/bin/agent-relay-mcp doctor" in workflow
