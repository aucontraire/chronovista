"""Generate the CLI Reference page from the Typer application.

Runs the Typer Markdown exporter (`python -m typer ... utils docs`) against
``chronovista.cli.main`` and writes the result to a mkdocs-gen-files virtual
page at ``reference/cli.md``. Executed at build time by the ``gen-files``
mkdocs plugin; not meant to be run standalone (though it can be).
"""

from __future__ import annotations

import subprocess
import sys

import mkdocs_gen_files

INTRO = """# CLI Reference

!!! info "Generated page"
    This page is generated at build time from the Typer application defined in
    `chronovista.cli.main`. Do not edit it by hand — update the CLI command
    definitions and their help text instead.

"""


def _export_cli_markdown() -> str:
    """Return the Typer-generated Markdown tree for the whole CLI."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "typer",
            "chronovista.cli.main",
            "utils",
            "docs",
            "--name",
            "chronovista",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def main() -> None:
    body = _export_cli_markdown()
    with mkdocs_gen_files.open("reference/cli.md", "w") as fd:
        fd.write(INTRO)
        fd.write(body)

    mkdocs_gen_files.set_edit_path("reference/cli.md", "src/chronovista/cli/main.py")


main()
