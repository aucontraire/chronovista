"""Unit tests for the recovery-provenance model.

These are pure validation tests — no database, no session. They live here rather
than beside the repository integration tests because a model that rejects a
malformed value does so without any I/O, and running them behind a Postgres
fixture would make the suite slower for no added confidence.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from chronovista.models.recovery_provenance import RecoverySourceRecord


class TestPackedSourceRejection:
    """The old `source:detail` convention must not be smuggled back in.

    Packing two facts into one string is what allowed a later pass to destroy
    archive snapshot timestamps along with the attribution. A packed value in
    `source` would recreate that defect silently, so it is refused outright.
    """

    def test_source_containing_a_colon_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="must not contain"):
            RecoverySourceRecord(source="wayback:20210101080938")

    def test_the_error_names_the_column_to_use_instead(self) -> None:
        """A rejection that does not say what to do instead invites a retry."""
        with pytest.raises(ValidationError, match="source_detail"):
            RecoverySourceRecord(source="wayback:20210101080938")

    def test_detail_is_the_place_for_the_identifier(self) -> None:
        rec = RecoverySourceRecord(source="wayback", source_detail="20210101080938")
        assert rec.source == "wayback"
        assert rec.source_detail == "20210101080938"

    def test_a_colon_in_the_detail_is_allowed(self) -> None:
        """Only `source` carries the ambiguity; the detail is free-form."""
        rec = RecoverySourceRecord(source="wayback", source_detail="12:34")
        assert rec.source_detail == "12:34"


class TestNormalisation:
    def test_whitespace_is_trimmed(self) -> None:
        """Third-party payloads have been observed with trailing spaces."""
        rec = RecoverySourceRecord(source="  filmot  ")
        assert rec.source == "filmot"

    def test_a_blank_detail_becomes_absent(self) -> None:
        """Empty and whitespace-only must both mean "no detail", not "".

        A stored empty string would rebuild the packed form as `filmot:`, which
        no reader expects.
        """
        assert (
            RecoverySourceRecord(source="filmot", source_detail="   ").source_detail
            is None
        )
        assert (
            RecoverySourceRecord(source="filmot", source_detail="").source_detail
            is None
        )

    def test_a_blank_source_is_refused(self) -> None:
        """Trimming must not be a route to an empty source."""
        with pytest.raises(ValidationError):
            RecoverySourceRecord(source="   ")


class TestFieldConstraints:
    def test_source_is_required(self) -> None:
        with pytest.raises(ValidationError):
            RecoverySourceRecord()  # type: ignore[call-arg]

    def test_everything_but_source_is_optional(self) -> None:
        """The minimum a pass can honestly claim is "I touched this row"."""
        rec = RecoverySourceRecord(source="sync")
        assert rec.source_detail is None
        assert rec.recovered_at is None
        assert rec.fields_written is None

    def test_source_length_is_bounded_to_the_column(self) -> None:
        with pytest.raises(ValidationError):
            RecoverySourceRecord(source="x" * 51)

    def test_detail_length_is_bounded_to_the_column(self) -> None:
        with pytest.raises(ValidationError):
            RecoverySourceRecord(source="wayback", source_detail="x" * 101)

    def test_fields_written_is_carried_verbatim(self) -> None:
        rec = RecoverySourceRecord(
            source="filmot", fields_written=["title", "duration"]
        )
        assert rec.fields_written == ["title", "duration"]

    def test_the_record_is_immutable(self) -> None:
        """A provenance record describes something that already happened."""
        rec = RecoverySourceRecord(source="wayback", source_detail="20210101080938")
        with pytest.raises(ValidationError):
            rec.source = "filmot"  # type: ignore[misc]

    def test_recovered_at_is_carried_verbatim(self) -> None:
        when = datetime(2022, 10, 1, 23, 20, 17, tzinfo=UTC)
        assert (
            RecoverySourceRecord(source="wayback", recovered_at=when).recovered_at
            == when
        )
