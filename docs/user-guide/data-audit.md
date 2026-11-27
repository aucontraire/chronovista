# Check your data before and after a change

`chronovista audit-invariants` checks that your library's data obeys the rules chronovista depends on, and tells you,
for each rule, whether it holds or how many rows break it. Use it as a gate around anything that changes data in bulk:
a repair, a full rescan, a batch correction, a backfill.

The audit only reads. The database itself refuses writes for the whole run, and every check sees the same moment of
your data, even while the app is in use. You can run it against your real library at any time.

Each check verifies one rule in the [system invariants](../architecture/invariants.md) register. That page explains
what each rule means and why it exists.

## See what your library looks like now

```bash
chronovista audit-invariants
```

```text
Invariant audit — 10 checks, 2026-11-27 16:20 UTC

  VIOLATED  T1-correction-flag           80           (0.6s)
  holds     C3-entity-counters                        (1.2s)
  ...

5 hold · 5 violated · 0 error
```

A full run takes a couple of minutes on a large library. Most of that is `M1-mention-reads`, which reuses the mention
repair's own analysis. To run only some checks, name them, or name a register entry to run all of its checks:

```bash
chronovista audit-invariants --check G1-alias-placement
chronovista audit-invariants --check T1        # both T1 checks
chronovista audit-invariants --list            # every check and its rule; runs nothing
```

## Gate a change: save, change, compare

A total on its own can hide harm. A repair that fixes 10 rows and breaks 3 others shows a smaller total, which looks
like progress. Compare against a saved run instead, which names exactly what is new:

```bash
# 1. Before the change
chronovista audit-invariants --save backups/audit-before.json

# 2. The change, for example
chronovista entities repair-mentions

# 3. After it
chronovista audit-invariants --compare backups/audit-before.json
```

The comparison reports, for each check, how many violations were resolved and how many are new:

```text
  T1-correction-flag     resolved 80   new 0
  G1-alias-placement     resolved 0    new 2   e.g. 0193…, 0193…
```

It **fails when anything is new**, even if that check's total went down. Violations that were already there before
the change don't fail it, so a known problem doesn't block unrelated work.

**Keep saved runs out of the repository.** They hold the keys of the rows that break each rule, and some keys are video
IDs from your library. `backups/` is ignored by git. The command refuses to save into a tracked folder unless you pass
`--force`.

## Read the result

| Exit status | Meaning |
|---|---|
| 0 | Every check holds; with `--compare`, nothing is new |
| 1 | A rule is broken; with `--compare`, something is new |
| 75 | A check could not run, or (with `--compare`) a check could not be compared and is broken now |
| 2 | The command was used wrongly: an unknown check, an unreadable baseline, or a missing folder |

**A check that could not run** shows `ERROR` with the database's reason, such as a statement that ran past the time
limit. It never shows as `holds`: a check that didn't run must never look clean. The other checks still run.

**"Not compared"** means the check can't be compared with the saved run. The reason is shown:
- it is new since then;
- it errored in one of the two runs;
- its rule has changed since the run was saved (rule changed: v1 → v2).

Save a fresh baseline before the next change.

**Keys** in the comparison are internal row IDs. Keys built from video IDs (the transcript checks) are hidden unless you
pass `--show-keys`, so the output is safe to paste. With `--show-keys`, don't paste it anywhere public.

## Where the checks come from

Each check uses the rule the application itself uses. For example, the entity counters are compared with a recount by
the exact function that writes them, and the stored transcript text by the rule that rebuilds it. A check therefore
can't disagree with the code it watches. The [register](../architecture/invariants.md) names each rule's home.
