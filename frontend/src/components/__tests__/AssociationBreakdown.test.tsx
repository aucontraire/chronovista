/**
 * Tests for AssociationBreakdown component (Feature 066, FR-004).
 *
 * Coverage:
 * - All five sources render, including zero-count sources
 * - Sources render in the required display order: tag, transcript, title,
 *   description, manual
 * - Each pill shows its count
 * - Container carries a single summarizing aria-label; pills are aria-hidden
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { AssociationBreakdown } from "../AssociationBreakdown";
import type { AssociationSourceBreakdown } from "../../api/entityMentions";

describe("AssociationBreakdown", () => {
  const bySource: AssociationSourceBreakdown = {
    manual: 1,
    transcript: 5,
    title: 2,
    description: 0,
    tag: 3,
  };

  it("renders all five sources, including zero-count ones", () => {
    const { container } = render(<AssociationBreakdown bySource={bySource} />);
    const pills = container.querySelectorAll("[aria-hidden='true']");
    expect(pills).toHaveLength(5);
  });

  it("renders sources in the required order: tag, transcript, title, description, manual", () => {
    const { container } = render(<AssociationBreakdown bySource={bySource} />);
    const pills = container.querySelectorAll("[aria-hidden='true']");
    const texts = Array.from(pills).map((pill) => pill.textContent);
    expect(texts).toEqual(["TAG 3", "TRANSCRIPT 5", "TITLE 2", "DESCRIPTION 0", "MANUAL 1"]);
  });

  it("shows the description pill even when its count is 0", () => {
    render(<AssociationBreakdown bySource={bySource} />);
    expect(screen.getByText("DESCRIPTION 0")).toBeInTheDocument();
  });

  it("gives the container a single summarizing aria-label", () => {
    const { container } = render(<AssociationBreakdown bySource={bySource} />);
    const wrapper = container.firstElementChild;
    expect(wrapper).toHaveAttribute(
      "aria-label",
      "Associations by source: 3 tag, 5 transcript, 2 title, 0 description, 1 manual"
    );
  });

  it("applies an optional className to the container", () => {
    const { container } = render(
      <AssociationBreakdown bySource={bySource} className="mt-2" />
    );
    expect(container.firstElementChild).toHaveClass("mt-2");
  });
});
