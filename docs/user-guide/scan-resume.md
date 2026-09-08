# Interrupt and resume an entity scan

An entity-mention scan over a large library can run for a long time. This guide
covers how to stop one safely and pick it up again without losing work or
re-doing what already finished.

## What changed

The scan **commits as it goes** — after every batch, not once at the end. Two
things follow from that:

- **Stopping is safe.** Press `Ctrl+C` and every batch committed so far is kept.
  There is no multi-hour transaction to roll back, and no half-written state.
- **Resuming is cheap.** A `--resume` run continues from the last committed
  position instead of starting over. At most one batch is repeated.

## Stopping a scan

Press `Ctrl+C` once. The scan finishes the batch it is on, commits it, and exits
cleanly — no traceback. It prints how far it got and reminds you how to resume:

```text
Scan interrupted — committed work was kept.
Re-run with --resume to continue where it left off.
```

The progress line shows the live position (a segment id, or a video id for
title/description scans), so you can see what a resume will skip.

## Resuming

Re-run the **same command** with `--resume` added:

```bash
chronovista entity scan --resume
```

```bash
# Whatever scope you started with, repeat it and add --resume:
chronovista entity scan --sources transcript,title,description --full --resume
```

!!! important "Resume matches the original scope"
    The saved position is keyed to the scan's **scope** — its sources, entity
    filters, entity type, video filter, language, and whether `--full` was set.
    A `--resume` only continues a run whose scope matches. If you change any of
    those, it is a different scope: the run starts fresh rather than resuming the
    wrong position. Repeat the original flags exactly.

When every requested source finishes, the saved position is cleared
automatically. The next plain run (no `--resume`) starts a fresh scan.

### Combined source scans

A scan over several sources (for example `--sources transcript,title`) tracks
each source independently. If the transcript phase finishes and you interrupt
during the title phase, a `--resume` **skips the completed transcript phase** and
continues the title phase from where it stopped.

## Notes and edge cases

- **`--resume` with `--dry-run` does nothing.** A dry run writes no mentions and
  saves no position, so there is nothing to resume.
- **`--limit` still applies per invocation.** It bounds the work of the current
  run; a later `--resume` continues past that bound.
- **A missing or unreadable resume file is not an error.** The scan warns and
  starts fresh rather than failing or resuming from a bad position.
- **`--full` stays safe under interrupt.** A full re-scan deletes and re-derives
  its mentions one batch at a time, committed together, so no segment is ever
  left with its old mentions removed and the new ones not yet written — even if
  you stop midway. Manually added mentions are never touched.
