"""
Integration tests for the Docker containerized stack.

These tests require Docker to be running and are skipped by default.
Run with: pytest -m docker tests/integration/test_docker_stack.py
"""

from __future__ import annotations

import subprocess
import time

import pytest

pytestmark = [pytest.mark.docker, pytest.mark.integration]


class TestDockerStack:
    """Tests for the containerized chronovista stack."""

    def test_dockerfile_builds_successfully(self) -> None:
        """Verify the Docker image builds without errors."""
        result = subprocess.run(
            ["docker", "compose", "build"],
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert result.returncode == 0, f"Docker build failed: {result.stderr}"

    def test_image_size_under_550mb(self) -> None:
        """Verify the app image is under 550MB without NLP deps."""
        result = subprocess.run(
            ["docker", "images", "chronovista-app", "--format", "{{.Size}}"],
            capture_output=True,
            text=True,
        )
        # Parse size (e.g., "360MB", "1.2GB")
        size_str = result.stdout.strip()
        assert size_str, "Image not found"
        if "GB" in size_str:
            size_mb = float(size_str.replace("GB", "")) * 1024
        else:
            size_mb = float(size_str.replace("MB", ""))
        assert size_mb < 550, f"Image size {size_str} exceeds 550MB limit"

    def test_stack_starts_with_compose_up(self) -> None:
        """Verify both containers start successfully."""
        result = subprocess.run(
            ["docker", "compose", "up", "-d"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Stack start failed: {result.stderr}"

        # Verify containers are running
        ps_result = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            capture_output=True,
            text=True,
        )
        assert ps_result.returncode == 0

    def test_health_endpoint_responds(self) -> None:
        """Verify the API health endpoint returns 200."""
        # Wait for app to be ready
        for _ in range(30):
            try:
                import httpx

                response = httpx.get("http://localhost:8765/api/v1/health", timeout=5)
                if response.status_code == 200:
                    return
            except Exception:
                pass
            time.sleep(2)
        pytest.fail("Health endpoint did not respond within 60 seconds")

    def test_spa_catchall_returns_html(self) -> None:
        """Verify non-API routes return index.html for SPA routing."""
        import httpx

        response = httpx.get("http://localhost:8765/onboarding", timeout=5)
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_api_routes_return_json(self) -> None:
        """Verify API routes return JSON, not index.html."""
        import httpx

        response = httpx.get("http://localhost:8765/api/v1/health", timeout=5)
        assert response.status_code == 200
        assert "application/json" in response.headers.get("content-type", "")
