"""Generate code (autodoc) Reference pages via mkdocstrings.

Standard mkdocstrings + mkdocs-gen-files recipe. Walks the ``models``, ``db``,
``services``, and ``repositories`` packages under ``src/chronovista`` and emits
one page per module at ``reference/code/<path>.md`` containing a single
``:::`` autodoc directive. A ``reference/code/SUMMARY.md`` literate-nav file is
written grouping the pages by top-level package. Executed at build time by the
``gen-files`` mkdocs plugin.

Skipped: ``__init__`` files, ``__main__`` modules, private modules (leading
underscore), and Alembic ``migrations`` (not part of the public code surface).
"""

from __future__ import annotations

from pathlib import Path

import mkdocs_gen_files

PACKAGES = ("models", "db", "services", "repositories")

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def _is_skippable(parts: tuple[str, ...], stem: str) -> bool:
    if "migrations" in parts:
        return True
    if stem in ("__init__", "__main__"):
        return True
    return stem.startswith("_")


def main() -> None:
    # package -> list of (doc_path, dotted_module, title)
    grouped: dict[str, list[tuple[str, str, str]]] = {pkg: [] for pkg in PACKAGES}

    for pkg in PACKAGES:
        pkg_dir = SRC / "chronovista" / pkg
        if not pkg_dir.exists():
            continue
        for path in sorted(pkg_dir.rglob("*.py")):
            rel = path.relative_to(SRC)  # e.g. chronovista/models/channel.py
            parts = rel.with_suffix("").parts
            if _is_skippable(parts, path.stem):
                continue

            dotted = ".".join(parts)
            doc_path = Path("reference", "code", *rel.with_suffix(".md").parts)
            title = rel.with_suffix("").parts[-1]

            with mkdocs_gen_files.open(doc_path, "w") as fd:
                fd.write(f"# `{dotted}`\n\n")
                fd.write(f"::: {dotted}\n")

            mkdocs_gen_files.set_edit_path(doc_path, str(rel))

            nav_target = "/".join(rel.with_suffix(".md").parts)
            grouped[pkg].append((nav_target, dotted, title))

    section_titles = {
        "models": "Models",
        "db": "Database",
        "services": "Services",
        "repositories": "Repositories",
    }

    summary_lines: list[str] = []
    for pkg in PACKAGES:
        entries = grouped.get(pkg, [])
        if not entries:
            continue
        summary_lines.append(f"* {section_titles[pkg]}")
        for nav_target, _dotted, title in entries:
            summary_lines.append(f"    * [{title}]({nav_target})")

    with mkdocs_gen_files.open("reference/code/SUMMARY.md", "w") as fd:
        fd.write("\n".join(summary_lines) + "\n")

    # Top-level Reference literate-nav: wires CLI, API, and Code subtrees.
    # `api/` and `code/` are expanded from their own SUMMARY.md files.
    with mkdocs_gen_files.open("reference/SUMMARY.md", "w") as fd:
        fd.write("* [CLI](cli.md)\n")
        fd.write("* [REST API](api/)\n")
        fd.write("* [Code](code/)\n")


main()
