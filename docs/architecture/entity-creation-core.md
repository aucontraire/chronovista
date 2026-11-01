# Entity creation: one shared core

*Explanation — why the five entity-creation paths share a single core, and how that is kept true.*

Named entities come into being through five entry points: the manual `POST /entities`
endpoint, tag→entity classification, candidate approval, the CLI `entities create` command, and
the offline resolution loader. Each used to re-implement the same sequence — normalize, look up a
duplicate, insert, register the canonical alias, maybe trigger enrichment — and over time those
copies drifted apart. The divergence shipped as three separate bugs (a 500 on a name collision
with a non-active entity, the CLI silently title-casing names, and the loader writing grounding
identifiers in a shape readers could not consume).

## The core and the policy seam

All five paths now persist through one orchestrator,
`services.entity_creation.create_and_ground_entity`. The core owns everything the paths share:

- the **all-status duplicate lookup** (a name+type collision is global across active, merged, and
  deprecated entities, so the lookup must see every status);
- the **insert**, through the uniquely-named `NamedEntityRepository.insert_new_entity`;
- the **canonical `NAME_VARIANT` self-alias** (occurrence count 0) and de-duplication of any extra
  aliases by normalized form.

Each caller keeps only its own **policy** — the parts that legitimately differ:

| Path | Reaction on a collision |
|------|-------------------------|
| Manual `POST /entities` | reject with HTTP 409 (naming the existing entity and its status) |
| Candidate approval | supersede the candidate, return the existing entity |
| Tag→entity classify | link the tag to the existing entity |
| CLI `entities create` | reject (print and exit non-zero) |
| Offline loader | skip |

The reaction is supplied as a small `on_conflict` callback, so the core never encodes any
caller's decision. The entity type, the description, and the enrichment mode (a detached task for
request paths, an awaited best-effort fetch for approval, or none for the CLI and loader) are
likewise decided by the caller, not the core.

Two invariants are deliberate: the core performs **no transaction control** (it flushes; the
caller commits or rolls back, preserving the loader's per-batch commits and every `--dry-run`),
and it performs **no network I/O** — enrichment is triggered by the caller after the entity is
persisted, never inside the creation transaction.

Grounding identifiers are built by a single helper, `build_grounding`, which produces the
structured `{id, verified, status}` record every `external_ids` reader expects.

## Keeping it one home

Consolidation decays the moment the next feature adds a sixth path — unless the single-entry-point
rule is mechanically enforced. Three architecture fitness tests
(`tests/unit/architecture/test_entity_creation_fitness.py`) run on every push and fail if:

- an entity is inserted outside the core (`insert_new_entity` appears anywhere but its definition
  and the core's single call);
- a grounding dict is hand-built outside `build_grounding` (at either the `external_ids=` creation
  seam or the `add_external_id(identifier=…)` merge seam);
- a second enrichment-trigger helper is defined.

These are name- and literal-based guards: they catch honest duplication — a new path that creates
an entity the ordinary way — and make it a reviewable diff, not a silent regression. They are not
a security boundary (a determined author can evade any of them by aliasing a name), and they do
not replace review; they promote one high-value invariant from review discipline to an automated
check, following the Constitution's "Single-Source Operations and Fitness Guards" rule.

This change is a pure refactor: no database schema change, no new dependency, and no change to any
API or CLI contract.
