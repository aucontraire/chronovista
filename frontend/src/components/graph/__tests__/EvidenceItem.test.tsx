import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { EvidenceItem } from "../EvidenceItem";
import { fixtureEvidenceItem, fixtureVariant } from "./fixtures";

function renderItem(item = fixtureEvidenceItem()) {
  return render(
    <MemoryRouter>
      <EvidenceItem item={item} />
    </MemoryRouter>,
  );
}

describe("EvidenceItem", () => {
  it("renders the representative passage with both matched forms highlighted", () => {
    renderItem();
    const marks = document.querySelectorAll("mark");
    expect(Array.from(marks).map((m) => m.textContent)).toEqual([
      "Alpha",
      "Beta",
    ]);
  });

  it("deep-links to the representative passage with lang, seg and floored t", () => {
    renderItem();
    const link = screen.getByRole("link", {
      name: /Open Generic Video Title at 0:12/,
    });
    expect(link).toHaveAttribute(
      "href",
      "/videos/vid00000001?lang=en&seg=101&t=12",
    );
  });

  it("renders one link per passage when the mentions are far apart", () => {
    renderItem(
      fixtureEvidenceItem({
        representative: fixtureVariant({
          passages: [
            { text: "Alpha first.", start_time: 5, segment_id: 1 },
            { text: "Later Beta.", start_time: 300, segment_id: 50 },
          ],
        }),
      }),
    );
    expect(screen.getAllByRole("link")).toHaveLength(2);
  });

  it("shows the representative separation and video/channel titles", () => {
    renderItem();
    expect(screen.getByTestId("evidence-separation")).toHaveTextContent(
      "~2 segments apart",
    );
    expect(screen.getByText("Generic Video Title")).toBeInTheDocument();
    expect(screen.getByText(/Generic Channel/)).toBeInTheDocument();
  });

  it("copes with missing titles", () => {
    renderItem(fixtureEvidenceItem({ video_title: null, channel_title: null }));
    expect(screen.getByText("Untitled video")).toBeInTheDocument();
  });

  it("has no expander for a single-language video", () => {
    renderItem();
    expect(screen.queryByTestId("evidence-expander")).not.toBeInTheDocument();
  });

  it("shows an expander listing the other co-occurring languages and their passages", () => {
    renderItem(
      fixtureEvidenceItem({
        other_language_variants: [
          fixtureVariant({
            language_code: "es",
            passages: [
              {
                text: "Alpha junto a Beta aqui.",
                start_time: 40,
                segment_id: 200,
              },
            ],
          }),
        ],
        cooccurring_language_count: 2,
      }),
    );
    expect(screen.getByTestId("evidence-expander")).toHaveTextContent(
      /also in 1 other transcript \(es\)/,
    );
    // The expander's variant deep-links into the es transcript.
    const esLink = screen.getByRole("link", {
      name: /Open Generic Video Title at 0:40/,
    });
    expect(esLink).toHaveAttribute(
      "href",
      "/videos/vid00000001?lang=es&seg=200&t=40",
    );
  });
});
