"""
Unit tests for the shared ASR alias registry utility.

Tests both public functions exported by
``chronovista.services.asr_alias_registry``:

* ``resolve_entity_id_from_text`` — canonical-name / alias lookup
* ``register_asr_alias`` — best-effort hook that auto-registers ASR error
  aliases when a correction replacement matches a known entity

All database I/O is mocked; these are pure unit tests with no real DB
connection required.

Feature 038 — Entity Mention Detection
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from chronovista.services.asr_alias_registry import (
    is_valid_asr_alias,
    register_asr_alias,
    resolve_entity_id_from_text,
)

# ---------------------------------------------------------------------------
# CRITICAL: Module-level asyncio marker ensures async tests run properly
# with coverage tools, avoiding silent test-skipping (see CLAUDE.md).
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_execute_returns(*results: Any) -> AsyncMock:
    """Build a mock ``AsyncSession`` whose ``execute`` call returns *results* in sequence.

    Parameters
    ----------
    *results : Any
        Values to return from ``scalar_one_or_none()`` and
        ``scalars().first()`` in the order they are consumed by the
        production code.

    Returns
    -------
    AsyncMock
        A fully configured mock session with chained result mocks and a
        non-async ``begin_nested`` returning an async context manager.
    """
    side_effects: list[MagicMock] = []
    for r in results:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = r
        mock_result.scalars.return_value.first.return_value = r
        side_effects.append(mock_result)

    session = AsyncMock()
    session.execute.side_effect = side_effects

    # begin_nested() must be a *non-async* callable returning an async CM.
    # The production code does ``async with session.begin_nested():`` which
    # requires __aenter__/__aexit__ to be coroutines, but begin_nested itself
    # must not be awaited.
    nested_cm = MagicMock()
    nested_cm.__aenter__ = AsyncMock(return_value=None)
    nested_cm.__aexit__ = AsyncMock(return_value=False)
    session.begin_nested = MagicMock(return_value=nested_cm)
    return session


# ---------------------------------------------------------------------------
# TestResolveEntityIdFromText
# ---------------------------------------------------------------------------


class TestResolveEntityIdFromText:
    """Tests for ``resolve_entity_id_from_text``.

    Verifies canonical-name lookup (first priority), alias fallback
    (second priority), and None return when nothing matches.

    Feature 038 — Entity Mention Detection
    """

    async def test_returns_entity_id_and_canonical_name_on_canonical_match(
        self,
    ) -> None:
        """Returns ``(entity_id, canonical_name)`` when text matches canonical_name."""
        entity_mock = MagicMock()
        entity_mock.id = uuid.uuid4()
        entity_mock.canonical_name = "Katherine Johnson"

        # First execute: entity lookup → found; second would never be reached.
        session = _mock_execute_returns(entity_mock)

        result = await resolve_entity_id_from_text(session, "Katherine Johnson")

        assert result is not None
        entity_id, returned_name = result
        assert entity_id == entity_mock.id
        assert returned_name == "Katherine Johnson"

    async def test_match_is_case_insensitive_for_canonical_name(self) -> None:
        """Canonical-name lookup is case-insensitive (``func.lower`` applied)."""
        entity_mock = MagicMock()
        entity_mock.id = uuid.uuid4()
        entity_mock.canonical_name = "Katherine Johnson"

        session = _mock_execute_returns(entity_mock)

        # Pass lowercase variant — the SQL func.lower handles normalisation.
        result = await resolve_entity_id_from_text(session, "katherine johnson")

        assert result is not None
        entity_id, returned_name = result
        assert entity_id == entity_mock.id
        # canonical_name is returned unchanged from the DB object
        assert returned_name == "Katherine Johnson"

    async def test_returns_entity_id_and_original_text_on_alias_match(self) -> None:
        """Returns ``(entity_id, text)`` when text matches an alias (not canonical)."""
        alias_mock = MagicMock()
        alias_mock.entity_id = uuid.uuid4()

        # First execute: no entity → None; second execute: alias found.
        session = _mock_execute_returns(None, alias_mock)

        result = await resolve_entity_id_from_text(session, "Johnsbom")

        assert result is not None
        entity_id, returned_text = result
        assert entity_id == alias_mock.entity_id
        # When matched via alias, the original *text* arg is returned verbatim.
        assert returned_text == "Johnsbom"

    async def test_alias_match_is_case_insensitive(self) -> None:
        """Alias lookup is case-insensitive (``func.lower`` applied)."""
        alias_mock = MagicMock()
        alias_mock.entity_id = uuid.uuid4()

        session = _mock_execute_returns(None, alias_mock)

        # Text passed in mixed case; alias lookup normalises via SQL.
        result = await resolve_entity_id_from_text(session, "SHEINBOM")

        assert result is not None
        entity_id, returned_text = result
        assert entity_id == alias_mock.entity_id
        assert returned_text == "SHEINBOM"

    async def test_returns_none_when_no_entity_or_alias_matched(self) -> None:
        """Returns ``None`` when text matches neither entity canonical_name nor alias."""
        session = _mock_execute_returns(None, None)

        result = await resolve_entity_id_from_text(session, "Completely Unknown Person")

        assert result is None

    async def test_strips_leading_and_trailing_whitespace(self) -> None:
        """Text is stripped before matching; surrounding spaces are ignored."""
        entity_mock = MagicMock()
        entity_mock.id = uuid.uuid4()
        entity_mock.canonical_name = "Katherine Johnson"

        session = _mock_execute_returns(entity_mock)

        # The implementation does text.lower().strip() before the SQL query.
        result = await resolve_entity_id_from_text(session, "  Katherine Johnson  ")

        # Should still resolve even with surrounding whitespace.
        assert result is not None

    async def test_alias_lookup_only_called_when_entity_not_found(self) -> None:
        """Second DB query (alias) is only executed after entity lookup misses."""
        entity_mock = MagicMock()
        entity_mock.id = uuid.uuid4()
        entity_mock.canonical_name = "Katherine Johnson"

        # Only one execute result supplied — entity found on first call.
        session = _mock_execute_returns(entity_mock)

        await resolve_entity_id_from_text(session, "Katherine Johnson")

        # Should have called execute exactly once (entity lookup only).
        assert session.execute.call_count == 1

    async def test_both_queries_run_when_entity_not_found(self) -> None:
        """Both entity and alias queries are run when entity lookup returns None."""
        session = _mock_execute_returns(None, None)

        await resolve_entity_id_from_text(session, "Unknown")

        # Both entity lookup and alias lookup should execute.
        assert session.execute.call_count == 2


# ---------------------------------------------------------------------------
# TestRegisterAsrAlias
# ---------------------------------------------------------------------------


class TestRegisterAsrAlias:
    """Tests for ``register_asr_alias``.

    Covers new-alias creation, occurrence-count increment, commit
    behaviour, no-op on unknown entity, and best-effort exception
    swallowing.

    Feature 038 — Entity Mention Detection
    """

    async def test_calls_session_commit_when_commit_true(self) -> None:
        """``session.commit()`` is called when ``commit=True``."""
        entity_mock = MagicMock()
        entity_mock.id = uuid.uuid4()
        entity_mock.canonical_name = "Katherine Johnson"

        existing_alias = MagicMock()
        existing_alias.occurrence_count = 1

        session = _mock_execute_returns(entity_mock, existing_alias)

        with patch(
            "chronovista.services.asr_alias_registry.TagNormalizationService"
        ) as MockNorm:
            MockNorm.return_value.normalize.return_value = "katherine johnsom"

            await register_asr_alias(
                session,
                original_text="Katherine Johnsom",
                corrected_text="Katherine Johnson",
                commit=True,
            )

        session.commit.assert_called_once()

    async def test_does_not_call_session_commit_when_commit_false(self) -> None:
        """``session.commit()`` is NOT called when ``commit=False`` (default)."""
        entity_mock = MagicMock()
        entity_mock.id = uuid.uuid4()
        entity_mock.canonical_name = "Katherine Johnson"

        existing_alias = MagicMock()
        existing_alias.occurrence_count = 1

        session = _mock_execute_returns(entity_mock, existing_alias)

        with patch(
            "chronovista.services.asr_alias_registry.TagNormalizationService"
        ) as MockNorm:
            MockNorm.return_value.normalize.return_value = "katherine johnsom"

            await register_asr_alias(
                session,
                original_text="Katherine Johnsom",
                corrected_text="Katherine Johnson",
                commit=False,
            )

        session.commit.assert_not_called()

    async def test_commit_false_is_default(self) -> None:
        """``commit=False`` is the default; session.commit() not called without explicit True."""
        entity_mock = MagicMock()
        entity_mock.id = uuid.uuid4()
        entity_mock.canonical_name = "Katherine Johnson"

        existing_alias = MagicMock()
        existing_alias.occurrence_count = 0

        session = _mock_execute_returns(entity_mock, existing_alias)

        with patch(
            "chronovista.services.asr_alias_registry.TagNormalizationService"
        ) as MockNorm:
            MockNorm.return_value.normalize.return_value = "katherine johnsom"

            # No commit kwarg supplied → default False
            await register_asr_alias(
                session,
                original_text="Katherine Johnsom",
                corrected_text="Katherine Johnson",
            )

        session.commit.assert_not_called()

    async def test_exception_is_caught_and_not_propagated(self) -> None:
        """Exception inside the hook is swallowed (best-effort behaviour)."""
        session = AsyncMock()
        # Make execute raise to trigger the broad except clause.
        session.execute.side_effect = RuntimeError("DB exploded")

        # Should NOT raise — best-effort means any exception is caught.
        await register_asr_alias(
            session,
            original_text="Johnsom",
            corrected_text="Katherine Johnson",
        )

    async def test_exception_is_logged_not_raised(self, caplog: Any) -> None:
        """Exception is logged as a warning via the module logger."""
        import logging

        session = AsyncMock()
        session.execute.side_effect = RuntimeError("Connection refused")

        with caplog.at_level(
            logging.WARNING, logger="chronovista.services.asr_alias_registry"
        ):
            await register_asr_alias(
                session,
                original_text="Johnsom",
                corrected_text="Katherine Johnson",
            )

        assert any("hook failed" in record.message for record in caplog.records)

    async def test_uses_tag_normalization_service_for_normalized_form(
        self,
    ) -> None:
        """``TagNormalizationService.normalize()`` is called on original_text."""
        entity_mock = MagicMock()
        entity_mock.id = uuid.uuid4()
        entity_mock.canonical_name = "Katherine Johnson"

        existing_alias = MagicMock()
        existing_alias.occurrence_count = 0

        session = _mock_execute_returns(entity_mock, existing_alias)

        with patch(
            "chronovista.services.asr_alias_registry.TagNormalizationService"
        ) as MockNorm:
            mock_normalizer = MagicMock()
            mock_normalizer.normalize.return_value = "katherine johnsom"
            MockNorm.return_value = mock_normalizer

            await register_asr_alias(
                session,
                original_text="Katherine Johnsom",
                corrected_text="Katherine Johnson",
            )

        # T022: normalize() is now called twice — once for the full-string alias
        # ("Katherine Johnsom") and once for the minimal error token ("Johnsom").
        calls = mock_normalizer.normalize.call_args_list
        assert (
            len(calls) == 2
        ), f"Expected 2 normalize() calls, got {len(calls)}: {calls}"
        assert (
            calls[0].args[0] == "Katherine Johnsom"
        ), f"First call should normalize the full-string alias, got: {calls[0].args[0]}"
        assert (
            calls[1].args[0] == "Johnsom"
        ), f"Second call should normalize the minimal error token, got: {calls[1].args[0]}"

    async def test_log_prefix_appears_in_warning_on_exception(
        self, caplog: Any
    ) -> None:
        """Custom ``log_prefix`` is included in the warning log on failure."""
        import logging

        session = AsyncMock()
        session.execute.side_effect = RuntimeError("DB error")

        with caplog.at_level(
            logging.WARNING, logger="chronovista.services.asr_alias_registry"
        ):
            await register_asr_alias(
                session,
                original_text="Johnsom",
                corrected_text="Katherine Johnson",
                log_prefix="batch-correction",
            )

        # The log_prefix must appear in the warning message
        assert any("batch-correction" in record.message for record in caplog.records)

    async def test_default_log_prefix_is_asr_alias(self, caplog: Any) -> None:
        """Default ``log_prefix`` is ``'asr-alias'``."""
        import logging

        session = AsyncMock()
        session.execute.side_effect = RuntimeError("DB error")

        with caplog.at_level(
            logging.WARNING, logger="chronovista.services.asr_alias_registry"
        ):
            await register_asr_alias(
                session,
                original_text="Johnsom",
                corrected_text="Katherine Johnson",
            )

        assert any("asr-alias" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# TestIsValidAsrAlias
# ---------------------------------------------------------------------------


class TestIsValidAsrAlias:
    """Tests for ``is_valid_asr_alias`` quality gate.

    Validates that common English phrases and very short strings are
    rejected, while legitimate ASR error forms pass.
    """

    def test_rejects_all_stopword_alias(self) -> None:
        """Alias consisting entirely of stopwords is rejected."""
        assert is_valid_asr_alias("be out") is False

    def test_rejects_single_stopword(self) -> None:
        """Single common word is rejected."""
        assert is_valid_asr_alias("have") is False

    def test_rejects_multi_stopword_phrase(self) -> None:
        """Multi-word all-stopword phrase is rejected."""
        assert is_valid_asr_alias("it was on the") is False

    def test_rejects_short_alias(self) -> None:
        """Alias shorter than 4 characters is rejected."""
        assert is_valid_asr_alias("abc") is False

    def test_rejects_empty_string(self) -> None:
        """Empty string is rejected."""
        assert is_valid_asr_alias("") is False

    def test_rejects_whitespace_only(self) -> None:
        """Whitespace-only string is rejected."""
        assert is_valid_asr_alias("   ") is False

    def test_accepts_legitimate_asr_error(self) -> None:
        """Legitimate ASR error alias is accepted."""
        assert is_valid_asr_alias("Johnsom") is True

    def test_accepts_multi_word_asr_error(self) -> None:
        """Multi-word alias with at least one non-stopword is accepted."""
        assert is_valid_asr_alias("Katherine Johnsom") is True

    def test_accepts_mixed_stopword_and_name(self) -> None:
        """Alias with both stopwords and non-stopwords is accepted."""
        assert is_valid_asr_alias("Alan turn out") is True

    def test_accepts_four_char_alias(self) -> None:
        """Alias of exactly 4 characters passes length check."""
        assert is_valid_asr_alias("Seon") is True

    def test_stopword_check_is_case_insensitive(self) -> None:
        """Stopword check works regardless of case."""
        assert is_valid_asr_alias("Be Out") is False
        assert is_valid_asr_alias("BE OUT") is False


# ---------------------------------------------------------------------------
# TestRegisterAsrAliasQualityGate
# ---------------------------------------------------------------------------


class TestRegisterAsrAliasQualityGate:
    """Tests that ``register_asr_alias`` rejects aliases failing quality gate.

    The quality gate runs before any DB lookups, so the session should
    never be touched for rejected aliases.
    """

    async def test_rejects_stopword_alias_no_db_interaction(self) -> None:
        """Stopword-only alias is rejected before any DB call."""
        session = AsyncMock()

        await register_asr_alias(
            session,
            original_text="be out",
            corrected_text="Alan Turner",
        )

        session.execute.assert_not_called()

    async def test_rejects_short_alias_no_db_interaction(self) -> None:
        """Alias under 4 characters is rejected before any DB call."""
        session = AsyncMock()

        await register_asr_alias(
            session,
            original_text="ab",
            corrected_text="Katherine Johnson",
        )

        session.execute.assert_not_called()

    async def test_rejection_is_logged(self, caplog: Any) -> None:
        """Rejected alias is logged at DEBUG level."""
        import logging

        session = AsyncMock()

        with caplog.at_level(
            logging.DEBUG, logger="chronovista.services.asr_alias_registry"
        ):
            await register_asr_alias(
                session,
                original_text="be out",
                corrected_text="Alan Turner",
            )

        assert any(
            "rejected alias" in record.message and "quality gate" in record.message
            for record in caplog.records
        )
