"""
Tests for ``DatabaseManager.session()`` — commit, rollback and early exit.

Regression coverage for issue #189. ``get_session()`` is an async generator that
commits *after* the yield, so a consumer writing::

    async for session in db_manager.get_session():
        await repo.create(session, obj_in=thing)
        break

throws ``GeneratorExit`` at the suspended yield. ``GeneratorExit`` derives from
``BaseException``, so the ``except Exception`` arm did not catch it, the
``finally`` closed the session, and ``await session.commit()`` never ran. The
write was lost with no error at the call site.

Two things are asserted here, and they are different:

1. ``session()`` is a context manager, so ``return``/``break`` inside the block
   is ordinary control flow and **the commit still happens**. This is the fix —
   it makes the mistake unrepresentable rather than documenting it.
2. ``CancelledError`` now rolls back. That half was a live defect, not a latent
   one: it fires whenever a client disconnects mid-request, and under
   ``except Exception`` nothing rolled back at all.

The session is a mock throughout — the subject is the commit/rollback control
flow of the scope itself, not any database behaviour.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from chronovista.config.database import DatabaseManager

# CRITICAL: Module-level asyncio marker ensures async tests run properly
# with coverage tools, avoiding silent test-skipping (see CLAUDE.md).
pytestmark = pytest.mark.asyncio


def _manager_with_mock_session() -> tuple[DatabaseManager, MagicMock]:
    """A manager whose session factory yields a mock session."""
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock(return_value=ctx)
    manager = DatabaseManager()
    manager.get_session_factory = MagicMock(return_value=factory)  # type: ignore[method-assign]
    return manager, session


class TestSessionScopeCommits:
    """The happy path, and the early exit that used to lose writes."""

    async def test_commits_on_normal_exit(self) -> None:
        manager, session = _manager_with_mock_session()

        async with manager.session():
            pass

        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()
        session.close.assert_awaited_once()

    async def test_commits_when_the_block_returns_early(self) -> None:
        """The #189 regression, in the form the fix is meant to make safe.

        The equivalent `async for ... break` skips the commit entirely. Inside a
        context manager an early ``return`` is just control flow, so ``__aexit__``
        runs with no exception and the commit happens.
        """
        manager, session = _manager_with_mock_session()

        async def write_and_return() -> str:
            async with manager.session():
                return "done"

        assert await write_and_return() == "done"
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()

    async def test_commits_when_the_block_breaks_out_of_a_loop(self) -> None:
        """`break` inside the block is likewise ordinary control flow."""
        manager, session = _manager_with_mock_session()

        async with manager.session():
            for _ in range(3):
                break

        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()


class TestSessionScopeRollsBack:
    """Failure paths, including the two that ``except Exception`` missed."""

    async def test_rolls_back_on_exception(self) -> None:
        manager, session = _manager_with_mock_session()

        with pytest.raises(ValueError, match="boom"):
            async with manager.session():
                raise ValueError("boom")

        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()
        session.close.assert_awaited_once()

    async def test_rolls_back_on_cancellation(self) -> None:
        """The live half of #189: a cancelled request rolled nothing back.

        ``CancelledError`` derives from ``BaseException``, so the previous
        ``except Exception`` arm never ran — the session was closed with the
        transaction neither committed nor rolled back.
        """
        manager, session = _manager_with_mock_session()

        with pytest.raises(asyncio.CancelledError):
            async with manager.session():
                raise asyncio.CancelledError()

        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()
        session.close.assert_awaited_once()

    async def test_rolls_back_on_base_exception(self) -> None:
        """Any ``BaseException`` leaves the transaction resolved, not dangling."""
        manager, session = _manager_with_mock_session()

        with pytest.raises(KeyboardInterrupt):
            async with manager.session():
                raise KeyboardInterrupt()

        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()

    async def test_a_failed_commit_still_closes_the_session(self) -> None:
        """A connection lost at commit time must not leak the session."""
        manager, session = _manager_with_mock_session()
        session.commit.side_effect = RuntimeError("connection lost")

        with pytest.raises(RuntimeError, match="connection lost"):
            async with manager.session():
                pass

        session.rollback.assert_awaited_once()
        session.close.assert_awaited_once()


class TestGetSessionDelegates:
    """``get_session()`` stays for FastAPI, and shares the same scope."""

    async def test_generator_form_commits_when_fully_consumed(self) -> None:
        manager, session = _manager_with_mock_session()

        async for _ in manager.get_session():
            pass

        session.commit.assert_awaited_once()

    async def test_generator_form_does_not_commit_on_early_exit(self) -> None:
        """Documents the hazard `session()` exists to remove.

        Note what `break` alone does: **nothing, yet**. The generator is left
        suspended at its yield, and ``GeneratorExit`` is only thrown when it is
        finalized — by garbage collection, or at interpreter shutdown, which is
        where issue #189 reports the stray traceback appearing. So the commit is
        not merely skipped; the cleanup happens at an unpredictable later time.

        ``aclose()`` here forces that finalization deterministically, which is
        the only way to assert on it. The write is discarded either way.
        """
        manager, session = _manager_with_mock_session()

        agen = manager.get_session()
        async for _ in agen:
            break

        # Nothing has run yet — the generator is still suspended at its yield.
        session.commit.assert_not_awaited()
        session.rollback.assert_not_awaited()

        await agen.aclose()  # what GC or shutdown would eventually do

        session.commit.assert_not_awaited()
        session.rollback.assert_awaited_once()
        session.close.assert_awaited_once()
