"""Guard: the package version and pyproject.toml must not drift apart.

``chronovista.__version__`` is user-visible in several places — ``chronovista
--version``, the ``/health`` and ``/settings`` API responses, and the outbound
``User-Agent`` sent to the Wayback Machine — while ``pyproject.toml`` is what
release tooling reads. They were allowed to drift for two releases (the package
reported 0.57.0 while the project was at 0.59.0), which silently misreported the
version to users and to an external service.

Bumping one without the other now fails the build.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from chronovista import __version__

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _pyproject_version() -> str:
    with PYPROJECT.open("rb") as fh:
        return str(tomllib.load(fh)["tool"]["poetry"]["version"])


def test_package_version_matches_pyproject() -> None:
    assert __version__ == _pyproject_version(), (
        f"chronovista.__version__ ({__version__}) != pyproject.toml version "
        f"({_pyproject_version()}). Bump both when releasing."
    )
