"""Generate the private-term list used by the pre-commit leak check.

The list is every entity name and alias in the local library. It is written to
``.private-terms`` at the repository root, which is **gitignored**: the list is
itself the sensitive data and must never be committed. For the same reason this
docstring names no examples from it.

Every entity type is included, not just people. The exposure this guards
against is not only "who does the owner watch" but "what subjects does the
owner care about" — organizations, places, events, and concepts identify a
person's politics at least as sharply as names do, and are the categories that
attract hostile attention.

Two exclusions, both narrow and both stated so they are not mistaken for
completeness:

- **Toolchain terms** (``ALLOWLIST``). Some entities are the software this
  project is built with or about. They appear throughout the codebase for
  reasons that have nothing to do with the owner's viewing, and blocking them
  would make the check unusable. They also disclose nothing personal.
- **Nothing else.** Short and common names are *not* excluded, because the
  check matches on word boundaries; a three-letter agency acronym matched as a
  substring hits "especially" and "association", but matched as a word it does
  not.

Usage
-----
    python scripts/utilities/gen_private_terms.py
    python scripts/utilities/gen_private_terms.py --dsn postgresql+asyncpg://...

Re-run after adding entities. The check fails open when the list is missing, so
a stale list silently reduces coverage rather than blocking work.
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DEFAULT_DSN = "postgresql+asyncpg://chronovista:chronovista@localhost:5435/chronovista"
OUTPUT = pathlib.Path(__file__).resolve().parents[2] / ".private-terms"

# Entities that are this project's own subject matter or toolchain. Present in
# the library because the owner watches technology content, but they identify
# the software rather than the person, and they occur throughout the repository
# for unrelated reasons.
ALLOWLIST = {
    "Anthropic",
    "ChatGPT",
    "Claude",
    "Claude Code",
    "GraphRAG",
    "Knowledge Graph",
    "Large Language Model",
    "LLM",
    "Obsidian",
    "OpenAI",
    "Vector Database",
}

# Aliases that are ordinary English words. Word boundaries do not rescue these
# — "web UI", "fork the repo", "peek at the output", "check mate" are all
# legitimate, and a detector that fires on them gets switched off. Each of these
# entities is still covered by its full name, which is the form that actually
# identifies a person. Listed separately from ALLOWLIST because the reason is
# different: these are not this project's subject matter, they are collisions.
COMMON_WORD_ALIASES = {
    "Fork",
    "Mate",
    "Peek",
    "Sham",
    "Web",
}

QUERY = text(
    """
    SELECT canonical_name AS term FROM named_entities
    UNION
    SELECT alias_name FROM entity_aliases
    """
)


async def main(dsn: str) -> int:
    engine = create_async_engine(dsn)
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(QUERY)
            # Compared case-insensitively: the same name exists as an alias in
            # other casings ("Openai" beside "OpenAI"), and an exact-set
            # subtraction leaves those behind for the case-insensitive matcher
            # to flag — allowlisting a term must allowlist all its spellings.
            blocked = {a.casefold() for a in ALLOWLIST | COMMON_WORD_ALIASES}
            terms = sorted(
                {
                    r.term.strip()
                    for r in rows
                    if r.term
                    and r.term.strip()
                    and r.term.strip().casefold() not in blocked
                }
            )
    finally:
        await engine.dispose()

    # A one-character term would match a word anywhere; nothing in the library
    # is that short, but the guard costs nothing and the failure would be loud.
    terms = [t for t in terms if len(t) > 1]

    OUTPUT.write_text("\n".join(terms) + "\n", encoding="utf-8")
    print(f"Wrote {len(terms)} terms to {OUTPUT.name} ({len(ALLOWLIST)} allowlisted)")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate .private-terms")
    parser.add_argument("--dsn", default=DEFAULT_DSN, help="async SQLAlchemy DSN")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.dsn)))
