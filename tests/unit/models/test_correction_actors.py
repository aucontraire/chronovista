"""
Tests for transcript correction actor constants and helpers.

Verifies that actor string constants have the expected values and that
the ``auto_actor`` helper produces correctly formatted actor strings.
"""

from __future__ import annotations

from chronovista.models.correction_actors import (
    ACTOR_CLI_BATCH,
    ACTOR_CLI_INTERACTIVE,
    ACTOR_USER_LOCAL,
    auto_actor,
)


class TestActorConstants:
    """Verify each actor constant carries the correct literal value."""

    def test_actor_user_local(self) -> None:
        assert ACTOR_USER_LOCAL == "user:local"

    def test_actor_cli_batch(self) -> None:
        assert ACTOR_CLI_BATCH == "cli:batch"

    def test_actor_cli_interactive(self) -> None:
        assert ACTOR_CLI_INTERACTIVE == "cli:interactive"


class TestAutoActor:
    """Verify the ``auto_actor`` helper returns the expected format."""

    def test_whisper_v3(self) -> None:
        assert auto_actor("whisper-v3") == "auto:whisper-v3"

    def test_deepgram_nova2(self) -> None:
        assert auto_actor("deepgram-nova2") == "auto:deepgram-nova2"

    def test_plain_engine_name(self) -> None:
        assert auto_actor("myengine") == "auto:myengine"

    def test_empty_string_returns_auto_colon(self) -> None:
        """Empty engine is allowed per spec -- no validation required."""
        assert auto_actor("") == "auto:"
