"""Integration tests for Feature 056 tag merge/preview/undo API endpoints.

Exercises the merge preview (exact distinct counts), merge execution, the
cross-feature data contract (downstream consumers reflect the merge), undo,
and auth, using the ``sample_data`` fixture from the canonical-tags router
tests. The fixture seeds Music with videos {vid1, vid2, vid4} and New York
with {vid2}, so merging New York into Music yields a DISTINCT video count of
3 — the overlap case (vid2 is shared) that a naive per-tag sum (3 + 1 = 4)
would get wrong.
"""

# The seeding fixtures are defined in the sibling canonical-tags router test
# module and imported below for reuse; ruff flags each use as a parameter as a
# redefinition (F811), which is a false positive for this pytest pattern.
# ruff: noqa: F811

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

# Reuse the seeding fixtures defined in the canonical-tags router test module.
from tests.integration.api.test_canonical_tags_router import (  # noqa: F401
    cleanup_test_data,
    sample_channel,
    sample_data,
    test_data_session,
)

pytestmark = pytest.mark.asyncio

_AUTH = "chronovista.api.deps.youtube_oauth"


class TestMergePreview:
    async def test_preview_dedups_overlapping_videos(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """Preview of New York -> Music counts the shared video once (2, not 3)."""
        from unittest.mock import patch

        with patch(_AUTH) as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.post(
                "/api/v1/canonical-tags/merge/preview",
                json={
                    "source_normalized_forms": ["new york"],
                    "target_normalized_form": "music",
                },
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert (
            data["resulting_video_count"] == 3
        ), "vid2 is shared; distinct union of Music{vid1,vid2,vid4}+NY{vid2} is 3, not 4"
        assert data["target_tag"] == "Music"


class TestContainsSearch:
    async def test_contains_finds_midstring_that_prefix_misses(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """'york' finds 'New York' in contains mode but not in prefix mode."""
        from unittest.mock import patch

        with patch(_AUTH) as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            contains = await async_client.get(
                "/api/v1/canonical-tags?q=york&match_mode=contains&limit=50"
            )
            prefix = await async_client.get(
                "/api/v1/canonical-tags?q=york&match_mode=prefix&limit=50"
            )
        assert contains.status_code == 200 and prefix.status_code == 200
        contains_forms = {t["normalized_form"] for t in contains.json()["data"]}
        prefix_forms = {t["normalized_form"] for t in prefix.json()["data"]}
        assert "new york" in contains_forms, "contains must find mid-string 'New York'"
        assert "new york" not in prefix_forms, "prefix must NOT find mid-string 'York'"

    async def test_contains_below_min_length_returns_empty(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """Contains mode with a 1-char query returns no results (FR-003)."""
        from unittest.mock import patch

        with patch(_AUTH) as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.get(
                "/api/v1/canonical-tags?q=y&match_mode=contains"
            )
        assert resp.status_code == 200
        assert resp.json()["data"] == []


class TestMerge:
    async def test_merge_executes_and_dedups(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        from unittest.mock import patch

        with patch(_AUTH) as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.post(
                "/api/v1/canonical-tags/merge",
                json={
                    "source_normalized_forms": ["new york"],
                    "target_normalized_form": "music",
                    "reason": "integration test",
                },
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert (
            data["new_video_count"] == 3
        ), "distinct video count after merge (vid2 deduped)"
        assert data["operation_id"]

    async def test_preview_equals_actual_merge(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """SC-008: preview counts equal what the merge actually produces."""
        from unittest.mock import patch

        body = {
            "source_normalized_forms": ["new york"],
            "target_normalized_form": "music",
        }
        with patch(_AUTH) as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            preview = await async_client.post(
                "/api/v1/canonical-tags/merge/preview", json=body
            )
            merge = await async_client.post("/api/v1/canonical-tags/merge", json=body)
        assert preview.status_code == 200 and merge.status_code == 200
        assert (
            preview.json()["data"]["resulting_video_count"]
            == merge.json()["data"]["new_video_count"]
        ), "preview video count must equal the merge's actual new_video_count"

    async def test_merge_self_merge_rejected(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        from unittest.mock import patch

        with patch(_AUTH) as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.post(
                "/api/v1/canonical-tags/merge",
                json={
                    "source_normalized_forms": ["music"],
                    "target_normalized_form": "music",
                },
            )
        assert resp.status_code == 400, resp.text

    async def test_merge_requires_auth(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        from unittest.mock import patch

        with patch(_AUTH) as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            resp = await async_client.post(
                "/api/v1/canonical-tags/merge",
                json={
                    "source_normalized_forms": ["new york"],
                    "target_normalized_form": "music",
                },
            )
        assert resp.status_code == 401, resp.text


class TestCrossFeatureContract:
    async def test_merge_then_downstream_consumers(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """After merge, target /videos includes the source's video; source resolves to target."""
        from unittest.mock import patch

        with patch(_AUTH) as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            merge = await async_client.post(
                "/api/v1/canonical-tags/merge",
                json={
                    "source_normalized_forms": ["new york"],
                    "target_normalized_form": "music",
                },
            )
            assert merge.status_code == 200, merge.text

            # Consumer 1: target /videos returns the union (vid1, vid2) — vid2
            # was tagged via New York and must still appear under Music.
            videos = await async_client.get(
                "/api/v1/canonical-tags/music/videos?include_unavailable=true"
            )
            assert videos.status_code == 200, videos.text
            vids = {v["video_id"] for v in videos.json()["data"]}
            assert (
                len(vids) == 3
            ), f"Music retains 3 distinct videos; shared vid2 not double-counted, got {vids}"

            # Consumer 2: the former New York raw alias now resolves to Music.
            resolve = await async_client.get(
                "/api/v1/canonical-tags/resolve",
                params={"raw_form": "ctag_test_New York"},
            )
            assert resolve.status_code == 200, resolve.text
            assert resolve.json()["data"]["normalized_form"] == "music"


class TestUndo:
    async def test_merge_then_undo_restores_source(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        from unittest.mock import patch

        with patch(_AUTH) as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            merge = await async_client.post(
                "/api/v1/canonical-tags/merge",
                json={
                    "source_normalized_forms": ["new york"],
                    "target_normalized_form": "music",
                },
            )
            op_id = merge.json()["data"]["operation_id"]

            undo = await async_client.post(
                f"/api/v1/canonical-tags/operations/{op_id}/undo"
            )
            assert undo.status_code == 200, undo.text
            assert undo.json()["data"]["operation_type"] == "merge"

            # Second undo must 409 (already undone).
            undo2 = await async_client.post(
                f"/api/v1/canonical-tags/operations/{op_id}/undo"
            )
            assert undo2.status_code == 409, undo2.text
