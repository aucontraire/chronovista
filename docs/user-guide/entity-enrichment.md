# Ground an entity in a knowledge base

An entity in your library is a name and a type. **Grounding** attaches it to a public
knowledge base — Wikidata, and through it DBpedia — so it carries a stable identifier and,
once the resolution pipeline has run, a set of facts: occupation, country, dates, external
handles, and so on. This page shows how to ground an entity as you create it, how to land the
captured facts into the database, and what to expect on the entity's page.

---

## What grounding gives you

The entity detail page has an **Enrichment** section with two parts:

| | What it holds | Where it comes from |
|---|---|---|
| **External identifiers** | links to the entity on Wikidata / DBpedia, with a **Verified** badge when a human confirmed the match | set when you ground the entity, or by the pipeline |
| **Properties** | the grounded facts (occupation, country, birth date, categories, …) with their provenance | the batch resolution pipeline only |

An entity with neither reads as **not grounded** — not an error, just nothing linked yet.

---

## Ground an entity while creating it

Grounding is offered on the **Create Entity** dialog, whether you are creating a standalone
entity or promoting an existing tag. It depends only on the name and type — not on whether a
tag exists.

1. Open **Create Entity**, enter the **name**, and pick an **entity type**.
2. A **Ground in Wikidata** section appears and searches automatically. It offers a short,
   ranked list of candidates. Each shows what you need to reject a look-alike: a description,
   a **Type match** check against the type you chose, the number of statements and linked
   reference pages, and a **stub** warning for machine-generated items.
3. Select the correct candidate. It shows as **Grounded to …**, and — if the description
   field is empty — offers to prefill it from the match (you can edit or clear it).
4. Click **Create Entity**. The identifier is stored as **verified**.

Grounding is always optional. If no candidate is right, if the search finds nothing, or if
Wikidata is slow or unreachable, just create the entity — it is saved **ungrounded** and can
be grounded later. Grounding never blocks creation.

!!! note "Approving is deliberate"
    A single exactly-named hit can still be the wrong subject — a namesake, a work named
    after a person, a calendar date. Nothing is applied until you select a candidate, so read
    the signals (statement count, sitelinks, the type-match check) before approving.

---

## Load the captured enrichment

The rich **Properties** come from the resolution pipeline, which exports what it found to a
ledger file. Land that into the database with:

```bash
chronovista entities load-enrichment --ledger data/entity-resolution/entities.json
```

This is a **dry run** — it reports what it would do and never writes. Add `--apply` to write:

```bash
chronovista entities load-enrichment --ledger data/entity-resolution/entities.json --apply
```

The load is safe to re-run: it is idempotent (an unchanged export changes nothing), it
refreshes by full replacement (a fact removed upstream does not linger), and it only writes
enrichment — it never overwrites a human-edited display name or description. It also reports
whether the export covers every active entity, so a **stale partial snapshot** is flagged
rather than reported as a silent success.

!!! warning "Check the database target first"
    In development mode the connection can resolve to the development database even when you
    intend production. Confirm the effective target before `--apply`, and take a backup — the
    load mutates real data.

---

## What is filled now, and what is filled later

Grounding an entity in the app stores the **identifier** immediately, but not the property
set. The properties are produced by the batch resolution pipeline and landed by
`load-enrichment`. So a freshly grounded entity shows its verified identifier right away and
its properties after the next pipeline run — it does not fill in on its own in the background.

For how the enrichment is stored, see
[Data model](../architecture/data-model.md).
