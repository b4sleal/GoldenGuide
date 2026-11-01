import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { EvidenceTable } from "./EvidenceTable";
import { Markdown } from "./Markdown";

describe("answer tables", () => {
  it("preserves database values and meeting line breaks in a labelled, keyboard-focusable viewport", async () => {
    const meetings = "Monday 10:00 - 11:20\nWednesday 10:00 - 11:20";
    render(
      <EvidenceTable table={{ title: "CP264 sections", columns: ["Section", "Meetings"], rows: [["A | <section>", meetings]] }} />,
    );

    const viewport = screen.getByRole("region", { name: "CP264 sections" });
    const table = within(viewport).getByRole("table", { name: "CP264 sections" });
    expect(within(table).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual(["Section", "Meetings"]);
    expect(within(table).getAllByRole("cell").map((cell) => cell.textContent)).toEqual(["A | <section>", meetings]);
    // Scraped markup stays literal text, and keyboard users can reach the scroll region.
    expect(table.querySelector("section")).toBeNull();
    await userEvent.setup().tab();
    expect(viewport).toHaveFocus();
  });

  it("makes Markdown tables keyboard-focusable while preserving links and cell content", async () => {
    render(<Markdown markdown={"| Course | Prerequisite |\n| --- | --- |\n| [CP264](https://wlu.ca/cp264) | CP164 |"} />);

    const viewport = screen.getByRole("region", { name: "Answer table" });
    const table = within(viewport).getByRole("table");
    expect(within(table).getByRole("cell", { name: "CP164" })).toBeInTheDocument();
    expect(within(table).getByRole("link", { name: "CP264" })).toHaveAttribute("href", "https://wlu.ca/cp264");
    await userEvent.setup().tab();
    expect(viewport).toHaveFocus();
  });
});
