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
entity or promoting an existing tag. It depends only on the **name** — you can ground before
choosing a type, and the match can suggest the type for you.

1. Open **Create Entity** and enter the **name**. You may pick an **entity type** now, or leave
   it and let the match suggest one (see step 3).
2. A **Ground in Wikidata** section searches automatically. It offers a short, ranked list of
   candidates. Each shows what you need to reject a look-alike: a description, the number of
   statements and linked reference pages, a **stub** warning for machine-generated items, and —
   once you have chosen a type — a **Type match** check against it.
3. Select the correct candidate. It shows as **Grounded to …**. If you have not chosen a type,
   the match's **suggested type** (from its own Wikidata classification) is pre-selected for you
   to confirm or change; when Wikidata offers no confident type, the selector is left for you to
   pick. If the description field is empty, the dialog also offers to prefill it from the match
   (you can edit or clear it).
4. Click **Create Entity**. The identifier is stored as **verified**.

Grounding is always optional. If no candidate is right, if the search finds nothing, or if
Wikidata is slow or unreachable, just create the entity — it is saved **ungrounded** and can
be grounded later. Grounding never blocks creation.

!!! note "Approving is deliberate"
    A single exactly-named hit can still be the wrong subject — a namesake, a work named
    after a person, a calendar date. Nothing is applied until you select a candidate, so read
    the signals (statement count, sitelinks, the type-match check) before approving.

---

## Re-link or refresh an entity after creation

Grounding is not only a create-time decision. On an entity's detail page, the **Enrichment**
section offers two actions so you can correct a wrong link or pull fresh facts without
re-creating the entity.

### Change link

Use this when an entity is linked to the wrong subject (a namesake, a work named after a
person) or was created ungrounded.

1. On the entity page, open **Change link** in the Enrichment section.
2. The same **Wikidata match picker** appears as on create — it searches, ranks candidates,
   and shows the type-match check, statement count, sitelinks, and stub warning.
3. Select the correct candidate. The description field **pre-fills from the match** and stays
   editable; if the match has no description the field is **empty** (it never silently keeps
   the old one). Edit or clear it as you like.
4. Confirm. The link, description, facts, and secondary DBpedia link update **together**.

The previous match's facts are **never shown against the new link**: on confirm the old facts
are cleared and the new ones are fetched in the background, so the page shows the new link
with its facts, or with facts still pending — never a stale mix. The old DBpedia link is
dropped and re-resolved for the new subject.

### Refresh

Use this when an entity is correctly linked but its facts are missing (an earlier fetch
failed) or stale (the source has since changed).

1. **Refresh** appears in the Enrichment section only when the entity already has a Wikidata
   link — there is nothing to refresh otherwise.
2. Click it. The facts are re-fetched from the entity's **current** link. The link and the
   description are left untouched.

A refresh **fully replaces** the fact set (facts removed upstream disappear), and repeated
refreshes converge to the same result. The facts you already have stay visible until the new
ones arrive, so if the knowledge base is briefly unreachable you keep what you had rather than
seeing the entity go blank.

Both actions are recorded in the entity's operation history with the previous link, the new
link, and which of {link, description, facts} changed — so a re-ground is traceable and
reversible in review. Neither action ever changes the entity's name, aliases, detected
mentions, or tag associations.

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

Grounding an entity in the app stores the **identifier** immediately, and its **properties**
(occupation, country, dates, and so on) are then fetched **in the background** — they appear on the
entity's detail page moments later, without you reloading. The create action itself never waits on
this fetch, so grounding stays instant.

If that background fetch cannot reach the knowledge base, the entity simply stays grounded with its
identifier and no properties (no error is shown); the batch resolution pipeline fills them on its
next run. The batch pipeline (landed by `load-enrichment`) remains the source of record for bulk
enrichment. The same background fetch also runs when you **re-link** or **refresh** an entity
after creation (see above), so a single corrected entity fills its facts without waiting for
the next batch run.

### Categories for entities without an English Wikipedia article

A grounded entity whose Wikipedia article exists only in another language — Spanish, French,
Hebrew, Arabic, and so on — used to show no categories, because categories were read from the
English article it does not have. Now the same background fetch reads that entity's foreign-language
article categories and maps each one to its English equivalent, attaching the English categories it
finds and quietly skipping any that have no English counterpart. When the entity has articles in
several languages, the categories from all of them are combined. Because this runs on the same
approval / refresh fetch, pressing **Refresh** on such an entity recovers its categories; a one-time
maintenance backfill applies the same recovery to entities created before this was added. The
recovered categories are stored exactly like English-sourced ones, so the entity takes its place in
the shared-category relationships used to relate entities to one another.

For how the enrichment is stored, see
[Data model](../architecture/data-model.md).
