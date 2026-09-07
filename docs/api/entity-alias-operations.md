# Entity Alias Operations

> **Version**: 1.0.0
> **Last Updated**: 2026-09-06

Reference for deleting an alias (with mention retraction), undoing that deletion, and the
backfill that records historical alias→mention links. All routes require authentication
(same dependency as the other `/entities` routes).

---

## DELETE /api/v1/entities/{entity_id}/aliases/{alias_id}

Delete an alias and its auto-detected associations, as a **reversible** operation.

- Removes the entity's auto-detected (`rule_match`) mentions of the alias — preferring the
  recorded `alias_id` provenance link, falling back to the case/accent fold for un-linked rows
  (keeping mentions another surviving alias still covers).
- **Preserves** hand-made (`manual`) and correction-derived (`user_correction`) mentions.
- Recomputes the entity's mention/video counters.
- Records one `alias_delete` operation capturing the removed alias + mentions.

### Response — 200 OK

```jsonc
{ "data": {
    "id": "…", "alias_name": "…", "alias_type": "name_variant",
    "occurrence_count": 7, "case_sensitive": false,
    "removed_mention_count": 5,
    "operation_id": "…"        // pass to the undo route to reverse this deletion
} }
```

### Errors

- **404** — no such entity, or the alias is not owned by it (RFC7807).

---

## POST /api/v1/entities/operations/{operation_id}/undo

The existing entity-operation undo route, which also reverses an `alias_delete` operation:
re-creates the alias and re-inserts the removed mentions, then recomputes counters. No body.

### Response — 200 OK

Returns the restored entity detail (same shape as `GET /api/v1/entities/{entity_id}`).

### Errors

- **404** — the operation (or its entity) no longer exists.
- **409** — the operation was already undone, **or** restoring the alias would collide with an
  alias created since the deletion (nothing is restored — no partial state).

A removed mention whose transcript segment has since been deleted is skipped on restore; the
alias and all still-valid mentions are restored and the call still succeeds.

---

## CLI: `chronovista entities backfill-alias-links`

One-time backfill that records the alias→mention link on historical auto-detected mentions.

- Links each `rule_match` mention with no recorded alias to the entity alias whose folded name
  matches it — only where that fold maps to exactly **one** alias (ambiguous folds stay NULL).
- Never touches manual or correction-derived mentions. Idempotent.

```bash
chronovista entities backfill-alias-links            # dry-run: reports linked / remaining
chronovista entities backfill-alias-links --apply    # write the links
```

For the model and the invariants, see
[Alias→mention provenance & undoable deletion](../architecture/entity-alias-provenance.md).
