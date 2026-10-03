/**
 * Tests for the "Include unavailable videos" toggle on EntityDetailPage
 * (Feature 080). Defaults off; toggling threads includeUnavailable into
 * useEntityVideos.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { EntityDetailPage } from "../EntityDetailPage";

vi.mock("../../hooks/useEntityMentions", () => ({
  useEntityVideos: vi.fn(),
  useVideoEntities: vi.fn(() => ({
    entities: [],
    isLoading: false,
    isError: false,
    error: null,
  })),
  useDeleteManualAssociation: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    isSuccess: false,
  })),
  useScanEntity: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    data: null,
    reset: vi.fn(),
  })),
  useScanVideoEntities: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    data: null,
    reset: vi.fn(),
  })),
  useUpdateEntity: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    isSuccess: false,
    reset: vi.fn(),
  })),
}));

vi.mock("../../components/corrections/PhoneticVariantsSection", () => ({
  PhoneticVariantsSection: () => null,
}));

vi.mock("../../components/corrections/ExclusionPatternsSection", () => ({
  ExclusionPatternsSection: () => null,
}));

vi.mock("@tanstack/react-query", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/react-query")>();
  return { ...actual, useQuery: vi.fn() };
});

import { useQuery } from "@tanstack/react-query";
import { useEntityVideos } from "../../hooks/useEntityMentions";

const mockEntity = {
  entity_id: "entity-uuid-001",
  canonical_name: "Test Entity",
  entity_type: "person",
  description: null,
  status: "active",
  mention_count: 5,
  video_count: 3,
  by_source: { manual: 0, transcript: 5, title: 0, description: 0, tag: 0 },
  aliases: [] as { alias_name: string; alias_type: string; occurrence_count: number }[],
  exclusion_patterns: [] as string[],
};

const defaultUseEntityVideos = {
  videos: [],
  total: null,
  pagination: null,
  isLoading: false,
  isError: false,
  error: null,
  hasNextPage: false,
  isFetchingNextPage: false,
  fetchNextPage: vi.fn(),
  loadMoreRef: { current: null },
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/entities/entity-uuid-001"]}>
        <Routes>
          <Route path="/entities/:entityId" element={<EntityDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useQuery).mockReturnValue({
    data: mockEntity,
    isLoading: false,
    isError: false,
    error: null,
    status: "success",
    isSuccess: true,
    isFetching: false,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof useQuery>);
  vi.mocked(useEntityVideos).mockReturnValue(defaultUseEntityVideos);
});

describe("EntityDetailPage — include unavailable toggle (Feature 080)", () => {
  it("renders an unchecked, labelled checkbox by default", () => {
    renderPage();
    const toggle = screen.getByRole("checkbox", {
      name: "Include unavailable videos",
    });
    expect(toggle).not.toBeChecked();
  });

  it("does not request unavailable videos by default", () => {
    renderPage();
    const params = vi.mocked(useEntityVideos).mock.calls.at(-1)?.[1];
    expect(params?.includeUnavailable).toBeUndefined();
  });

  it("passes includeUnavailable: true when toggled on, and drops it when off", () => {
    renderPage();
    const toggle = screen.getByRole("checkbox", {
      name: "Include unavailable videos",
    });

    fireEvent.click(toggle);
    expect(toggle).toBeChecked();
    expect(vi.mocked(useEntityVideos).mock.calls.at(-1)?.[1]).toMatchObject({
      includeUnavailable: true,
    });

    fireEvent.click(toggle);
    expect(toggle).not.toBeChecked();
    expect(
      vi.mocked(useEntityVideos).mock.calls.at(-1)?.[1]?.includeUnavailable
    ).toBeUndefined();
  });
});
