"""Tests for AppIdentity Pydantic models (Feature 060, T010)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from chronovista.models.app_identity import (
    LOCAL_USER_ID,
    AppIdentity,
    AppIdentityCreate,
    AppIdentitySource,
    AppIdentityUpdate,
)


class TestAppIdentitySource:
    def test_values(self) -> None:
        assert AppIdentitySource.CHANNEL.value == "channel"
        assert AppIdentitySource.LOCAL_CONSTANT.value == "local_constant"

    def test_is_str_enum(self) -> None:
        # (str, Enum) for JSON-serialization safety
        assert isinstance(AppIdentitySource.CHANNEL, str)


class TestLocalUserConstant:
    def test_local_user_id_is_documented_constant(self) -> None:
        assert LOCAL_USER_ID == "local_user"

    def test_fits_user_id_column_width(self) -> None:
        # app_identities.user_id / user_videos.user_id are varchar(50)
        assert len(LOCAL_USER_ID) <= 50

    def test_is_valid_user_id(self) -> None:
        # Must pass UserId validation (non-empty) when used in a model
        model = AppIdentityCreate(
            user_id=LOCAL_USER_ID, source=AppIdentitySource.LOCAL_CONSTANT
        )
        assert model.user_id == "local_user"


class TestHierarchy:
    def test_create(self) -> None:
        m = AppIdentityCreate(
            user_id="UCzYTmeK-6v3DcJ6hzRh1q9w", source=AppIdentitySource.CHANNEL
        )
        assert m.source is AppIdentitySource.CHANNEL

    def test_update_defaults_none(self) -> None:
        m = AppIdentityUpdate()
        assert m.user_id is None
        assert m.source is None

    def test_full_from_attributes(self) -> None:
        now = datetime.now(UTC)
        m = AppIdentity(
            id=1,
            user_id="UCzYTmeK-6v3DcJ6hzRh1q9w",
            source=AppIdentitySource.CHANNEL,
            created_at=now,
            updated_at=now,
        )
        assert m.id == 1
        assert m.model_config.get("from_attributes") is True

    def test_rejects_empty_user_id(self) -> None:
        with pytest.raises(ValidationError):
            AppIdentityCreate(user_id="   ", source=AppIdentitySource.CHANNEL)
