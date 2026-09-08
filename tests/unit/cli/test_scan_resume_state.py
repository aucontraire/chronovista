"""Unit tests for the scan resume-state file (#291, T011)."""

from __future__ import annotations

import pytest

from chronovista.cli import scan_resume_state as st


@pytest.fixture(autouse=True)
def _tmp_state(tmp_path, monkeypatch):
    # Point the state file at a temp dir so tests never touch real data_dir.
    monkeypatch.setattr(st.settings, "data_dir", tmp_path, raising=False)
    yield


def _key() -> str:
    return st.compute_scope_key(
        sources=["transcript"],
        entity_type=None,
        entity_ids=None,
        video_ids=None,
        language=None,
        full=False,
    )


class TestScopeKey:
    def test_same_scope_same_key(self) -> None:
        a = _key()
        b = _key()
        assert a == b

    def test_different_scope_different_key(self) -> None:
        a = _key()
        b = st.compute_scope_key(
            sources=["transcript"],
            entity_type="person",  # different scope
            entity_ids=None,
            video_ids=None,
            language=None,
            full=False,
        )
        assert a != b


class TestRoundTrip:
    def test_record_and_read(self) -> None:
        k = _key()
        assert st.read_position(k, "transcript") is None
        st.record_cursor(k, "transcript", "1234")
        pos = st.read_position(k, "transcript")
        assert pos is not None and pos.cursor == "1234" and pos.completed is False

    def test_completed_position_not_returned(self) -> None:
        k = _key()
        st.record_cursor(k, "transcript", "50", completed=True)
        # A completed source has nothing to resume.
        assert st.read_position(k, "transcript") is None

    def test_clear_scope_when_all_complete(self) -> None:
        k = _key()
        st.record_cursor(k, "transcript", "9", completed=True)
        st.clear_scope_if_all_complete(k, ["transcript"])
        # Entry removed; re-read is empty.
        assert st.read_position(k, "transcript") is None

    def test_clear_scope_noop_when_incomplete(self) -> None:
        k = _key()
        st.record_cursor(k, "transcript", "9", completed=False)
        st.clear_scope_if_all_complete(k, ["transcript", "metadata"])
        # transcript not complete + metadata absent -> not cleared
        pos = st.read_position(k, "transcript")
        assert pos is not None and pos.cursor == "9"

    def test_is_source_completed(self) -> None:
        k = _key()
        # Absent -> not completed.
        assert st.is_source_completed(k, "transcript") is False
        # In-progress -> not completed (so resume re-scans from the cursor).
        st.record_cursor(k, "transcript", "9", completed=False)
        assert st.is_source_completed(k, "transcript") is False
        # Completed -> True, so a --resume can skip the finished phase entirely
        # (read_position returns None for it, which would otherwise restart it).
        st.record_cursor(k, "transcript", "9", completed=True)
        assert st.is_source_completed(k, "transcript") is True
        assert st.read_position(k, "transcript") is None


class TestCorruptFile:
    def test_corrupt_file_treated_as_empty(self, tmp_path) -> None:
        (tmp_path / "scan_resume_state.json").write_text("{ not valid json ")
        # No crash; behaves as no saved position.
        assert st.read_position(_key(), "transcript") is None

    def test_missing_file_is_empty(self) -> None:
        assert st.read_position(_key(), "transcript") is None
