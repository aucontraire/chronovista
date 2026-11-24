import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { EvidenceItem } from "../EvidenceItem";
import {
  fixtureGroupedPassage,
  fixtureLanguagePassage,
  fixtureMention,
  fixtureVideoPassages,
} from "./fixtures";

function renderItem(item = fixtureVideoPassages()) {
  return render(
    <MemoryRouter>
      <EvidenceItem item={item} />
    </MemoryRouter>,
  );
}

/** N grouped passages, each starting 100s after the previous, so time ranges are distinct. */
function manyPassages(n: number) {
  return Array.from({ length: n }, (_, i) =>
    fixtureGroupedPassage({
      start_time: 100 * (i + 1),
      end_time: 100 * (i + 1) + 50,
    }),
  );
}

describe("EvidenceItem", () => {
  it("shows video title, channel and the closest gap in whole seconds", () => {
    renderItem();
    expect(screen.getByText("Generic Video Title")).toBeInTheDocument();
    expect(screen.getByText(/Generic Channel/)).toBeInTheDocument();
    expect(screen.getByTestId("evidence-separation")).toHaveTextContent(
      "closest mentions 8s apart",
    );
  });

  it("renders the video title as an h3 and names its passages list after the video", () => {
    renderItem();
    expect(
      screen.getByRole("heading", { level: 3, name: "Generic Video Title" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("list", { name: "Passages in Generic Video Title" }),
    ).toBeInTheDocument();
  });

  it("keeps every link's accessible name starting with its visible text (WCAG 2.5.3)", () => {
    renderItem(
      fixtureVideoPassages({
        passages: [
          fixtureGroupedPassage({
            variants: [
              fixtureLanguagePassage({
                co_mention_count: 2,
                other_moments: [{ start_time: 40, gap_seconds: 9.6 }],
              }),
            ],
          }),
        ],
      }),
    );
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(2);
    for (const link of links) {
      const visible = (link.textContent ?? "").trim();
      expect(link.getAttribute("aria-label")?.startsWith(visible)).toBe(true);
    }
  });

  it("wraps the sr-only context marker in lang=en", () => {
    renderItem();
    expect(screen.getByText("(context)")).toHaveAttribute("lang", "en");
  });

  it("copes with missing titles", () => {
    renderItem(fixtureVideoPassages({ video_title: null, channel_title: null }));
    expect(screen.getByText("Untitled video")).toBeInTheDocument();
  });

  it("shows the passage time range as m:ss–m:ss and as h:mm:ss for long videos", () => {
    renderItem(
      fixtureVideoPassages({
        passages: [
          fixtureGroupedPassage({ start_time: 65, end_time: 130 }),
          fixtureGroupedPassage({ start_time: 3600, end_time: 3725 }),
        ],
      }),
    );
    expect(screen.getByText("1:05–2:10")).toBeInTheDocument();
    expect(screen.getByText("1:00:00–1:02:05")).toBeInTheDocument();
  });

  it("shows the co-mention count only when above one", () => {
    const { unmount } = renderItem();
    expect(screen.queryByText(/co-mentions/)).not.toBeInTheDocument();
    unmount();
    renderItem(
      fixtureVideoPassages({
        passages: [
          fixtureGroupedPassage({
            variants: [fixtureLanguagePassage({ co_mention_count: 3 })],
          }),
        ],
      }),
    );
    expect(screen.getByText(/3 co-mentions/)).toBeInTheDocument();
  });

  it("highlights both matched names and sets the transcript language", () => {
    renderItem();
    const marks = document.querySelectorAll("mark");
    expect(Array.from(marks).map((m) => m.textContent)).toEqual([
      "Alpha",
      "Beta",
    ]);
    expect(marks[0]?.closest("[lang]")).toHaveAttribute("lang", "en");
  });

  it("dims context segments and marks them for screen readers, not by colour alone", () => {
    renderItem();
    const context = screen.getByText("Afterwards they moved on.");
    expect(context.closest(".text-slate-500")).not.toBeNull();
    expect(screen.getByText("(context)")).toHaveClass("sr-only");
    // Mention segments carry no context marker.
    expect(screen.getAllByText("(context)")).toHaveLength(1);
  });

  it("deep-links 'Open at m:ss' with lang, seg and floored t", () => {
    renderItem();
    const link = screen.getByRole("link", {
      name: /^Open at 0:12 – Generic Video Title \(en\)$/,
    });
    expect(link).toHaveTextContent("Open at 0:12");
    expect(link).toHaveAttribute(
      "href",
      "/videos/vid00000001?lang=en&seg=101&t=12",
    );
  });

  it("lists other moments as timestamps and gaps only, with no transcript text", () => {
    renderItem(
      fixtureVideoPassages({
        passages: [
          fixtureGroupedPassage({
            variants: [
              fixtureLanguagePassage({
                co_mention_count: 3,
                other_moments: [
                  { start_time: 40, gap_seconds: 9.6 },
                  { start_time: 75, gap_seconds: 14 },
                ],
              }),
            ],
          }),
        ],
      }),
    );
    const details = screen.getByTestId("other-moments");
    expect(details).toHaveTextContent("Other moments in this passage (2)");
    const items = within(details).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("0:40 → 0:49 · 10s apart");
    expect(items[1]).toHaveTextContent("1:15 → 1:29 · 14s apart");
    expect(
      within(items[0] as HTMLElement).getByRole("link"),
    ).toHaveAttribute("href", "/videos/vid00000001?lang=en&seg=101&t=40");
  });

  it("shows both times, in the link's accessible name too, so rows sharing an earlier mention differ", () => {
    renderItem(
      fixtureVideoPassages({
        passages: [
          fixtureGroupedPassage({
            variants: [
              fixtureLanguagePassage({
                co_mention_count: 4,
                other_moments: [
                  { start_time: 12, gap_seconds: 13 },
                  { start_time: 12, gap_seconds: 24 },
                  { start_time: 12, gap_seconds: 0 },
                ],
              }),
            ],
          }),
        ],
      }),
    );
    const items = within(screen.getByTestId("other-moments")).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("0:12 → 0:25 · 13s apart");
    expect(items[1]).toHaveTextContent("0:12 → 0:36 · 24s apart");
    expect(items[2]).toHaveTextContent("0:12 · 0s apart");
    expect(items[2]).not.toHaveTextContent("→");
    const link = within(items[0] as HTMLElement).getByRole("link");
    expect(link).toHaveAccessibleName(/^0:12 → 0:25 – Generic Video Title/);
    expect(link).toHaveAttribute("href", "/videos/vid00000001?lang=en&seg=101&t=12");
  });

  it("counts all other co-mentions and says how many are not listed when the server caps them", () => {
    renderItem(
      fixtureVideoPassages({
        passages: [
          fixtureGroupedPassage({
            variants: [
              fixtureLanguagePassage({
                co_mention_count: 120,
                other_moments: Array.from({ length: 50 }, (_, i) => ({
                  start_time: 100 + i,
                  gap_seconds: 5,
                })),
              }),
            ],
          }),
        ],
      }),
    );
    const details = screen.getByTestId("other-moments");
    expect(details).toHaveTextContent("Other moments in this passage (119)");
    expect(within(details).getAllByRole("listitem")).toHaveLength(50);
    expect(within(details).getByText("and 69 more")).toBeInTheDocument();
  });

  it("shows no 'and more' line when every other moment is listed", () => {
    renderItem(
      fixtureVideoPassages({
        passages: [
          fixtureGroupedPassage({
            variants: [
              fixtureLanguagePassage({
                co_mention_count: 2,
                other_moments: [{ start_time: 40, gap_seconds: 9.6 }],
              }),
            ],
          }),
        ],
      }),
    );
    expect(screen.queryByText(/and \d+ more/)).not.toBeInTheDocument();
  });

  it("omits the other-moments expander when there are none", () => {
    renderItem();
    expect(screen.queryByTestId("other-moments")).not.toBeInTheDocument();
  });

  describe("folding after three passages (FR-014a)", () => {
    it("shows three, then a button with the exact folded count", () => {
      renderItem(fixtureVideoPassages({ passages: manyPassages(5) }));
      expect(screen.getAllByTestId("evidence-passage")).toHaveLength(3);
      const button = screen.getByRole("button", {
        name: "Show 2 more passages",
      });
      expect(button).toHaveAttribute("aria-expanded", "false");
      expect(button).toHaveAttribute("aria-controls");
      expect(
        document.getElementById(button.getAttribute("aria-controls") ?? ""),
      ).not.toBeNull();
    });

    it("has no button when three or fewer passages", () => {
      renderItem(fixtureVideoPassages({ passages: manyPassages(3) }));
      expect(screen.queryByRole("button")).not.toBeInTheDocument();
    });

    it("reveals the rest in place and focuses the first revealed passage", () => {
      renderItem(fixtureVideoPassages({ passages: manyPassages(5) }));
      fireEvent.click(
        screen.getByRole("button", { name: "Show 2 more passages" }),
      );
      const rows = screen.getAllByTestId("evidence-passage");
      expect(rows).toHaveLength(5);
      expect(rows[3]).toHaveFocus();
      expect(rows[3]).toHaveAccessibleName("Passage 4 of 5, 6:40–7:30");
      expect(screen.queryByRole("button")).not.toBeInTheDocument();
    });
  });

  describe("other transcript languages", () => {
    it("has no expander for a single-language passage", () => {
      renderItem();
      expect(screen.queryByTestId("evidence-expander")).not.toBeInTheDocument();
    });

    it("keeps the other-languages expander collapsed by default", () => {
      renderItem(
        fixtureVideoPassages({
          passages: [
            fixtureGroupedPassage({
              variants: [
                fixtureLanguagePassage(),
                fixtureLanguagePassage({ language_code: "es" }),
              ],
            }),
          ],
        }),
      );
      expect(screen.getByTestId("evidence-expander")).not.toHaveAttribute("open");
    });

    it("renders two variants of the same language, each with its own link and no duplicate-key warning", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      const base = fixtureLanguagePassage();
      renderItem(
        fixtureVideoPassages({
          passages: [
            fixtureGroupedPassage({
              variants: [
                base,
                fixtureLanguagePassage({
                  start_time: 30,
                  closest: { ...base.closest, segment_id: 301, start_time: 30 },
                }),
                fixtureLanguagePassage({
                  start_time: 50,
                  closest: { ...base.closest, segment_id: 302, start_time: 50 },
                }),
              ],
            }),
          ],
        }),
      );
      const expander = screen.getByTestId("evidence-expander");
      const hrefs = within(expander)
        .getAllByRole("link")
        .map((l) => l.getAttribute("href"));
      expect(hrefs).toEqual([
        "/videos/vid00000001?lang=en&seg=301&t=30",
        "/videos/vid00000001?lang=en&seg=302&t=50",
      ]);
      expect(spy).not.toHaveBeenCalled();
      spy.mockRestore();
    });

    it("lists variants[1:] with their own deep link", () => {
      renderItem(
        fixtureVideoPassages({
          passages: [
            fixtureGroupedPassage({
              variants: [
                fixtureLanguagePassage(),
                fixtureLanguagePassage({
                  language_code: "es",
                  closest_gap_seconds: 5,
                  closest: {
                    ...fixtureLanguagePassage().closest,
                    segment_id: 200,
                    start_time: 40,
                  },
                }),
              ],
            }),
          ],
        }),
      );
      expect(screen.getByTestId("evidence-expander")).toHaveTextContent(
        /Also in 1 other transcript \(es\)/,
      );
      expect(
        screen.getByRole("link", { name: /^Open at 0:40 – Generic Video Title \(es\)$/ }),
      ).toHaveAttribute("href", "/videos/vid00000001?lang=es&seg=200&t=40");
    });
  });

  describe("name-list badge", () => {
    it("shows a text badge for a name-list leading variant and none otherwise", () => {
      const { unmount } = renderItem();
      expect(screen.queryByText("Several names in one segment")).not.toBeInTheDocument();
      unmount();
      renderItem(
        fixtureVideoPassages({
          passages: [
            fixtureGroupedPassage({
              variants: [
                fixtureLanguagePassage({ name_list: true }),
                fixtureLanguagePassage({ language_code: "es", name_list: true }),
              ],
            }),
          ],
        }),
      );
      // One for the leading variant and one inside the other-languages expander.
      expect(screen.getAllByText("Several names in one segment")).toHaveLength(2);
      // Nothing is hidden: the passage text is still there.
      expect(screen.getAllByText("Afterwards they moved on.").length).toBeGreaterThan(0);
    });
  });

  describe("omitted text between segments", () => {
    const omitted = (c: HTMLElement) => c.querySelectorAll("p[lang] [aria-hidden='true']");

    function passageWith(sequences: number[]) {
      const base = fixtureLanguagePassage();
      return fixtureVideoPassages({
        passages: [
          fixtureGroupedPassage({
            variants: [
              fixtureLanguagePassage({
                closest: {
                  ...base.closest,
                  mention_a: fixtureMention({ segment_id: 101, mention_text: "Alex Doe" }),
                  mention_b: fixtureMention({ segment_id: 102, mention_text: "Beta" }),
                  segments: sequences.map((n, i) => ({
                    segment_id: 101 + i,
                    sequence_number: n,
                    start_time: i * 4,
                    text: ["Alex Doe spoke.", "Then Beta.", "Later on.", "The end."][i] ?? "x",
                    is_context: i >= 2,
                  })),
                },
              }),
            ],
          }),
        ],
      });
    }

    it("adds no ellipsis between adjacent segments", () => {
      const { container } = renderItem(passageWith([20, 21, 22]));
      expect(omitted(container)).toHaveLength(0);
      expect(screen.queryByText("(text omitted)")).not.toBeInTheDocument();
    });

    it("marks exactly one omission, between the segments it separates, for sighted and screen-reader users", () => {
      const { container } = renderItem(passageWith([20, 21, 24, 25]));
      const marks = omitted(container);
      expect(marks).toHaveLength(1);
      expect(marks[0]).toHaveTextContent("\u2026");
      expect(marks[0]).toHaveClass("text-slate-400");
      const note = screen.getByText("(text omitted)");
      expect(note).toHaveClass("sr-only");
      expect(note).toHaveAttribute("lang", "en");
      // Sits after segment 21's text and before segment 24's, not elsewhere.
      const para = container.querySelector("p[lang]") as HTMLElement;
      expect(para.textContent).toMatch(/Then Beta\. ?\u2026\(text omitted\) \(context\) Later on\./);
      expect(para.textContent).not.toMatch(/Alex Doe spoke\. ?\u2026/);
    });

    it("still marks both names across an omission", () => {
      const { container } = renderItem(passageWith([20, 30, 31]));
      expect(omitted(container)).toHaveLength(1);
      expect(Array.from(container.querySelectorAll("mark")).map((m) => m.textContent)).toEqual([
        "Alex Doe",
        "Beta",
      ]);
    });
  });

  it("shows each passage's own closest gap, not the video's minimum", () => {
    renderItem(
      fixtureVideoPassages({
        closest_gap_seconds: 0.4,
        passages: [
          fixtureGroupedPassage({ start_time: 10, end_time: 40, closest_gap_seconds: 0.4 }),
          fixtureGroupedPassage({
            start_time: 118,
            end_time: 149,
            closest_gap_seconds: 9,
            variants: [fixtureLanguagePassage({ co_mention_count: 3 })],
          }),
        ],
      }),
    );
    expect(screen.getByTestId("evidence-separation")).toHaveTextContent("closest mentions 0s apart");
    const rows = screen.getAllByTestId("evidence-passage");
    expect(rows[0]).toHaveTextContent("closest 0s apart");
    expect(rows[1]).toHaveTextContent("1:58–2:29 · 3 co-mentions · closest 9s apart");
  });

  describe("highlighting by offset", () => {
    const marks = (container: HTMLElement) =>
      Array.from(container.querySelectorAll("mark")).map((m) => m.textContent);

    function withSegments(
      segments: {
        segment_id: number;
        text: string;
        is_context?: boolean;
        sequence_number?: number;
      }[],
      a: Parameters<typeof fixtureMention>[0],
      b: Parameters<typeof fixtureMention>[0],
    ) {
      const base = fixtureLanguagePassage();
      return fixtureVideoPassages({
        passages: [
          fixtureGroupedPassage({
            variants: [
              fixtureLanguagePassage({
                closest: {
                  ...base.closest,
                  mention_a: fixtureMention(a),
                  mention_b: fixtureMention(b),
                  segments: segments.map((s, i) => ({
                    segment_id: s.segment_id,
                    sequence_number: s.sequence_number ?? i,
                    start_time: i * 4,
                    text: s.text,
                    is_context: s.is_context ?? false,
                  })),
                },
              }),
            ],
          }),
        ],
      });
    }

    it("marks a mention that crosses a segment boundary in both segments", () => {
      const { container } = renderItem(
        withSegments(
          [
            { segment_id: 101, text: "Scholars on Placeland Alex Doe" },
            { segment_id: 102, text: "Smithson went on to speak." },
            { segment_id: 103, text: "Afterwards Beta arrived." },
          ],
          { segment_id: 101, end_segment_id: 102, mention_text: "Alex Doe Smithson", match_start: 22, match_end: 8 },
          { segment_id: 103, mention_text: "Beta", match_start: 11, match_end: 15 },
        ),
      );
      expect(marks(container)).toEqual(["Alex Doe", "Smithson", "Beta"]);
    });

    it("marks the end segment's part of the mention even when that segment is context", () => {
      const { container } = renderItem(
        withSegments(
          [
            { segment_id: 101, text: "Scholars on Placeland Alex Doe" },
            { segment_id: 102, text: "Smithson went on.", is_context: true },
            { segment_id: 103, text: "Then Beta." },
          ],
          { segment_id: 101, end_segment_id: 102, mention_text: "Alex Doe Smithson", match_start: 22, match_end: 8 },
          { segment_id: 103, mention_text: "Beta", match_start: 5, match_end: 9 },
        ),
      );
      expect(marks(container)).toEqual(["Alex Doe", "Smithson", "Beta"]);
    });

    it("falls back to text search when offsets are stale, never marking the wrong characters", () => {
      const { container } = renderItem(
        withSegments(
          [
            { segment_id: 101, text: "A new intro. Alex Doe spoke first." },
            { segment_id: 102, text: "Then Beta spoke." },
          ],
          // Offsets 0..8 now select "A new in", not the mention text.
          { segment_id: 101, mention_text: "Alex Doe", match_start: 0, match_end: 8 },
          { segment_id: 102, mention_text: "Beta", match_start: 5, match_end: 9 },
        ),
      );
      expect(marks(container)).toEqual(["Alex Doe", "Beta"]);
    });

    it("falls back when offsets are out of range or the end segment is missing", () => {
      const { container } = renderItem(
        withSegments(
          [
            { segment_id: 101, text: "Alex Doe here." },
            { segment_id: 102, text: "Then Beta." },
          ],
          { segment_id: 101, mention_text: "Alex Doe", match_start: 0, match_end: 99 },
          { segment_id: 102, end_segment_id: 777, mention_text: "Beta", match_start: 5, match_end: 4 },
        ),
      );
      expect(marks(container)).toEqual(["Alex Doe", "Beta"]);
    });

    it("keeps a longer name whole when another mention is its prefix", () => {
      const { container } = renderItem(
        withSegments(
          [{ segment_id: 101, text: "Alex Doe Jr and Alex Doe met." }],
          { segment_id: 101, mention_text: "Alex Doe Jr", match_start: 0, match_end: 11 },
          { segment_id: 101, mention_text: "Alex Doe", match_start: 16, match_end: 24 },
        ),
      );
      expect(marks(container)).toEqual(["Alex Doe Jr", "Alex Doe"]);
    });
  });
});
