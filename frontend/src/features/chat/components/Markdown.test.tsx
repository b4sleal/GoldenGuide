import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Source } from "../stream/events";
import { citationMarkdown } from "../stream/citations";
import { AnswerSourcesProvider } from "./AnswerSourcesProvider";
import { Markdown } from "./Markdown";
import { SourceList } from "./SourceList";

const sources: Source[] = [
  { title: "PC/CP220: Digital Electronics", url: "https://physics.wlu.ca/cp220", snippet: "Office hours: by appointment." },
  { title: "Laurier Backgrounder", url: "https://www.wlu.ca/about/backgrounder" },
];

function renderAnswer(markdown: string, withList = false) {
  return render(
    <AnswerSourcesProvider sources={sources}>
      <Markdown markdown={markdown} idPrefix="0" />
      {withList && <SourceList sources={sources} />}
    </AnswerSourcesProvider>,
  );
}

/** Everything highlighted in the answer (the card is portalled outside it). */
const lit = (container: HTMLElement) => [...container.querySelectorAll("[data-highlighted]")].map((node) => node.textContent?.trim());

async function hoverCardSource(user: ReturnType<typeof userEvent.setup>, chipName: RegExp) {
  await user.hover(screen.getByRole("button", { name: chipName }));
  const card = await screen.findByRole("list", { name: "Cited sources" });
  await user.hover(within(card).getAllByRole("link")[0]!);
}

describe("Markdown citations", () => {
  it("shows a citation as a source chip instead of a bracketed number", () => {
    const { container } = renderAnswer(`Opened in 1999. ${citationMarkdown([1])}`);
    expect(screen.getByRole("button", { name: "Source: PC/CP220: Digital Electronics" })).toBeInTheDocument();
    expect(container).not.toHaveTextContent("[1]");
    expect(container.querySelector("a")).toBeNull();
  });

  it("highlights nothing while only the chip is hovered", async () => {
    const { container } = renderAnswer(`Opened in 1999. ${citationMarkdown([1])}`, true);
    await userEvent.setup().hover(screen.getByRole("button", { name: /PC\/CP220/ }));
    expect(lit(container)).toEqual([]);
  });

  it("highlights exactly the text a citation covers when a source in its card is hovered", async () => {
    const { container } = renderAnswer(`**Brantford:** Opened in 1999. ${citationMarkdown([1])} Also in Kitchener. ${citationMarkdown([2])}`);
    await hoverCardSource(userEvent.setup(), /PC\/CP220/);
    expect(lit(container)).toEqual(["Brantford: Opened in 1999."]);
  });

  it("starts each list item's segment at the item, not at the previous item's citation", async () => {
    const { container } = renderAnswer(`- First fact ${citationMarkdown([1])}\n- Second fact ${citationMarkdown([2])}`);
    await hoverCardSource(userEvent.setup(), /Laurier Backgrounder/);
    expect(lit(container)).toEqual(["Second fact"]);
  });

  it("lights up only the chips citing a source hovered in the source list, not their text", async () => {
    const markdown = `One. ${citationMarkdown([1])} Two. ${citationMarkdown([2])} Three. ${citationMarkdown([1, 2])}`;
    const { container } = renderAnswer(markdown, true);
    await userEvent.setup().hover(screen.getByRole("link", { name: /Laurier Backgrounder/ }));

    expect(lit(container)).toEqual(["Laurier Backgrounder", "PC/CP220: Digital Electronics+1"]);
  });

  it("keeps ordinary links as plain new-tab links", () => {
    renderAnswer("See [CP264](https://academic-calendar.wlu.ca/cp264).");
    const link = screen.getByRole("link", { name: "CP264" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });
});
