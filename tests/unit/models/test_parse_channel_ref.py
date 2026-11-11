"""Unit tests for ``parse_channel_ref`` (Feature 109).

Reuses the synthetic 24-char channel id already used in ``youtube_types``' own tests — no
real/library channel id.
"""

from __future__ import annotations

import pytest

from chronovista.models.youtube_types import parse_channel_ref

_VALID = "UCuAXFkgsw1L7xaCfnd5JJOw"


class TestParseChannelRef:
    def test_raw_id_passthrough(self) -> None:
        assert parse_channel_ref(_VALID) == _VALID

    def test_raw_id_stripped(self) -> None:
        assert parse_channel_ref(f"  {_VALID}  ") == _VALID

    def test_channel_url(self) -> None:
        assert parse_channel_ref(f"https://www.youtube.com/channel/{_VALID}") == _VALID

    def test_channel_url_trailing_path(self) -> None:
        assert (
            parse_channel_ref(f"https://youtube.com/channel/{_VALID}/videos") == _VALID
        )

    def test_channel_url_with_query(self) -> None:
        assert parse_channel_ref(f"https://youtube.com/channel/{_VALID}?x=1") == _VALID

    @pytest.mark.parametrize(
        "bad",
        [
            "@somehandle",
            "https://youtube.com/@somehandle",
            "https://youtube.com/c/SomeCustomName",
            "https://youtube.com/user/legacyname",
            "PLnotachannelidatall1234",
            "UCtooshort",
            "",
        ],
    )
    def test_rejects_non_channel_refs(self, bad: str) -> None:
        with pytest.raises((ValueError, TypeError)):
            parse_channel_ref(bad)
