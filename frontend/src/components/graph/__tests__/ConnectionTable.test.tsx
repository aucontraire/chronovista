import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { ConnectionTable } from "../ConnectionTable";
import { buildConnectionModel } from "../connectionModel";
import { fixtureConnection } from "./fixtures";

describe("ConnectionTable", () => {
  it("renders one row per model edge with endpoints marked", () => {
    const model = buildConnectionModel(fixtureConnection());
    render(<ConnectionTable model={model} />);
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(model.edges.length + 1); // + header
    expect(screen.getAllByText(/\(endpoint A\)/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/\(endpoint B\)/).length).toBeGreaterThan(0);
    expect(screen.getByRole("columnheader", { name: "Relationship" })).toBeInTheDocument();
  });

  it("labels the co-occurrence overlay as not a knowledge-base fact", () => {
    render(<ConnectionTable model={buildConnectionModel(fixtureConnection())} />);
    const row = screen.getByText("co occurs transcript").closest("tr")!;
    expect(within(row).getByText(/not a knowledge-base fact/)).toBeInTheDocument();
  });
});
