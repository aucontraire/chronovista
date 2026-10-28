# Review candidate entities in the browser

The **Candidates** page turns the seed-and-grow suggestion queue into a point-and-click
review loop: generate suggestions, triage them, and approve or reject each one — without
leaving the browser. (The command-line queue is still available; see
[Grow your entity graph](candidate-queue.md).)

## Open the review page

Open **Candidates** from the sidebar. If the queue is empty, the page offers a
**Generate** button rather than sending you to a terminal.

## Generate suggestions

Click **Generate** to start a run. Generation walks your grounded entities' stored
relationships, grounds the candidate names against your videos, scores and triages them,
and fills the queue.

- The run happens in the background: the page stays responsive and shows a **progress bar
  with a percentage** so you can see how far along it is.
- Only one run happens at a time. If a run is already going, the page shows its progress
  instead of starting a second one.
- When the run finishes, the queue and the summary refresh on their own. A run that finds
  no grounded entities to grow from completes immediately and tells you why.
- If a run is interrupted, the page reports it as failed and offers a retry — it never
  gets stuck showing "running" forever.

Re-running is safe: your past approvals and rejections are preserved, and a suggestion
whose identity has since become a real entity is quietly retired.

## Triage the queue

The queue is ranked by plausibility. Narrow it with the filters:

- **Triage bucket** — worth-review, likely-eliminable, or grounds-nowhere.
- **Type** — person, organization, place, and so on.
- **Hide single-token names** — drop one-word names that are usually noise.
- **Possible duplicates only** — show suggestions that collide with an existing name.

Sort by **score**, **corroboration**, or **presence**. The summary panel shows the counts
by status and the pending triage distribution, and stays visible while you filter.

## Inspect a candidate

Open a candidate to see:

- its **signals** — score, how many of your videos it appears in, how many independent
  seeds point at it (its corroboration), and more;
- its **provenance** — which relationships and which of your existing entities produced
  it, each linked to its own page;
- a **View on Wikidata** link, so you can confirm the identity at the source before
  accepting it;
- a **possible-duplicate** note when the name collides with an entity you already have.

Because each suggestion's identity comes straight from a Wikidata statement on an entity
you already trust, there is no list of look-alikes to pick from — you verify the one
pre-resolved identity rather than disambiguating it.

## Approve or reject

- **Approve** creates a grounded entity and tells you the true outcome: created, or
  *already existed* (linked, never duplicated), or that it could not be created. The new
  entity appears on your entity pages right away.
- **Reject** drops the suggestion from the queue; it will not be offered again.

You cannot act on the same candidate twice, and if a candidate was already decided
elsewhere the page says so rather than acting again.

## Claim a candidate's tag footprint

When you approve an entity whose name matches one of your canonical tags, the entity page
shows how many **additional** videos linking that tag would associate — counting only
videos not already linked to the entity. Click **Link** to claim them; the videos appear
under the entity immediately.

Videos tagged with the entity's own name are associated automatically on approval, so the
footprint only offers the extra, variant-spelled tags. A tag already linked to a
*different* entity is shown for information only — to claim it, unlink it first from tag
management.
