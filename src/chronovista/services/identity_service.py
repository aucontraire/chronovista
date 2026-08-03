"""
Canonical local-user identity service (Feature 060).

Resolves *who the local user is* exactly once, persists that identity in the
``app_identities`` singleton, and hands it to every writer/reader of
user-scoped data. Also orchestrates the one-time watch-history deduplication
repair (added in later tasks).

Design notes:
- ``resolve()`` never calls the YouTube API itself. The caller passes the
  authenticated channel id if it has one (writers already fetch it as a
  *fetch target*); otherwise the resolver persists a final local constant.
  This keeps the resolver offline-safe and free of YouTube coupling.
- ``get_established_identity()`` is read-only and raises when no identity
  exists — API endpoints use it so a read request never *establishes* identity.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..config.settings import settings
from ..models.app_identity import (
    LOCAL_USER_ID,
    AppIdentityCreate,
    AppIdentitySource,
    AppIdentityUpdate,
    IdentityInvariants,
    MergeStats,
)
from ..models.youtube_types import UserId
from ..repositories.app_identity_repository import AppIdentityRepository
from ..repositories.user_language_preference_repository import (
    RekeyCollisionError,
    UserLanguagePreferenceRepository,
)
from ..repositories.user_video_repository import UserVideoRepository

logger = logging.getLogger(__name__)

# Identity literals that are safe to merge/re-key away. Any other non-canonical
# identity (e.g. a second real channel id) is an unrecognized configuration and
# the repair refuses rather than guessing a survivor (FR-008).
_RECOGNIZED_PLACEHOLDERS: frozenset[str] = frozenset(
    {"takeout_user", "default_user", LOCAL_USER_ID}
)


class IdentityError(Exception):
    """Base class for canonical-identity errors."""


class IdentityNotEstablishedError(IdentityError):
    """Raised when a read requires an identity but none has been established."""


class IdentityMismatchError(IdentityError):
    """Raised when the authenticated channel differs from the persisted identity."""

    def __init__(self, persisted: str, authenticated: str) -> None:
        self.persisted = persisted
        self.authenticated = authenticated
        super().__init__(
            f"Authenticated channel '{authenticated}' differs from the persisted "
            f"canonical identity '{persisted}'. Refusing to write under a "
            f"mismatched identity. If you changed accounts, run 'chronovista "
            f"identity reset' or investigate before proceeding."
        )


class UnrecognizedIdentityConfigError(IdentityError):
    """Raised when non-canonical identities cannot be safely merged.

    E.g. a second real channel id alongside the canonical one — the repair
    refuses rather than guessing which to keep (FR-008).
    """

    def __init__(self, canonical: str, unrecognized: list[str]) -> None:
        self.canonical = canonical
        self.unrecognized = unrecognized
        super().__init__(
            f"Refusing to repair: unrecognized identities present alongside the "
            f"canonical '{canonical}': {unrecognized}. These are not known "
            f"placeholders, so a survivor cannot be chosen automatically. "
            f"Investigate (see 'chronovista identity status') before proceeding."
        )


class InvariantRegressionError(IdentityError):
    """Raised (after rollback) when the merge changed an integrity invariant.

    A correct merge leaves all three per-video invariants exactly unchanged, so
    any difference — a fall (data lost) or a rise (rows duplicated) — is a
    defect and aborts the repair.
    """

    def __init__(self, before: IdentityInvariants, after: IdentityInvariants) -> None:
        self.before = before
        self.after = after
        super().__init__(
            f"Repair aborted and rolled back: an integrity invariant changed "
            f"(before={before.model_dump()}, after={after.model_dump()}). No "
            f"changes were committed."
        )


class PreImageError(IdentityError):
    """Raised when the pre-image (recovery snapshot) cannot be written."""


class LanguagePrefRekeyError(IdentityError):
    """Raised (after rollback) when re-keying language preferences collides."""


class RepairReport(BaseModel):
    """Summary returned by the identity repair (dry-run or applied)."""

    dry_run: bool
    canonical_user_id: str
    source: str
    placeholder_user_ids: list[str]
    user_videos: MergeStats
    language_prefs_rekeyed: int
    invariants_before: IdentityInvariants
    invariants_after: IdentityInvariants
    pre_image_path: str | None


class IdentityService:
    """Resolves and persists the single canonical local-user identity."""

    def __init__(
        self,
        identity_repo: AppIdentityRepository | None = None,
        user_video_repo: UserVideoRepository | None = None,
        lang_pref_repo: UserLanguagePreferenceRepository | None = None,
    ) -> None:
        self.identity_repo = identity_repo or AppIdentityRepository()
        self.user_video_repo = user_video_repo or UserVideoRepository()
        self.lang_pref_repo = lang_pref_repo or UserLanguagePreferenceRepository()

    async def resolve(
        self,
        session: AsyncSession,
        *,
        authenticated_channel_id: str | None = None,
    ) -> UserId:
        """Return the canonical identity, establishing it once if needed.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        authenticated_channel_id : str | None
            The caller's authenticated YouTube channel id, if it has one
            (obtained as a fetch target). When ``None`` and no identity is yet
            persisted, a final local constant is used — loading is never gated
            on authentication.

        Returns
        -------
        UserId
            The persisted canonical identity.

        Raises
        ------
        IdentityMismatchError
            If a channel-sourced identity is persisted and a *different*
            authenticated channel is supplied.
        """
        existing = await self.identity_repo.get_identity(session)
        if existing is not None:
            if (
                existing.source == AppIdentitySource.CHANNEL.value
                and authenticated_channel_id is not None
                and authenticated_channel_id != existing.user_id
            ):
                raise IdentityMismatchError(
                    persisted=existing.user_id,
                    authenticated=authenticated_channel_id,
                )
            return existing.user_id

        if authenticated_channel_id:
            created = await self.identity_repo.set_identity(
                session,
                obj_in=AppIdentityCreate(
                    user_id=authenticated_channel_id,
                    source=AppIdentitySource.CHANNEL,
                ),
            )
        else:
            created = await self.identity_repo.set_identity(
                session,
                obj_in=AppIdentityCreate(
                    user_id=LOCAL_USER_ID,
                    source=AppIdentitySource.LOCAL_CONSTANT,
                ),
            )
        logger.info(
            "Canonical identity established: %s (source=%s) — this is permanent.",
            created.user_id,
            created.source,
        )
        return created.user_id

    async def get_established_identity(self, session: AsyncSession) -> UserId:
        """Return the persisted canonical identity, or raise if unestablished.

        Read-only: never establishes an identity. API endpoints use this so a
        read request cannot mint an identity as a side effect (FR-020a).
        """
        existing = await self.identity_repo.get_identity(session)
        if existing is None:
            raise IdentityNotEstablishedError(
                "No canonical user identity has been established yet. Run "
                "'chronovista auth login' then load your data, or run "
                "'chronovista identity repair'."
            )
        return existing.user_id

    def _write_pre_image(self, rows: list[dict[str, object]], placeholder: str) -> str:
        """Write a JSON pre-image of the rows about to change; return its path.

        Persistent location under ``settings.data_dir/backups`` (already
        gitignored via ``data/``). Refuses (raises PreImageError) if the
        directory is not writable — the merge must never run without a
        recoverable snapshot (FR-006).

        The file is written with a ``.provisional.json`` suffix because it is
        created *before* the invariant re-check and commit. On a successful
        commit it is renamed to ``.committed.json`` (see ``_finalize_pre_image``);
        if the repair aborts and rolls back, the file stays marked provisional so
        an operator cannot mistake it for evidence that a repair completed.
        """
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        safe = placeholder.replace("/", "_")
        backups_dir = Path(settings.data_dir) / "backups"
        try:
            backups_dir.mkdir(parents=True, exist_ok=True)
            path = (
                backups_dir / f"identity-merge-preimage-{safe}-{stamp}.provisional.json"
            )
            path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        except OSError as exc:
            raise PreImageError(
                f"Cannot write pre-image under {backups_dir} (verify it is a "
                f"persistent, writable location): {exc}"
            ) from exc
        # Verify the pre-image actually landed on a persistent path.
        if not path.exists():
            raise PreImageError(f"Pre-image was not written to {path}.")
        return str(path)

    def _finalize_pre_image(self, path: str) -> str:
        """Rename a provisional pre-image to ``.committed.json`` after commit.

        Best-effort: the merge has already committed, so a rename failure must
        never turn a successful repair into an error — it only leaves the file
        marked provisional. Returns the (possibly-renamed) path. A no-op for a
        path that is not provisional-named (e.g. a mocked path in unit tests).
        """
        provisional = Path(path)
        if (
            not provisional.name.endswith(".provisional.json")
            or not provisional.exists()
        ):
            return path
        final = provisional.with_name(
            provisional.name.replace(".provisional.json", ".committed.json")
        )
        try:
            provisional.replace(final)
        except OSError:
            return path
        return str(final)

    async def _select_survivor(
        self,
        session: AsyncSession,
        distinct: list[str],
        authenticated_channel_id: str | None,
    ) -> tuple[str, str]:
        """Choose (and persist) the merge survivor. Returns (user_id, source).

        Survivor rule (spec Assumptions): the identity persisted first survives.
        - If an identity is already persisted, use it.
        - Else, if the data contains exactly one non-placeholder identity (a real
          channel id), adopt it — this is the primary prod case (fresh
          ``app_identities``, data already under ``UC…`` + ``takeout_user``).
        - Else (only placeholders, or none), resolve from auth or a local
          constant.
        Two real channel ids → refuse (FR-008; never guess).
        """
        existing = await self.identity_repo.get_identity(session)
        if existing is not None:
            return existing.user_id, existing.source

        non_placeholders = [
            uid for uid in distinct if uid not in _RECOGNIZED_PLACEHOLDERS
        ]
        if len(non_placeholders) > 1:
            raise UnrecognizedIdentityConfigError(
                canonical="(unresolved)", unrecognized=non_placeholders
            )
        if len(non_placeholders) == 1:
            created = await self.identity_repo.set_identity(
                session,
                obj_in=AppIdentityCreate(
                    user_id=non_placeholders[0], source=AppIdentitySource.CHANNEL
                ),
            )
            logger.info(
                "Canonical identity adopted from existing data: %s (permanent).",
                created.user_id,
            )
            return created.user_id, created.source

        canonical = await self.resolve(
            session, authenticated_channel_id=authenticated_channel_id
        )
        row = await self.identity_repo.get_identity(session)
        return canonical, (row.source if row is not None else "unknown")

    async def repair(
        self,
        session: AsyncSession,
        *,
        dry_run: bool,
        authenticated_channel_id: str | None = None,
    ) -> RepairReport:
        """Collapse placeholder ``user_videos`` identities into the survivor.

        One transaction: select+persist the survivor → snapshot invariants →
        write a pre-image (real runs) → merge each placeholder → re-check
        invariants and abort on any regression → commit (or roll back on
        dry-run). Idempotent; refuses on an unrecognized identity configuration.
        """
        uv_distinct = await self.user_video_repo.list_distinct_user_ids(session)
        canonical, source = await self._select_survivor(
            session, uv_distinct, authenticated_channel_id
        )
        uv_placeholders = [uid for uid in uv_distinct if uid != canonical]

        lang_distinct = await self.lang_pref_repo.list_distinct_user_ids(session)
        lang_placeholders = [uid for uid in lang_distinct if uid != canonical]

        invariants_before = await self.user_video_repo.count_identity_invariants(
            session
        )

        # FR-008: refuse on any non-canonical identity (in either table) that is
        # not a known placeholder (e.g. a second real channel id) — never guess.
        unrecognized = [
            uid
            for uid in set(uv_placeholders) | set(lang_placeholders)
            if uid not in _RECOGNIZED_PLACEHOLDERS
        ]
        if unrecognized:
            raise UnrecognizedIdentityConfigError(
                canonical=canonical, unrecognized=sorted(unrecognized)
            )

        # Idempotent no-op: nothing to merge or re-key in either table. Still
        # commit on a real run — ``_select_survivor`` may have just established
        # (flush-only) a freshly-adopted identity that would otherwise be lost
        # when the session closes.
        if not uv_placeholders and not lang_placeholders:
            if not dry_run:
                await session.commit()
            return RepairReport(
                dry_run=dry_run,
                canonical_user_id=canonical,
                source=source,
                placeholder_user_ids=[],
                user_videos=MergeStats(merged=0, deleted=0, rekeyed=0),
                language_prefs_rekeyed=0,
                invariants_before=invariants_before,
                invariants_after=invariants_before,
                pre_image_path=None,
            )

        # Pre-image (real runs only — dry-run writes nothing).
        pre_image_path: str | None = None
        if not dry_run and uv_placeholders:
            rows = await self.user_video_repo.dump_merge_pre_image(
                session,
                survivor_user_id=canonical,
                placeholder_user_ids=uv_placeholders,
            )
            pre_image_path = self._write_pre_image(rows, "+".join(uv_placeholders))

        # Merge each user_videos placeholder into the survivor.
        merged = deleted = rekeyed = 0
        for placeholder in uv_placeholders:
            stats = await self.user_video_repo.merge_user_identity(
                session, from_user_id=placeholder, to_user_id=canonical
            )
            merged += stats.merged
            deleted += stats.deleted
            rekeyed += stats.rekeyed
        user_videos = MergeStats(merged=merged, deleted=deleted, rekeyed=rekeyed)

        # Re-key language preferences (US4) — within the same transaction.
        lang_rekeyed = 0
        for placeholder in lang_placeholders:
            try:
                lang_rekeyed += await self.lang_pref_repo.rekey_user_id(
                    session, from_user_id=placeholder, to_user_id=canonical
                )
            except RekeyCollisionError as exc:
                await session.rollback()
                raise LanguagePrefRekeyError(str(exc)) from exc

        invariants_after = await self.user_video_repo.count_identity_invariants(session)

        # Abort + roll back on ANY invariant change (FR-005). Equality — not
        # merely "did not decrease" — is the correct guard: every invariant is
        # computed per distinct video, and the merge collapses rows with
        # GREATEST/OR, so a correct merge leaves all three exactly unchanged.
        # A value that *rises* is as much a defect as one that falls (e.g. a
        # re-key that duplicated rows instead of moving them), and a
        # one-directional check would let it through silently.
        if invariants_after != invariants_before:
            await session.rollback()
            raise InvariantRegressionError(
                before=invariants_before, after=invariants_after
            )

        if dry_run:
            await session.rollback()
        else:
            await session.commit()
            if pre_image_path is not None:
                pre_image_path = self._finalize_pre_image(pre_image_path)

        return RepairReport(
            dry_run=dry_run,
            canonical_user_id=canonical,
            source=source,
            placeholder_user_ids=sorted(set(uv_placeholders) | set(lang_placeholders)),
            user_videos=user_videos,
            language_prefs_rekeyed=lang_rekeyed,
            invariants_before=invariants_before,
            invariants_after=invariants_after,
            pre_image_path=pre_image_path,
        )

    async def reset_identity(
        self,
        session: AsyncSession,
        *,
        authenticated_channel_id: str,
        dry_run: bool = False,
    ) -> RepairReport:
        """Fold a persisted *offline* identity into a newly available channel.

        Only applies when the persisted identity's source is ``local_constant``
        and a real channel is now available. Re-keys the local-constant rows
        onto the channel by reusing the US1 merge, then updates the persisted
        identity (FR-023). Same transactional + invariant + pre-image guarantees
        as ``repair``.
        """
        existing = await self.identity_repo.get_identity(session)
        if existing is None:
            raise IdentityNotEstablishedError(
                "No identity to reset — none has been established yet."
            )
        if existing.source != AppIdentitySource.LOCAL_CONSTANT.value:
            raise IdentityError(
                "identity reset only applies to an offline local identity; the "
                f"current identity is '{existing.user_id}' (source="
                f"{existing.source}). Nothing to reset."
            )

        old_id = existing.user_id
        new_id = authenticated_channel_id
        invariants_before = await self.user_video_repo.count_identity_invariants(
            session
        )

        pre_image_path: str | None = None
        if not dry_run:
            rows = await self.user_video_repo.dump_merge_pre_image(
                session, survivor_user_id=new_id, placeholder_user_ids=[old_id]
            )
            pre_image_path = self._write_pre_image(rows, old_id)

        stats = await self.user_video_repo.merge_user_identity(
            session, from_user_id=old_id, to_user_id=new_id
        )

        # Re-key language preferences onto the channel too, so no prefs are left
        # orphaned under the old local id (same transaction, same collision guard
        # as ``repair``).
        lang_rekeyed = 0
        try:
            lang_rekeyed = await self.lang_pref_repo.rekey_user_id(
                session, from_user_id=old_id, to_user_id=new_id
            )
        except RekeyCollisionError as exc:
            await session.rollback()
            raise LanguagePrefRekeyError(str(exc)) from exc

        await self.identity_repo.update_identity(
            session,
            obj_in=AppIdentityUpdate(user_id=new_id, source=AppIdentitySource.CHANNEL),
        )

        invariants_after = await self.user_video_repo.count_identity_invariants(session)
        if (
            invariants_after.distinct_watched_videos
            < invariants_before.distinct_watched_videos
            or invariants_after.liked_count < invariants_before.liked_count
            or invariants_after.rewatch_sum < invariants_before.rewatch_sum
        ):
            await session.rollback()
            raise InvariantRegressionError(
                before=invariants_before, after=invariants_after
            )

        if dry_run:
            await session.rollback()
        else:
            await session.commit()
            if pre_image_path is not None:
                pre_image_path = self._finalize_pre_image(pre_image_path)

        return RepairReport(
            dry_run=dry_run,
            canonical_user_id=new_id,
            source=AppIdentitySource.CHANNEL.value,
            placeholder_user_ids=[old_id],
            user_videos=stats,
            language_prefs_rekeyed=lang_rekeyed,
            invariants_before=invariants_before,
            invariants_after=invariants_after,
            pre_image_path=pre_image_path,
        )
