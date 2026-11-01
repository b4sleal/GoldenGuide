"""Validate the merged frontend deployment without starting Docker or application services."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def compose():
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker Compose CLI is required; no daemon is needed")
    version = subprocess.run([docker, "compose", "version"], check=False, capture_output=True, timeout=15)
    if version.returncode:
        pytest.skip("Docker Compose plugin is unavailable")

    def render(*, development, backend="http://backend:8080", site="http://localhost:8080"):
        # Explicit examples and overrides keep the developer's .env and shell out of these checks.
        command = [docker, "compose", "--env-file", ".env.dev.example", "-f", "docker-compose.yml"]
        if development:
            command += ["-f", "docker-compose.dev.yml"]
        command += ["--profile", "frontend", "config", "--format", "json", "--no-env-resolution"]
        result = subprocess.run(
            command,
            check=False,
            cwd=ROOT,
            env={
                **os.environ,
                "COMPOSE_PROFILES": "",
                "FRONTEND_PORT": "8080",
                "FRONTEND_BIND_ADDRESS": "127.0.0.1",
                "BACKEND_ORIGIN": backend,
                "SITE_ORIGIN": site,
            },
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    return render


def test_development_keeps_one_public_origin_and_waits_for_vite(compose):
    services = compose(development=True)["services"]
    frontend = services["frontend"]
    vite = services["frontend-vite"]

    assert frontend["build"]["target"] == "development-proxy"
    assert frontend["depends_on"]["frontend-vite"]["condition"] == "service_healthy"
    # Merging the dev dependency must retain the base file's optional backend dependency.
    assert frontend["depends_on"]["backend"]["required"] is False
    assert frontend["ports"][0]["host_ip"] == "127.0.0.1"
    assert frontend["ports"][0]["published"] == "8080"
    assert not vite.get("ports")
    assert vite["build"]["target"] == "development"


def test_development_mounts_react_source_with_separate_linux_dependencies(compose):
    vite = compose(development=True)["services"]["frontend-vite"]
    mounts = {mount["target"]: mount for mount in vite["volumes"]}

    assert mounts["/app"]["type"] == "bind"
    assert Path(mounts["/app"]["source"]).resolve() == ROOT / "frontend"
    # Host node_modules can contain Windows binaries; they must not reach the Linux Vite process.
    assert mounts["/app/node_modules"]["type"] == "volume"
    assert "pnpm install --frozen-lockfile" in vite["command"][-1]


def test_development_accepts_a_remote_backend_and_custom_public_origin(compose):
    services = compose(
        development=True, backend="https://api.example.test", site="https://guide.example.test"
    )["services"]

    assert services["frontend"]["environment"]["BACKEND_ORIGIN"] == "https://api.example.test"
    assert services["frontend-vite"]["environment"]["GG_BACKEND_ORIGIN"] == "https://api.example.test"
    assert services["frontend-vite"]["environment"]["GG_SITE_ORIGIN"] == "https://guide.example.test"


def test_runtime_uses_built_assets_without_development_services_or_mounts(compose):
    services = compose(development=False)["services"]

    assert "frontend-vite" not in services
    assert services["frontend"]["build"]["target"] == "runtime"
    assert not services["frontend"].get("volumes")
    assert "frontend-vite" not in services["frontend"]["depends_on"]
