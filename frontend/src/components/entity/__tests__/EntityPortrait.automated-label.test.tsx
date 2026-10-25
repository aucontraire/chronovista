/**
 * EntityPortrait automated-source label (Feature 093, US4 / FR-009).
 *
 * The automated portrait may now come from Wikidata or a free Wikipedia
 * image, so the toggle must not name a single provider. The API `source`
 * value stays "wikidata"; only the visible label changes.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { EntityPortrait } from "../EntityPortrait";

describe("EntityPortrait automated source label", () => {
  it("labels the automated option 'Automated image', not 'Wikidata image'", () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <EntityPortrait
          entityId="11111111-1111-4111-8111-111111111111"
          canonicalName="Sample Entity"
          image={{
            has_manual: true,
            has_wikidata: true,
            source: "manual",
            version: "v1",
          }}
        />
      </QueryClientProvider>,
    );

    expect(
      screen.getByRole("button", { name: "Automated image" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Your image" })).toBeInTheDocument();
    expect(screen.queryByText("Wikidata image")).toBeNull();
  });
});
