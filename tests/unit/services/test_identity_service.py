"""Tests for IdentityService.resolve / get_established_identity (Feature 060, T013).

The AppIdentityRepository is mocked — no DB I/O. Later tasks (T018, T024, T026)
add repair/reset/mismatch-write coverage.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from chronovista.models.app_identity import (
    AppIdentitySource,
    IdentityInvariants,
    MergeStats,
)
from chronovista.repositories.user_language_preference_repository import (
    RekeyCollisionError,
)
from chronovista.services.identity_service import (
    IdentityError,
    IdentityMismatchError,
    IdentityNotEstablishedError,
    IdentityService,
    InvariantRegressionError,
    LanguagePrefRekeyError,
    PreImageError,
    UnrecognizedIdentityConfigError,
)

pytestmark = pytest.mark.asyncio

CHANNEL = "UCzYTmeK-6v3DcJ6hzRh1q9w"


def _repo() -> MagicMock:
    repo = MagicMock()
    repo.get_identity = AsyncMock()
    repo.set_identity = AsyncMock()
    repo.update_identity = AsyncMock()
    return repo


def _row(user_id: str, source: AppIdentitySource) -> MagicMock:
    row = MagicMock()
    row.user_id = user_id
    row.source = source.value
    return row


class TestResolvePersisted:
    async def test_returns_persisted_unchanged(self) -> None:
        repo = _repo()
        repo.get_identity.return_value = _row(CHANNEL, AppIdentitySource.CHANNEL)
        svc = IdentityService(identity_repo=repo)

        result = await svc.resolve(MagicMock())
        assert result == CHANNEL
        repo.set_identity.assert_not_awaited()

    async def test_matching_channel_no_raise(self) -> None:
        repo = _repo()
        repo.get_identity.return_value = _row(CHANNEL, AppIdentitySource.CHANNEL)
        svc = IdentityService(identity_repo=repo)

        result = await svc.resolve(MagicMock(), authenticated_channel_id=CHANNEL)
        assert result == CHANNEL

    async def test_mismatch_raises(self) -> None:
        repo = _repo()
        repo.get_identity.return_value = _row(CHANNEL, AppIdentitySource.CHANNEL)
        svc = IdentityService(identity_repo=repo)

        with pytest.raises(IdentityMismatchError):
            await svc.resolve(
                MagicMock(), authenticated_channel_id="UCdifferent000000000000"
            )

    async def test_local_constant_persisted_not_treated_as_mismatch(self) -> None:
        # A persisted local_constant + an authenticated channel is the reset case,
        # not a mismatch — resolve returns the persisted value without raising.
        repo = _repo()
        repo.get_identity.return_value = _row(
            "local_user", AppIdentitySource.LOCAL_CONSTANT
        )
        svc = IdentityService(identity_repo=repo)

        result = await svc.resolve(MagicMock(), authenticated_channel_id=CHANNEL)
        assert result == "local_user"


class TestResolveEstablish:
    async def test_establishes_channel_when_given(self) -> None:
        repo = _repo()
        repo.get_identity.return_value = None
        repo.set_identity.return_value = _row(CHANNEL, AppIdentitySource.CHANNEL)
        svc = IdentityService(identity_repo=repo)

        result = await svc.resolve(MagicMock(), authenticated_channel_id=CHANNEL)
        assert result == CHANNEL
        args = repo.set_identity.await_args
        assert args.kwargs["obj_in"].source is AppIdentitySource.CHANNEL
        assert args.kwargs["obj_in"].user_id == CHANNEL

    async def test_establishes_local_constant_when_no_channel(self) -> None:
        repo = _repo()
        repo.get_identity.return_value = None
        repo.set_identity.return_value = _row(
            "local_user", AppIdentitySource.LOCAL_CONSTANT
        )
        svc = IdentityService(identity_repo=repo)

        result = await svc.resolve(MagicMock())  # no channel supplied
        assert result == "local_user"
        args = repo.set_identity.await_args
        assert args.kwargs["obj_in"].source is AppIdentitySource.LOCAL_CONSTANT


class TestGetEstablishedIdentity:
    async def test_returns_when_present(self) -> None:
        repo = _repo()
        repo.get_identity.return_value = _row(CHANNEL, AppIdentitySource.CHANNEL)
        svc = IdentityService(identity_repo=repo)

        assert await svc.get_established_identity(MagicMock()) == CHANNEL

    async def test_raises_when_absent(self) -> None:
        repo = _repo()
        repo.get_identity.return_value = None
        svc = IdentityService(identity_repo=repo)

        with pytest.raises(IdentityNotEstablishedError):
            await svc.get_established_identity(MagicMock())
        repo.set_identity.assert_not_awaited()  # read-only: never establishes


def _uv_repo(
    *,
    distinct: list[str],
    before: IdentityInvariants,
    after: IdentityInvariants,
) -> MagicMock:
    repo = MagicMock()
    repo.list_distinct_user_ids = AsyncMock(return_value=distinct)
    repo.count_identity_invariants = AsyncMock(side_effect=[before, after])
    repo.dump_merge_pre_image = AsyncMock(return_value=[])
    repo.merge_user_identity = AsyncMock(
        return_value=MergeStats(merged=1, deleted=1, rekeyed=2)
    )
    return repo


def _lang_repo(distinct: list[str] | None = None) -> MagicMock:
    repo = MagicMock()
    repo.list_distinct_user_ids = AsyncMock(return_value=distinct or [])
    repo.rekey_user_id = AsyncMock(return_value=0)
    return repo


def _session() -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


_INV = IdentityInvariants(distinct_watched_videos=10, liked_count=3, rewatch_sum=5)


class TestRepair:
    def _svc(self, identity_repo: MagicMock, uv_repo: MagicMock) -> IdentityService:
        svc = IdentityService(
            identity_repo=identity_repo,
            user_video_repo=uv_repo,
            lang_pref_repo=_lang_repo(),
        )
        svc._write_pre_image = MagicMock(return_value="/data/backups/pre.json")
        return svc

    async def test_real_run_commits_and_merges(self) -> None:
        idrepo = _repo()
        idrepo.get_identity.return_value = _row(CHANNEL, AppIdentitySource.CHANNEL)
        uv = _uv_repo(distinct=[CHANNEL, "takeout_user"], before=_INV, after=_INV)
        svc = self._svc(idrepo, uv)
        session = _session()

        report = await svc.repair(session, dry_run=False)

        uv.merge_user_identity.assert_awaited_once()
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()
        assert report.placeholder_user_ids == ["takeout_user"]
        assert report.pre_image_path == "/data/backups/pre.json"

    async def test_dry_run_rolls_back_writes_nothing(self) -> None:
        idrepo = _repo()
        idrepo.get_identity.return_value = _row(CHANNEL, AppIdentitySource.CHANNEL)
        uv = _uv_repo(distinct=[CHANNEL, "takeout_user"], before=_INV, after=_INV)
        svc = self._svc(idrepo, uv)
        session = _session()

        report = await svc.repair(session, dry_run=True)

        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()
        svc._write_pre_image.assert_not_called()  # dry-run writes nothing
        assert report.dry_run is True

    async def test_idempotent_noop_when_single_identity(self) -> None:
        idrepo = _repo()
        idrepo.get_identity.return_value = _row(CHANNEL, AppIdentitySource.CHANNEL)
        uv = _uv_repo(distinct=[CHANNEL], before=_INV, after=_INV)
        svc = self._svc(idrepo, uv)
        session = _session()

        report = await svc.repair(session, dry_run=False)

        uv.merge_user_identity.assert_not_awaited()
        # Commits even with nothing to merge (harmless empty commit here; the
        # commit matters when the no-op branch follows a freshly-adopted id).
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()
        assert report.placeholder_user_ids == []

    async def test_noop_commits_freshly_adopted_identity(self) -> None:
        # Adopt a real channel from data, then find no placeholders to merge —
        # the flush-only set_identity must still be committed, not dropped.
        idrepo = _repo()
        idrepo.get_identity.return_value = None
        idrepo.set_identity.return_value = _row(CHANNEL, AppIdentitySource.CHANNEL)
        uv = _uv_repo(distinct=[CHANNEL], before=_INV, after=_INV)
        svc = self._svc(idrepo, uv)
        session = _session()

        report = await svc.repair(session, dry_run=False)

        idrepo.set_identity.assert_awaited_once()  # adopted
        uv.merge_user_identity.assert_not_awaited()  # nothing to merge
        session.commit.assert_awaited_once()  # but the identity is persisted
        assert report.canonical_user_id == CHANNEL
        assert report.placeholder_user_ids == []

    async def test_noop_dry_run_does_not_commit(self) -> None:
        idrepo = _repo()
        idrepo.get_identity.return_value = _row(CHANNEL, AppIdentitySource.CHANNEL)
        uv = _uv_repo(distinct=[CHANNEL], before=_INV, after=_INV)
        svc = self._svc(idrepo, uv)
        session = _session()

        await svc.repair(session, dry_run=True)

        session.commit.assert_not_awaited()

    async def test_lang_pref_collision_rolls_back_and_raises(self) -> None:
        # FR-019: a (user_id, language_code) PK collision during the re-key must
        # roll back the whole repair transaction and surface as LanguagePrefRekeyError.
        idrepo = _repo()
        idrepo.get_identity.return_value = _row(CHANNEL, AppIdentitySource.CHANNEL)
        uv = _uv_repo(distinct=[CHANNEL, "takeout_user"], before=_INV, after=_INV)
        lang = _lang_repo(distinct=[CHANNEL, "default_user"])
        lang.rekey_user_id = AsyncMock(side_effect=RekeyCollisionError("en collides"))
        svc = IdentityService(
            identity_repo=idrepo, user_video_repo=uv, lang_pref_repo=lang
        )
        svc._write_pre_image = MagicMock(return_value="/data/backups/pre.json")
        session = _session()

        with pytest.raises(LanguagePrefRekeyError):
            await svc.repair(session, dry_run=False)
        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()

    async def test_unrecognized_identity_refuses(self) -> None:
        idrepo = _repo()
        idrepo.get_identity.return_value = _row(CHANNEL, AppIdentitySource.CHANNEL)
        # a second real channel id — not a known placeholder
        uv = _uv_repo(
            distinct=[CHANNEL, "UCsecondChannel00000000"], before=_INV, after=_INV
        )
        svc = self._svc(idrepo, uv)
        session = _session()

        with pytest.raises(UnrecognizedIdentityConfigError):
            await svc.repair(session, dry_run=False)
        uv.merge_user_identity.assert_not_awaited()
        session.commit.assert_not_awaited()

    async def test_pre_image_failure_refuses_before_merge(self) -> None:
        idrepo = _repo()
        idrepo.get_identity.return_value = _row(CHANNEL, AppIdentitySource.CHANNEL)
        uv = _uv_repo(distinct=[CHANNEL, "takeout_user"], before=_INV, after=_INV)
        svc = IdentityService(
            identity_repo=idrepo, user_video_repo=uv, lang_pref_repo=_lang_repo()
        )
        svc._write_pre_image = MagicMock(side_effect=PreImageError("no disk"))
        session = _session()

        with pytest.raises(PreImageError):
            await svc.repair(session, dry_run=False)
        uv.merge_user_identity.assert_not_awaited()
        session.commit.assert_not_awaited()

    async def test_adopts_real_channel_from_data_when_no_identity(self) -> None:
        # Primary prod case: app_identities empty, data under UC… + takeout_user.
        idrepo = _repo()
        idrepo.get_identity.return_value = None
        idrepo.set_identity.return_value = _row(CHANNEL, AppIdentitySource.CHANNEL)
        uv = _uv_repo(distinct=[CHANNEL, "takeout_user"], before=_INV, after=_INV)
        svc = self._svc(idrepo, uv)
        session = _session()

        report = await svc.repair(session, dry_run=False)

        assert report.canonical_user_id == CHANNEL
        idrepo.set_identity.assert_awaited_once()  # adopted + persisted
        uv.merge_user_identity.assert_awaited_once()
        session.commit.assert_awaited_once()

    async def test_two_real_channels_no_identity_refuses(self) -> None:
        idrepo = _repo()
        idrepo.get_identity.return_value = None
        uv = _uv_repo(
            distinct=["UCaaaaaaaaaaaaaaaaaaaaaa", "UCbbbbbbbbbbbbbbbbbbbbbb"],
            before=_INV,
            after=_INV,
        )
        svc = self._svc(idrepo, uv)

        with pytest.raises(UnrecognizedIdentityConfigError):
            await svc.repair(_session(), dry_run=False)
        uv.merge_user_identity.assert_not_awaited()

    async def test_invariant_regression_aborts_and_rolls_back(self) -> None:
        idrepo = _repo()
        idrepo.get_identity.return_value = _row(CHANNEL, AppIdentitySource.CHANNEL)
        after_worse = IdentityInvariants(
            distinct_watched_videos=9, liked_count=3, rewatch_sum=5  # watched dropped
        )
        uv = _uv_repo(
            distinct=[CHANNEL, "takeout_user"], before=_INV, after=after_worse
        )
        svc = self._svc(idrepo, uv)
        session = _session()

        with pytest.raises(InvariantRegressionError):
            await svc.repair(session, dry_run=False)
        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()

    async def test_invariant_increase_also_aborts(self) -> None:
        # A correct merge leaves the per-video invariants EXACTLY unchanged, so
        # a value that rises is as much a defect as one that falls (e.g. a
        # re-key that duplicated rows instead of moving them). A one-directional
        # "did not decrease" guard would commit this silently.
        idrepo = _repo()
        idrepo.get_identity.return_value = _row(CHANNEL, AppIdentitySource.CHANNEL)
        after_inflated = IdentityInvariants(
            distinct_watched_videos=11,  # gained a video out of nowhere
            liked_count=3,
            rewatch_sum=5,
        )
        uv = _uv_repo(
            distinct=[CHANNEL, "takeout_user"], before=_INV, after=after_inflated
        )
        svc = self._svc(idrepo, uv)
        session = _session()

        with pytest.raises(InvariantRegressionError):
            await svc.repair(session, dry_run=False)
        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()

    async def test_pre_image_covers_both_sides_of_the_merge(self) -> None:
        # The pre-image must capture the survivor rows the merge overwrites in
        # place (GREATEST/OR), not just the placeholder rows it deletes —
        # otherwise a committed repair cannot be reconstructed.
        idrepo = _repo()
        idrepo.get_identity.return_value = _row(CHANNEL, AppIdentitySource.CHANNEL)
        uv = _uv_repo(distinct=[CHANNEL, "takeout_user"], before=_INV, after=_INV)
        svc = self._svc(idrepo, uv)

        await svc.repair(_session(), dry_run=False)

        kwargs = uv.dump_merge_pre_image.await_args.kwargs
        assert kwargs["survivor_user_id"] == CHANNEL
        assert kwargs["placeholder_user_ids"] == ["takeout_user"]


class TestResolveStability:
    """T024: resolving twice is stable — the second call re-establishes nothing."""

    async def test_second_resolve_returns_persisted_without_reestablishing(
        self,
    ) -> None:
        repo = _repo()
        # First: not established → establishes channel.
        repo.get_identity.side_effect = [
            None,
            _row(CHANNEL, AppIdentitySource.CHANNEL),
        ]
        repo.set_identity.return_value = _row(CHANNEL, AppIdentitySource.CHANNEL)
        svc = IdentityService(identity_repo=repo)

        first = await svc.resolve(MagicMock(), authenticated_channel_id=CHANNEL)
        second = await svc.resolve(MagicMock())  # auth-after, no channel supplied
        assert first == second == CHANNEL
        repo.set_identity.assert_awaited_once()  # only established once


class TestResetIdentity:
    def _svc(self, identity_repo: MagicMock, uv_repo: MagicMock) -> IdentityService:
        svc = IdentityService(
            identity_repo=identity_repo,
            user_video_repo=uv_repo,
            lang_pref_repo=_lang_repo(),
        )
        svc._write_pre_image = MagicMock(return_value="/data/backups/pre.json")
        return svc

    async def test_folds_local_constant_into_channel(self) -> None:
        idrepo = _repo()
        idrepo.get_identity.return_value = _row(
            "local_user", AppIdentitySource.LOCAL_CONSTANT
        )
        uv = _uv_repo(distinct=["local_user"], before=_INV, after=_INV)
        svc = self._svc(idrepo, uv)
        session = _session()

        report = await svc.reset_identity(
            session, authenticated_channel_id=CHANNEL, dry_run=False
        )

        assert report.canonical_user_id == CHANNEL
        args = uv.merge_user_identity.await_args
        assert args.kwargs["from_user_id"] == "local_user"
        assert args.kwargs["to_user_id"] == CHANNEL
        idrepo.update_identity.assert_awaited_once()
        session.commit.assert_awaited_once()

    async def test_rekeys_language_prefs_onto_channel(self) -> None:
        # A reset must also re-key language prefs off the old local id, else they
        # orphan under local_user (get_user_preferences(channel) would be empty).
        idrepo = _repo()
        idrepo.get_identity.return_value = _row(
            "local_user", AppIdentitySource.LOCAL_CONSTANT
        )
        uv = _uv_repo(distinct=["local_user"], before=_INV, after=_INV)
        lang = _lang_repo()
        lang.rekey_user_id = AsyncMock(return_value=3)
        svc = IdentityService(
            identity_repo=idrepo, user_video_repo=uv, lang_pref_repo=lang
        )
        svc._write_pre_image = MagicMock(return_value="/data/backups/pre.json")
        session = _session()

        report = await svc.reset_identity(
            session, authenticated_channel_id=CHANNEL, dry_run=False
        )

        args = lang.rekey_user_id.await_args
        assert args.kwargs["from_user_id"] == "local_user"
        assert args.kwargs["to_user_id"] == CHANNEL
        assert report.language_prefs_rekeyed == 3

    async def test_lang_pref_collision_rolls_back(self) -> None:
        idrepo = _repo()
        idrepo.get_identity.return_value = _row(
            "local_user", AppIdentitySource.LOCAL_CONSTANT
        )
        uv = _uv_repo(distinct=["local_user"], before=_INV, after=_INV)
        lang = _lang_repo()
        lang.rekey_user_id = AsyncMock(side_effect=RekeyCollisionError("collision"))
        svc = IdentityService(
            identity_repo=idrepo, user_video_repo=uv, lang_pref_repo=lang
        )
        svc._write_pre_image = MagicMock(return_value="/data/backups/pre.json")
        session = _session()

        with pytest.raises(LanguagePrefRekeyError):
            await svc.reset_identity(
                session, authenticated_channel_id=CHANNEL, dry_run=False
            )
        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()

    async def test_refuses_when_source_is_channel(self) -> None:
        idrepo = _repo()
        idrepo.get_identity.return_value = _row(CHANNEL, AppIdentitySource.CHANNEL)
        uv = _uv_repo(distinct=[CHANNEL], before=_INV, after=_INV)
        svc = self._svc(idrepo, uv)

        with pytest.raises(IdentityError):
            await svc.reset_identity(
                _session(), authenticated_channel_id=CHANNEL, dry_run=False
            )
        uv.merge_user_identity.assert_not_awaited()

    async def test_refuses_when_no_identity(self) -> None:
        idrepo = _repo()
        idrepo.get_identity.return_value = None
        uv = _uv_repo(distinct=[], before=_INV, after=_INV)
        svc = self._svc(idrepo, uv)

        with pytest.raises(IdentityNotEstablishedError):
            await svc.reset_identity(
                _session(), authenticated_channel_id=CHANNEL, dry_run=False
            )

    async def test_dry_run_rolls_back(self) -> None:
        idrepo = _repo()
        idrepo.get_identity.return_value = _row(
            "local_user", AppIdentitySource.LOCAL_CONSTANT
        )
        uv = _uv_repo(distinct=["local_user"], before=_INV, after=_INV)
        svc = self._svc(idrepo, uv)
        session = _session()

        await svc.reset_identity(
            session, authenticated_channel_id=CHANNEL, dry_run=True
        )
        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()
        svc._write_pre_image.assert_not_called()
