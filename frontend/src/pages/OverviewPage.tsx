/**
 * Overview Dashboard (Feature 061, User Stories 2 and 3).
 *
 * Headline metric: "Saved & Forgotten" — videos saved to a curated playlist and
 * never watched. Below it, the breakdown: Watch Later depth, an inventory of the
 * playlist types actually present, and library-wide rollups. An additional
 * navigation destination; it deliberately does not replace the existing landing
 * page (FR-014a).
 *
 * Every figure comes from one request (FR-026), so the numbers on this page are
 * computed together and cannot disagree with each other.
 */

import { Link } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { StatGrid, type StatGridItem } from "../components/StatGrid";
import { useOverview } from "../hooks/useOverview";
import type { Overview, PlaylistTypeCount } from "../api/overview";
import { cardPatterns } from "../styles";

/**
 * Destination for the Saved & Forgotten metric (FR-018, FR-025).
 *
 * `include_unavailable=true` is required, not incidental: the dashboard figure
 * applies no availability condition, while the videos list hides unavailable
 * videos by default. Without it the user clicks 609 and lands on 586 — the 23
 * saved-but-unwatched videos that have since been deleted. A video you saved
 * and never watched is still forgotten even if it is now gone (FR-018b).
 */
const SAVED_FORGOTTEN_HREF =
  "/videos?saved_unwatched=true&include_unavailable=true";

/**
 * Human labels for the playlist types we know about.
 *
 * Deliberately a *lookup with a fallback*, never the source of what to render.
 * FR-021 requires the inventory to show whatever types exist in the data, so a
 * type introduced by a future feature must still appear — humanised from its
 * raw value rather than dropped for want of an entry here.
 */
const PLAYLIST_TYPE_LABELS: Record<string, string> = {
  regular: "Curated playlists",
  watch_later: "Watch Later",
  history: "History",
  liked: "Liked playlists",
  favorites: "Favorites",
};

function playlistTypeLabel(type: string): string {
  return (
    PLAYLIST_TYPE_LABELS[type] ??
    type.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase())
  );
}

function inventoryItems(rows: PlaylistTypeCount[]): StatGridItem[] {
  return rows.map((row) => ({
    label: playlistTypeLabel(row.playlist_type),
    value: row.playlist_count,
    // FR-022, FR-034: system lists are marked with words, not styling alone —
    // a colour or an icon carries nothing to a screen reader or in monochrome.
    ...(row.is_system ? { note: "System list" } : {}),
  }));
}

/**
 * FR-024: membership is never described as watching.
 *
 * "Watched" is reserved for watch-history figures; membership figures say
 * "saved" or "in playlists".
 */
function rollupItems(overview: Overview): StatGridItem[] {
  return [
    { label: "Watched videos", value: overview.rollup.watched_videos },
    {
      label: "Saved in curated playlists",
      value: overview.rollup.saved_curated_videos,
    },
    // FR-023, FR-023a: a video attribute, so it belongs among the video
    // rollups. A `liked` *playlist* is a different quantity from a different
    // table and lives in the inventory above.
    { label: "Liked videos", value: overview.rollup.liked_videos },
  ];
}

function watchLaterItems(overview: Overview): StatGridItem[] {
  const wl = overview.watch_later;
  if (!wl) return [];

  const unwatched: StatGridItem = {
    label: "Unwatched",
    value: wl.unwatched,
    // FR-025: link only when the target is unambiguous; otherwise the figure
    // stays inert rather than pointing somewhere whose count differs.
    ...(wl.playlist_id
      ? {
          href: `/playlists/${wl.playlist_id}?watched_status=unwatched`,
          linkLabel: `View ${wl.unwatched} unwatched videos in Watch Later`,
        }
      : {}),
  };

  return [{ label: "In the queue", value: wl.total }, unwatched];
}

