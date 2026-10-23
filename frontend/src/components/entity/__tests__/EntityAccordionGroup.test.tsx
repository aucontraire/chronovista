import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { EntityAccordionGroup } from "../EntityAccordionGroup";

function renderGroup(defaultOpen?: boolean) {
  return render(
    <EntityAccordionGroup
      title="Test Group"
      {...(defaultOpen !== undefined ? { defaultOpen } : {})}
    >
      <p>Group content</p>
    </EntityAccordionGroup>
  );
}

describe("EntityAccordionGroup", () => {
  it("is open by default", () => {
    renderGroup();
    const header = screen.getByRole("button", { name: "Test Group" });
    expect(header).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Group content")).toBeVisible();
  });

  it("honors defaultOpen={false}", () => {
    renderGroup(false);
    const header = screen.getByRole("button", { name: "Test Group" });
    expect(header).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("Group content")).not.toBeVisible();
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it("collapses and expands on click", async () => {
    const user = userEvent.setup();
    renderGroup();
    const header = screen.getByRole("button", { name: "Test Group" });

    await user.click(header);
    expect(header).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("Group content")).not.toBeVisible();

    await user.click(header);
    expect(header).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Group content")).toBeVisible();
  });

  it("toggles with Enter and Spacebar on the header button", async () => {
    const user = userEvent.setup();
    renderGroup();
    const header = screen.getByRole("button", { name: "Test Group" });

    header.focus();
    await user.keyboard("{Enter}");
    expect(header).toHaveAttribute("aria-expanded", "false");

    await user.keyboard(" ");
    expect(header).toHaveAttribute("aria-expanded", "true");
  });

  it("links the header to its region via aria-controls and aria-labelledby", () => {
    renderGroup();
    const header = screen.getByRole("button", { name: "Test Group" });
    const region = screen.getByRole("region", { name: "Test Group" });
    expect(header.getAttribute("aria-controls")).toBe(region.id);
  });
});
