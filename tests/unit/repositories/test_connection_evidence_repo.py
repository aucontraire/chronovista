"""Pure tests for ``EntityMentionRepository.non_transcript_basis`` (Features 114, 118).

The evidence panel's empty state names the non-transcript source a pair co-occurs through
(FR-012). The SQL paths behind the panel are crossed against a real database in
``tests/integration/api/test_pair_passages_api.py``.
"""

from __future__ import annotations

import uuid

from chronovista.repositories.entity_mention_repository import EntityMentionRepository

A = uuid.UUID("00000000-0000-0000-0000-00000000000a")
B = uuid.UUID("00000000-0000-0000-0000-00000000000b")
OTHER = uuid.UUID("00000000-0000-0000-0000-00000000000c")


class TestNonTranscriptBasis:
    def test_none_when_no_shared_non_transcript_video(self) -> None:
        triples = [(A, "v1", "title"), (B, "v2", "title")]
        assert EntityMentionRepository.non_transcript_basis(triples, A, B) is None

    def test_names_shared_source(self) -> None:
        triples = [(A, "v1", "description"), (B, "v1", "description")]
        assert (
            EntityMentionRepository.non_transcript_basis(triples, A, B) == "description"
        )

    def test_never_reports_transcript(self) -> None:
        triples = [(A, "v1", "transcript"), (B, "v1", "transcript")]
        assert EntityMentionRepository.non_transcript_basis(triples, A, B) is None

    def test_sources_must_match_on_the_same_video_and_source(self) -> None:
        # A via title on v1, B via tag on v1: different sources -> no shared basis.
        triples = [(A, "v1", "title"), (B, "v1", "tag")]
        assert EntityMentionRepository.non_transcript_basis(triples, A, B) is None

    def test_priority_order_title_before_tag(self) -> None:
        triples = [
            (A, "v1", "tag"),
            (B, "v1", "tag"),
            (A, "v2", "title"),
            (B, "v2", "title"),
        ]
        assert EntityMentionRepository.non_transcript_basis(triples, A, B) == "title"

    def test_ignores_unrelated_entities(self) -> None:
        triples = [(OTHER, "v1", "title"), (A, "v1", "title")]
        assert EntityMentionRepository.non_transcript_basis(triples, A, B) is None
