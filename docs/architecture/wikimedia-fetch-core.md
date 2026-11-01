# Wikimedia fetch: one shared transport

*Explanation — why the five Wikidata/DBpedia/MediaWiki services share one transport, how a transient failure is told apart from a genuine absence, and how the single entry point is kept true.*

The application enriches named entities from external knowledge sources: Wikidata (its action
API and SPARQL), DBpedia (SPARQL), and MediaWiki/Wikipedia (categories, category sizes, page
images). Five async services did this, and each had grown its own copy of the same
outbound-HTTP scaffolding — the `User-Agent`, the per-request client, the rate-limit/backoff
handling, the "reached but no data" versus "could not reach" distinction, request batching, and
multi-page continuation. Copied rather than shared, the copies drifted, and the drift was not
cosmetic: one service had no retry at all, the safeguard that distinguishes a transient server
error from a real absence lived in only one of them, and the backoff limits disagreed.

## One transport, thin clients

All five services now compose a single `services.wikimedia_transport.WikimediaTransport`. The
transport owns everything that was duplicated:

- the **outbound identity** — one `wikimedia_user_agent(component)` template producing
  `chronovista/<version> (<contact-url>; <label>)`, with a per-service label;
- the **client lifecycle** — a fresh client per request by default, an injected client when a
  caller owns the event loop, and a `run_sync` entry (a future synchronous caller gets a fresh
  loop and client per call, never a module-level client bound to a dead loop);
- the **unified retry/backoff** — a `Retry-After` header honored but capped, otherwise bounded
  exponential backoff, up to three attempts, covering rate limits, server errors **and** transient
  transport errors (timeouts, connection resets);
- the **unreachable-vs-empty contract** (below);
- the single **chunking** helper and the single **MediaWiki continuation** helper (with the
  `normalized`/`redirects` hop re-attribution that prevents false-zero category results).

Each service keeps only what legitimately differs: its endpoint and host, its request
parameters, and its response parsing. None performs its own HTTP scaffolding.

## Unreachable is not absent

The transport raises one signal, `WikidataUnavailable`, when a fetch *failed* — a transport
error, exhausted retries, a non-JSON HTTP 200 body, or an API error object returned inside an
HTTP 200 body. It returns data when the source was *reached*, even if the data is empty. That
distinction is the whole point: a transient outage recorded as "nothing found" silently degrades
the knowledge graph.

The raise is an **internal** contract between the transport and its thin clients, not a contract
with the rest of the application. Each client makes a deliberate choice:

| Service | On unreachable | Returns | Distinction recorded |
|---------|----------------|---------|----------------------|
| Wikidata client | propagate | raises `WikidataUnavailable` | the caller (its API boundary already exposes an `unavailable` flag) |
| DBpedia resolver | absorb | `None` | a `WARNING` log in `resolve()` |
| entity-category fetch | absorb | omits the title's key | operator batch report |
| category-size | absorb | omits the name's key | operator batch report |
| page-image fallback | absorb | `ERROR` outcome | its outcome enum |

Only the Wikidata client lets the signal escape; the others absorb it into their existing
fallback value. Crucially, none of them *persists* a false absence — every caller skips and
stays eligible for a later pass.

## Why the retry matters more than it looks

The enrichment that runs when an entity is approved is a one-shot, detached background task. A
docstring long claimed a failure there was harmless because "the next batch run" would backfill
it — but there is no scheduled sweeper. So before this change, a momentary DBpedia timeout during
those few seconds did not defer the link; it lost it until a human manually re-grounded the
entity. The transport's bounded retry is therefore not a nicety — it is the only retry that path
will ever get, which is why it must cover timeouts and connection resets (DBpedia's usual failure
mode), not just HTTP status codes.

## Keeping it one home

Three architecture fitness tests, run on every push, keep the single entry point from eroding the
way the five copies did:

- the `User-Agent` is assembled in exactly one site (the template) — the load-bearing,
  exact-count guard, because every request must carry the single-sourced identity, so a
  hand-rolled bypass must assemble its own and trips it;
- MediaWiki `clcontinue` continuation appears in exactly one site (the shared helper);
- Wikimedia host/endpoint literals stay within the fetch layer — a supporting heuristic, not the
  guarantee.

Each guard was mutation-verified (shown to fail on a planted bypass, then pass). The honest limit,
stated in the guard module itself: name-based guards catch *honest* duplication — a new request
that assembles a `User-Agent` the ordinary way — not deliberate evasion. The goal is a reviewable
diff that reads "this adds a second place that talks to a Wikimedia endpoint," not a security
boundary.

This is Phase B1. The offline resolution scripts still have their own copies of this scaffolding;
routing them through the transport (via its `run_sync` entry) is deferred to a later phase, and
the fitness guards — which scan tracked source only — do not reach them.
