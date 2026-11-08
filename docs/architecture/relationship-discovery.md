# Novel-relationship discovery

The novel-relationship candidate queue proposes pairs of entities that your corpus
connects but your imported knowledge graph does not. This page explains what a
candidate is, what it is *not*, and the rules that keep the queue from quietly
turning corpus statistics into asserted facts. For the commands and the browser
surface, see [Find novel relationships](../user-guide/relationship-candidates.md).

The queue only makes sense against the three spaces described in
[The knowledge model](knowledge-model.md): it is an instrument pointed at the gap
between the imported typed skeleton and the observed corpus layer.

## A candidate is a subtraction

A pair enters the queue when both halves hold:

1. **The corpus connects them.** They co-occur across videos often enough, and more
   often than their individual frequencies would predict.
2. **The knowledge graph does not.** No stored relationship explains the pair.

Neither half is interesting alone. Frequent co-occurrence without the second half is
just two popular entities; a missing edge without the first half is most of the
graph. The queue is the intersection, which is why it cannot blur the typed/observed
boundary — it is defined *by* that boundary.

### How "the corpus connects them" is measured

Co-occurrence is ranked by **lift** — the observed overlap divided by the overlap
expected if the two entities were independent. A raw shared-video count cannot be
used, because in a library with a savage size distribution a raw count ranks by
*size* and reads as relevance: the biggest entities co-occur with everything. Lift is
symmetric, needs no per-subject threshold, and orders a page identically to
directional specificity.

Two consequences worth knowing before reading the numbers:

- **Lift's maximum is bounded by support.** For a fixed corpus, the highest
  achievable lift falls as the shared count rises, so sorting by lift alone pulls
  minimum-support pairs toward the top. This is a variance effect, not a bias: the
  top of the queue is *more mixed* than the middle, not systematically wrong.
- **A support floor is the wrong fix.** Raising the minimum shared count removes the
  densest band of genuinely supported pairs along with the noise. Ranking and
  secondary sorting are the right instruments; filtering is not.

### How "the knowledge graph does not" is decided

Three independent arms, all reading the pair's own stored properties:

- **Direct edge** — either entity's relationships name the other.
- **Shared membership** — both belong to the same organisation, work, or group.
- **Shared attribute referent** — both point at the same referent on an attribute
  that implies a relationship.

Shared referents are capped: a referent held by many library entities is a *hub* and
does not disprove novelty. The cap bounds hub size; it does not decide meaning — a
referent with few holders can still be relationally empty.

One arm is **not** implemented: nothing checks whether a *third* entity names both
halves. A pair related only through an inbound holder therefore passes the filter
and appears as novel when it is not.

## Why the queue is read-only

There is no write verb in the API and no verdict surfaced in the UI. Generation is an
operator command and the only writer. That is deliberate: a queue that can be
approved is a queue that writes somewhere, and *where* is the decision this feature
deliberately did not make. The measurement is useful on its own, and shipping the
measurement without the write keeps the hard decision unforced.

## Three kinds of novelty, which need different answers

The most important thing to understand about the queue is that "novel" is not one
thing. A candidate the filter accepts can be novel for three reasons, and they belong
to three different spaces.

**The knowledge base is incomplete.** A relationship that genuinely exists in the
world and is genuinely missing upstream. This is the case the queue was built to
find. The honest home for a fix is upstream, or a local overlay explicitly marked as
locally asserted.

**The knowledge base models it differently.** The relationship is *derivable* from
the imported graph by a short path, but no direct edge exists because the upstream
model does not assert one. Two people credited on the same work are the canonical
example: the credit relations run person-to-work, so two co-credited people never
have a direct edge between them — by design, not by omission. These pairs are
**structurally** novel and **substantively** known. On a reviewed sample they
dominate the top of the queue.

Approving them would write facts the upstream model deliberately declines to assert.
What they actually indicate is a *traversal* gap, not a knowledge gap: the finding
belongs in a two-hop query, not in a store of relationships.

**The co-occurrence is topical only.** Two entities that recur together because the
corpus is about a subject both touch. Real, useful for navigation, and not a
relationship. This belongs in the observed layer and nowhere else.

A boolean approve/reject cannot express that distinction, which is why **the verdict
vocabulary is a versioned category rather than a boolean** — and why that is an
architectural requirement rather than a UI nicety. The categories map onto which
space the finding belongs to.

## What an approval may and may not write

The rule, to be satisfied by any future review surface:

> A verdict is a **human decision** with its own provenance, in its own space. It
> never writes into the representation that holds imported assertions.

If an approval wrote a relationship into the imported graph's own property
representation, then within one release nothing would distinguish "the knowledge base
asserts this" from "I inferred it because two names co-occurred in my videos" — the
exact conflation the typed/observed separation exists to prevent, arriving through a
UI button rather than a schema change.

## Scoping to the head

Support for a candidate thins out with rank, and below a measured boundary it goes
flat — a long tail at a near-constant low rate that no amount of reviewing improves.
The queue is therefore scoped to its highest-ranked **head**, and the rest of the
rows are **retained in storage** rather than deleted.

The head is defined over the **qualifying population** — every pair meeting the
support floor, and nothing else. It is the globally top-ranked rows of that
population, never of whatever subset a reader has narrowed to.

Three decisions inside that:

- **The cap lives in one place** — the shared read path every consumer funnels
  through — and is applied after ordering, not expressed as a page size. A cap shaped
  like a default `limit` is bypassable by any caller that asks for more.
- **The tail is kept.** Every recalibration of the cutoff so far has been a
  measurement *of the tail*; deleting it would make the next recalibration require a
  full regeneration, which rewrites the very rows being compared. Retention is
  cheaper than the recompute it avoids.
- **Filters select within the fixed head.** Narrowing by support or eligibility
  subsets the head; it never promotes a lower-ranked row into it. Without that
  property a narrow filter silently redefines which rows *are* the head, and a
  parameter documented as filtering rows only ends up deciding head membership. That
  is not hypothetical: measurement found a tight support filter filling most of a
  page with rows from far below the boundary, at roughly a third of the head's
  evidence density.

Ordering within the head ends in a stable identifier. Lift and corroboration both
tie often enough that without a terminal tiebreak the boundary row flickers between
reads, which breaks pagination at exactly the page a reviewer is looking at.

## Reading the queue's numbers honestly

- **A candidate's metrics are only interpretable with its generator version.** The
  novelty filter and the lift metric both evolve; a stored row records which
  generator produced it.
- **Knowledge-base corroboration is evidence, not ground truth.** It means "something
  else in the imported graph also links these two," which raises confidence without
  establishing a relationship.
- **Absence of corroboration is not evidence of unsupportedness.** Measured against
  an independent credit-based signal, the two overlap on only a small fraction of the
  pairs either one supports. They are nearly disjoint, so neither can be read as the
  other's negation.
- **Shared attributes can be weakly positive.** Real collaborators tend to share
  attributes such as nationality, so a shared hub attribute is a mild *positive*
  signal, not a noise marker. Filtering on it was proposed and measurement refuted
  it.

## See Also

- [The knowledge model](knowledge-model.md) — the three spaces and the never-union
  rule this feature depends on
- [Find novel relationships](../user-guide/relationship-candidates.md) — the how-to
- [Seed-and-grow discovery](seed-and-grow.md) — the complementary pipeline, which
  grows the typed skeleton rather than measuring its gaps
- [Data Model](data-model.md)
