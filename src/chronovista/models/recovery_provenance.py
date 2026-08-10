"""Models for recovery provenance — ADR-011.

One record per (target, source) saying that a given archive source contributed
metadata to a deleted video or channel. Append-only: a later pass adds a row, it
never replaces an earlier one.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RecoverySourceRecord(BaseModel):
    """One source's contribution to one target.

    ``source`` and ``source_detail`` are separate on purpose. The previous
    convention packed both into a single string (``wayback:20210101080938``),
    which is why a later pass overwriting that column destroyed the snapshot
    timestamps along with the attribution.
    """

    model_config = ConfigDict(frozen=True)

    source: str = Field(
        min_length=1,
        max_length=50,
        description="Which route produced this data: takeout | wayback | filmot | sync",
    )
    source_detail: str | None = Field(
        default=None,
        max_length=100,
        description=(
            "Source-specific identifier, e.g. a Wayback snapshot timestamp. "
            "Never packed into `source`."
        ),
    )
    recovered_at: datetime | None = Field(
        default=None,
        description="When this source contributed. Defaults to now() in the database.",
    )
    fields_written: list[str] | None = Field(
        default=None,
        description=(
            "Which columns this pass actually wrote. Best-effort: a pass that "
            "does not populate it still records that it touched the row. "
            "Consumers must treat it as a hint, never a guarantee."
        ),
    )

    @field_validator("source", "source_detail", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        """Trim, and treat an empty string as absent.

        Recovered values arrive from third-party payloads; one observed source
        returns names with a trailing space, and an untrimmed value silently
        breaks later equality checks.
        """
        if isinstance(v, str):
            stripped = v.strip()
            return stripped or None
        return v

    @field_validator("source")
    @classmethod
    def _reject_packed_source(cls, v: str) -> str:
        """Refuse the old packed form outright.

        ``wayback:20210101080938`` in ``source`` would recreate the exact defect
        this table exists to prevent, and it would do so silently — the row
        would look fine and the timestamp would be unqueryable. Failing loudly
        is the point.
        """
        if ":" in v:
            raise ValueError(
                f"source must not contain ':' (got {v!r}); "
                "put the identifier in source_detail instead"
            )
        return v
