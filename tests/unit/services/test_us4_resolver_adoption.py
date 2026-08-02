"""US4 resolver-adoption checks (Feature 060, T035 / FR-020).

The default-parameter sites keep their signatures but default to ``None`` and
resolve when unset (no hardcoded placeholder). The literal-absence itself is
enforced by tests/unit/test_no_identity_literals.py; here we lock the
default-None contract and the CLI resolver helpers.
"""

from __future__ import annotations

import inspect


def test_get_topic_insights_user_id_defaults_to_none() -> None:
    from chronovista.services.topic_analytics_service import TopicAnalyticsService

    sig = inspect.signature(TopicAnalyticsService.get_topic_insights)
    param = sig.parameters["user_id"]
    assert param.default is None  # resolve-when-unset, signature preserved


def test_language_commands_expose_resolver_helpers() -> None:
    import chronovista.cli.language_commands as mod

    assert hasattr(mod, "_resolve_user_id")
    assert hasattr(mod, "_current_user_id")


def test_topic_insights_resolves_when_user_id_none() -> None:
    # Behavioural: get_topic_insights(None) resolves the canonical identity.
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from chronovista.services.topic_analytics_service import TopicAnalyticsService

    svc = TopicAnalyticsService()

    async def _fake_sessions():  # type: ignore[no-untyped-def]
        yield MagicMock()

    with (
        patch("chronovista.services.topic_analytics_service.db_manager") as mock_dbm,
        patch(
            "chronovista.services.identity_service.IdentityService.resolve",
            new=AsyncMock(return_value="UCresolved0000000000000"),
        ) as mock_resolve,
    ):
        mock_dbm.get_session.return_value = _fake_sessions()
        # Short-circuit the heavy query path via the cache after resolution.
        svc._get_cached_result = MagicMock(return_value=MagicMock())  # type: ignore[method-assign]

        result = asyncio.run(svc.get_topic_insights(user_id=None))

        assert result is not None
        mock_resolve.assert_awaited_once()
