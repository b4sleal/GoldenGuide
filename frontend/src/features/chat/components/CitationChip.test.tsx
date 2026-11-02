import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Source } from "../stream/events";
import { AnswerSourcesProvider } from "./AnswerSourcesProvider";
import { CitationChip, HOVER_CLOSE_DELAY_MS } from "./CitationChip";

const sources: Source[] = [
  { title: "PC/CP220: Digital Electronics", url: "https://physics.wlu.ca/cp220", source_type: "wlu_page", snippet: "Office hours: by appointment." },
  { title: "Laurier Backgrounder", url: "https://www.wlu.ca/about/backgrounder", snippet: "Programs are also offered through Martin Luther University College." },
  { title: "Stored source", url: null },
];

function renderChip(numbers: number[], provided: Source[] = sources) {
  return render(
    <AnswerSourcesProvider sources={provided}>
      <CitationChip numbers={numbers} segment="0-0" />
    </AnswerSourcesProvider>,
  );
}

const card = () => screen.queryByRole("list", { name: "Cited sources" });

// Real timers: RTL settles each user-event action on a setTimeout(0) that only Jest's fake timers
// advance, so Vitest's fake timers hang these tests. The hover delays are a few hundred milliseconds.
async function sleep(ms: number) {
  await act(() => new Promise((resolve) => setTimeout(resolve, ms)));
}

const openCard = () => screen.findByRole("list", { name: "Cited sources" });
const closed = () => waitFor(() => expect(card()).not.toBeInTheDocument());

describe("CitationChip", () => {
  const setup = () => userEvent.setup();

  it("shows the first source's title and how many more it cites, and names them all", () => {
    renderChip([1, 2]);
    const chip = screen.getByRole("button", { name: "Sources: PC/CP220: Digital Electronics, Laurier Backgrounder" });
    expect(chip).toHaveTextContent("PC/CP220: Digital Electronics+1");
  });

  it("stands in the source number for a title until the source list has arrived", () => {
    renderChip([2], []);
    expect(screen.getByRole("button", { name: "Source: Source 2" })).toHaveTextContent("Source 2");
  });

  it("opens a card of every cited source after a short hover, with links, sites and previews", async () => {
    const user = setup();
    renderChip([1, 3]);
    await user.hover(screen.getByRole("button"));
    expect(card()).not.toBeInTheDocument();

    const entries = within(await openCard()).getAllByRole("listitem");
    expect(entries).toHaveLength(2);
    const link = within(entries[0]!).getByRole("link");
    expect(link).toHaveAttribute("href", "https://physics.wlu.ca/cp220");
    expect(link).toHaveAttribute("target", "_blank");
    expect(entries[0]).toHaveTextContent("physics.wlu.ca");
    expect(entries[0]).toHaveTextContent("Office hours: by appointment.");
    // A source without a link is shown but is not clickable.
    expect(entries[1]).toHaveTextContent("Stored source");
    expect(within(entries[1]!).queryByRole("link")).not.toBeInTheDocument();
  });

  it("keeps the card open while the pointer moves into it, and closes it after leaving", async () => {
    const user = setup();
    renderChip([1]);
    const chip = screen.getByRole("button");
    await user.hover(chip);
    await openCard();

    await user.unhover(chip);
    await user.hover(screen.getByRole("dialog"));
    await sleep(HOVER_CLOSE_DELAY_MS * 2);
    expect(card()).toBeInTheDocument();

    await user.unhover(screen.getByRole("dialog"));
    await closed();
  });

  it("does not move focus into a card opened by hovering", async () => {
    const user = setup();
    renderChip([1]);
    await user.hover(screen.getByRole("button"));
    await openCard();
    expect(screen.getByRole("dialog")).not.toContainElement(document.activeElement as HTMLElement);
  });

  it("opens on click for touch and stays pinned until clicked again or Escape is pressed", async () => {
    const user = setup();
    renderChip([1]);
    const chip = screen.getByRole("button");

    await user.click(chip);
    await openCard();
    await user.unhover(chip);
    await sleep(HOVER_CLOSE_DELAY_MS * 2);
    expect(card()).toBeInTheDocument();

    await user.click(chip);
    await closed();

    await user.click(chip);
    await openCard();
    await user.keyboard("{Escape}");
    await closed();
  });

  it("opens from the keyboard and lets Tab reach the source links", async () => {
    const user = setup();
    renderChip([1, 2]);
    screen.getByRole("button").focus();
    await user.keyboard("{Enter}");
    const links = within(await openCard()).getAllByRole("link");
    expect(links).toHaveLength(2);
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
  });

  it("scrolls the card instead of growing it when many sources are cited", async () => {
    const user = setup();
    const many = Array.from({ length: 6 }, (_, index) => ({ title: `Source ${index + 1}`, url: `https://www.wlu.ca/${index}` }));
    renderChip([1, 2, 3, 4, 5, 6], many);
    await user.click(screen.getByRole("button"));
    expect(await openCard()).toHaveClass("overflow-y-auto");
    expect(card()!.className).toMatch(/max-h-/);
    expect(within(card()!).getAllByRole("listitem")).toHaveLength(6);
  });
});