export function OverviewPage() {
  const { overview, isLoading, isError, retry } = useOverview();

  if (isError) {
    // FR-027b: an error must be distinguishable from a legitimately empty
    // library, so this is not a zero card. FR-027c: retry without reload.
    return (
      <div className={PAGE}>
        <OverviewHeader />
        <ErrorState
          title="Could not load your overview"
          message="The library aggregates could not be retrieved."
          onRetry={retry}
        />
      </div>
    );
  }

  const pending = isLoading || !overview;

  return (
    <div className={PAGE}>
      <OverviewHeader />

      {pending ? (
        <div
          className={`${cardPatterns.base} p-6`}
          aria-busy="true"
          data-testid="overview-loading"
        >
          <span className="sr-only">Loading overview…</span>
          {/* FR-027a: a loading state must not look like a zero value. */}
          <div className="animate-pulse" aria-hidden="true">
            <div className="h-4 w-40 bg-slate-200 rounded mb-3" />
            <div className="h-10 w-24 bg-slate-200 rounded" />
          </div>
        </div>
      ) : (
        <Link
          to={SAVED_FORGOTTEN_HREF}
          className={`${cardPatterns.base} ${cardPatterns.hover} ${cardPatterns.focus} ${cardPatterns.transition} block p-6`}
          aria-labelledby="saved-forgotten-label"
        >
          <dl>
            <dt
              id="saved-forgotten-label"
              className="text-sm font-medium text-slate-500"
            >
              Saved &amp; Forgotten
            </dt>
            {/* FR-014: the largest figure on the page, above every other card. */}
            <dd className="mt-1 text-5xl font-bold text-slate-900 tabular-nums">
              {overview.saved_and_forgotten.toLocaleString()}
            </dd>
          </dl>
          <p className="mt-3 text-sm text-slate-600">
            {overview.saved_and_forgotten === 0
              ? // FR-019: an explicit zero state, never a bare 0 to interpret.
                "Nothing forgotten — every video you saved to a playlist has been watched."
              : "Videos saved to a playlist you have never watched. Watch Later and History are not counted."}
          </p>
        </Link>
      )}

      {/* FR-027d: one column on narrow viewports, two from `md` — figures wrap
          rather than truncate, and the grid never forces horizontal scroll. */}
      <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-6 items-start">
        <section className={`${cardPatterns.base} p-6`}>
          {pending ? (
            <StatGrid
              items={[]}
              heading="Watch Later"
              headingId="overview-watch-later"
              loading
              skeletonCount={2}
            />
          ) : overview.watch_later ? (
            <StatGrid
              items={watchLaterItems(overview)}
              heading="Watch Later"
              headingId="overview-watch-later"
            />
          ) : (
            // FR-020a: absence is its own state. Zeros here would tell someone
            // with no Watch Later that their queue is empty.
            <div>
              <h3
                id="overview-watch-later"
                className="text-sm font-semibold text-slate-700 mb-3"
              >
                Watch Later
              </h3>
              <p className="text-sm text-slate-600">
                No Watch Later playlist found in your library.
              </p>
            </div>
          )}
        </section>

        <section className={`${cardPatterns.base} p-6`}>
          {pending ? (
            <StatGrid
              items={[]}
              heading="Playlists by type"
              headingId="overview-inventory"
              loading
              skeletonCount={3}
            />
          ) : overview.playlist_inventory.length > 0 ? (
            <StatGrid
              items={inventoryItems(overview.playlist_inventory)}
              heading="Playlists by type"
              headingId="overview-inventory"
            />
          ) : (
            <div>
              <h3
                id="overview-inventory"
                className="text-sm font-semibold text-slate-700 mb-3"
              >
                Playlists by type
              </h3>
              <p className="text-sm text-slate-600">
                No playlists yet — 0 in your library.
              </p>
            </div>
          )}
        </section>

        <section className={`${cardPatterns.base} p-6 md:col-span-2`}>
          <StatGrid
            items={pending ? [] : rollupItems(overview)}
            heading="Library totals"
            headingId="overview-rollup"
            loading={pending}
            skeletonCount={3}
          />
          <p className="mt-3 text-xs text-slate-500">
            Saved and watched are independent — a video can be in a playlist
            without ever having been watched.
          </p>
        </section>
      </div>
    </div>
  );
}

/**
 * Page container, matching Settings and Videos.
 *
 * Without this the content sits flush against the sidebar — every other page
 * carries its own padding because the shell's content area supplies none.
 */
const PAGE = "p-6 lg:p-8";

/**
 * Page header, matching Settings and Videos.
 *
 * `h2`, not `h1`: the shell header already renders the document's single `h1`
 * ("Chronovista", `layout/Header.tsx`). A second `h1` here would give the page
 * two top-level headings and break the outline screen-reader users navigate by.
 */
function OverviewHeader() {
  return (
    <div className="mb-8">
      <h2 className="text-2xl font-bold text-slate-900">Overview</h2>
      <p className="text-slate-600 mt-1">
        A snapshot of what you have saved and what you have actually watched.
      </p>
    </div>
  );
}
