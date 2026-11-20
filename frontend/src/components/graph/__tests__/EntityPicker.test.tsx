/** EntityPicker resolves a bare id to the entity's name (reload / deep link). */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { EntityPicker } from "../EntityPicker";
import { A_ID } from "./fixtures";

const detailMock = vi.fn();
vi.mock("../../../hooks/useEntityDetail", () => ({
  useEntityDetail: (...args: unknown[]) => detailMock(...args),
}));
vi.mock("../../../hooks/useEntitySearch", () => ({
  useEntitySearch: () => ({ entities: [], isLoading: false, isFetched: false, isError: false, isBelowMinChars: true }),
}));
vi.mock("../../../hooks/useConnection", () => ({
  useGraphPresence: () => ({ present: new Set<string>(), isLoading: false }),
}));

const noop = () => undefined;

describe("EntityPicker selected name", () => {
  beforeEach(() => detailMock.mockReset());

  it("looks the name up by id when only the id is known (page reload)", () => {
    detailMock.mockReturnValue({ entityDetail: { canonical_name: "Resolved Name" }, aliasNames: [], isLoading: false });
    render(<EntityPicker label="Entity A" selectedId={A_ID} selectedName={undefined} onSelect={noop} onClear={noop} />);
    expect(detailMock).toHaveBeenCalledWith(A_ID);
    expect(screen.getByTestId("picker-selected")).toHaveTextContent("Resolved Name");
  });

  it("falls back to the short id only while the lookup is pending", () => {
    detailMock.mockReturnValue({ entityDetail: undefined, aliasNames: [], isLoading: true });
    render(<EntityPicker label="Entity A" selectedId={A_ID} selectedName={undefined} onSelect={noop} onClear={noop} />);
    expect(screen.getByTestId("picker-selected")).toHaveTextContent("Entity 11111111");
  });

  it("does not look anything up when the name is already known", () => {
    detailMock.mockReturnValue({ entityDetail: undefined, aliasNames: [], isLoading: false });
    render(<EntityPicker label="Entity A" selectedId={A_ID} selectedName="Given Name" onSelect={noop} onClear={noop} />);
    expect(detailMock).toHaveBeenCalledWith(null);
    expect(screen.getByTestId("picker-selected")).toHaveTextContent("Given Name");
  });
});
