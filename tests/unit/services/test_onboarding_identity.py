"""Regression guard: onboarding load path uses the resolver, not the dead
PR #98 "Step 2.5" skip-on-conflict migration (Feature 060, T025)."""

from __future__ import annotations

import inspect

import chronovista.services.onboarding_service as onboarding


def test_dead_step_2_5_skip_migration_is_removed() -> None:
    src = inspect.getsource(onboarding)
    # The PR #98 no-op migration ran a skip-on-conflict UPDATE. Assert its
    # actual code signature is gone (the literal takeout_user reference is also
    # covered by tests/unit/test_no_identity_literals.py).
    assert "UPDATE user_videos" not in src
    assert "video_id NOT IN (" not in src


def test_load_path_uses_identity_resolver() -> None:
    src = inspect.getsource(onboarding)
    # Identity is obtained from the canonical resolver, not a hardcoded literal.
    assert "IdentityService" in src
    assert ".resolve(" in src
