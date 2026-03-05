"""
Actor string constants for transcript correction submissions.

Defines the actor identifiers used in the ``actor`` column of the
``transcript_corrections`` audit table.  Each constant encodes who or
what originated a correction so that downstream analytics, undo logic,
and trust scoring can discriminate between human and automated sources.

Feature 036 (FR-032).
"""

from __future__ import annotations

ACTOR_USER_LOCAL: str = "user:local"
"""Web UI (human) correction submitted from the local browser session."""

ACTOR_CLI_BATCH: str = "cli:batch"
"""Batch CLI operation (e.g., ``chronovista corrections apply --file ...``)."""

ACTOR_CLI_INTERACTIVE: str = "cli:interactive"
"""Future single-correction CLI workflow (interactive prompt)."""


def auto_actor(engine: str) -> str:
    """
    Build an actor string for an automated / AI correction source.

    Parameters
    ----------
    engine : str
        Short identifier for the engine that produced the correction
        (e.g., ``"whisper-v3"``, ``"deepgram-nova2"``).

    Returns
    -------
    str
        Actor string in the format ``"auto:<engine>"``.
    """
    return f"auto:{engine}"
