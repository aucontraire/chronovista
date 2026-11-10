# Channel cast: who fronts a channel

A person who hosts or regularly contributes to a channel is associated with
*every* video on it. But the system can only learn that from the text of each
video — so without help it re-learns the same fact once per video, badly, forever.
The **channel cast** model records it once, as a channel-level fact, and this page
explains what that fact is, what it is deliberately *not*, and the rules that keep
it from turning a channel-level guess into a per-video claim.

It builds on [the knowledge model](knowledge-model.md): a cast link is a fact about
a channel, assembled from all three provenance spaces, and the never-union rule
governs it exactly as it governs the entity layer.

## Two different relations, kept apart

"Owner" conflates two claims the data separates, so the system models them
separately:

- **Operates** — *entity E operates channel C.* An imported assertion (a knowledge
  base lists the channel against the entity). It is not person-specific: an
  organisation, a place, or a person can operate a channel. See
  [channel ownership](../user-guide/channel-ownership.md) for how to read it.
- **Cast** — *person P fronts channel C.* A person who hosts, co-hosts, or
  recurs as a contributor. This is person-only, and it is assembled from
  observation and human decision, not merely imported.

Ownership *seeds* cast where an operator is a person, but the two never collapse:
an organisation operates a channel; it is not a member of its cast.

## A cast link lives in all three provenance spaces

| Space | For a cast link |
|---|---|
| **Imported** | the operator link, where a knowledge base happens to list one |
| **Observed** | a corpus signal — a person **credited** on a channel's videos (in tags or in the title/description text) but **not spoken** in the transcript reads as present-but-not-announced, the signature of a host rather than a discussed subject |
| **Decided** | a person's review of what that evidence means — the terminal fact |

The observed signal is only a *candidate generator*. It cannot, on its own, tell a
host from a frequently-discussed guest or a pasted boilerplate name — so the signal
proposes, and a human decides.

## The rule that matters most: a channel fact is never a video fact

**A cast link asserts nothing about any individual video.** A host is absent from a
meaningful fraction of their own channel's videos — guest-hosted episodes, clips,
archival re-uploads — so presence is established per video, from that video's own
text, and is never inherited from the channel-level link. Nothing reads "P is cast
of C" as "P appears in video V" and writes a per-video mention from it; doing so
would mint false associations wholesale, in rows indistinguishable from real ones a
release later — the exact conflation the [never-union rule](knowledge-model.md)
exists to prevent, arriving one level up.

What the link powers instead is channel-level: showing who fronts a channel, and
making a channel's whole catalogue reachable from its cast — without claiming each
video individually.

## "Not cast" is four different answers, not one

A person the detector surfaces but who is *not* a current host can be so for
distinct reasons, and collapsing them to a yes/no throws away the distinction that
motivated the cast model. The verdict is a **versioned category**:

- **cast** — a host, co-host, or recurring contributor. The only verdict that
  becomes a live cast link.
- **recurring guest** — appears as an interviewee, but is not *of* the channel.
- **credited subject** — discussed or credited in standing text, but not a
  participant at all.
- **stuffing** — a boilerplate or SEO name that does not reflect the content; this
  feeds the channel-stuffing detectors, not the cast.

A name credited across a channel's descriptions is not evidence of hosting in
proportion to its volume: boilerplate and standing credit *scale with support*, so
the highest-evidence rows include some of the clearest non-cast cases. Evidence
volume ranks candidates; it does not classify them. The classification is the human
verdict.

## Cast has tenure: current is not the same as all-time

People leave. A founder pushed out, a co-host who departs — each was genuinely cast
during a window and is not cast now. A cast link therefore carries a **tenure**: an
observed first- and last-seen, and a decided *end* (absent while the person is
current). One table then serves both a **current roster** (ending no tenure) and an
**all-time** one (tenure included), and a departed host is recorded honestly as
"cast, ended" rather than forced to be either a current member or a non-member.

Detecting that someone has left is only *partly* mechanical. When a channel goes
quiet on a departed member, the gap in the data dates the departure on its own. When
the channel keeps naming them — because they remain newsworthy, or a public falling-out
keeps their name in circulation — there is no gap, and only outside knowledge dates
the exit. The first case a signal can catch; the second needs a person. It is the
same division the verdict itself has: the observable part is cheap, the judgment is
irreducibly human.

## Standing rules

- A cast link is a channel-level fact; never derive a per-video mention from it.
- Ownership (any entity type) and cast (person) are different relations; seed one
  from the other, never merge them.
- The verdict is a versioned category, not a boolean — "not cast" has four meanings.
- Evidence volume ranks candidates; it never classifies them. A high-support
  candidate is not a safer one.
- A reviewed candidate is terminal: record the decision so a later pass never
  re-proposes it, whatever the verdict was.
- Cast has tenure: distinguish current from former rather than dropping the departed.

## See also

- [The knowledge model](knowledge-model.md) — the three provenance spaces and the
  never-union rule this model rests on.
- [Channel ownership](../user-guide/channel-ownership.md) — how to see which channels
  an entity operates, and who operates a channel.
- [Novel-relationship discovery](relationship-discovery.md) — the sibling pattern:
  a corpus signal that proposes candidates for human review, never asserts them.
- [Tags and aliases](tags-and-aliases.md) — why a tagged name and a spoken name are
  different evidence, which is what the cast signal reads.
