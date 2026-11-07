/**
 * Tests for the intersection link on a relationship candidate row (Feature 107).
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { RelationshipCandidate } from "../../../hooks/useRelationshipCandidates";
import { RelationshipCandidateRow } from "../RelationshipCandidateRow";

const candidate: RelationshipCandidate = {
  id: "rc-1",
  entity_a: { id: "a-1", canonical_name: "Entity A", entity_type: "person" },
  entity_b: { id: "b-1", canonical_name: "Entity B", entity_type: "person" },
  shared_video_count: 12,
  lift: 8,
  both_typed_eligible: false,
  kb_corroboration_count: 0,
  kb_corroboration_detail: [],
  channel: "title_description",
  channel_video_universe: 1000,
  status: "candidate",
};

describe("RelationshipCandidateRow", () => {
  it("links to the /videos intersection of both entities, a before b", () => {
    render(
      <MemoryRouter>
        <ul>
          <RelationshipCandidateRow candidate={candidate} />
        </ul>
      </MemoryRouter>
    );
    const link = screen.getByRole("link", {
      name: "View videos where Entity A and Entity B appear together",
    });
    expect(link.getAttribute("href")).toBe("/videos?entity_id=a-1&entity_id=b-1");
    expect(link).toHaveTextContent("View shared videos");
    expect(link).not.toHaveTextContent("12");
  });
});
