import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SourceList } from "./SourceList";

const sources = [
  { title: "LORIS - Registration", url: "https://loris.wlu.ca", source_type: "course_terms" },
  { title: "Academic Calendar", url: "https://academic-calendar.wlu.ca" },
  { title: "Stored source", url: null },
];

afterEach(() => vi.restoreAllMocks());

function overflow() {
  vi.spyOn(Element.prototype, "clientWidth", "get").mockReturnValue(300);
  vi.spyOn(Element.prototype, "scrollWidth", "get").mockReturnValue(900);
}

function pointer(element: Element, type: string, clientX: number, pointerType = "mouse") {
  const event = new MouseEvent(type, { bubbles: true, cancelable: true, button: 0, buttons: type === "pointerup" ? 0 : 1, clientX });
  Object.defineProperties(event, { pointerId: { value: 1 }, pointerType: { value: pointerType } });
  fireEvent(element, event);
}

describe("SourceList", () => {
  it("keeps the backend order, numbering and links, including non-link sources", () => {
    render(<SourceList sources={sources} />);
    const list = screen.getByRole("list", { name: "Source links" });
    const cards = within(list).getAllByRole("listitem");
    expect(cards).toHaveLength(3);
    expect(cards.map((card) => card.textContent?.[0])).toEqual(["1", "2", "3"]);
    expect(within(cards[0]!).getByRole("link")).toHaveAttribute("href", sources[0]!.url);
    expect(within(cards[0]!).getByRole("link")).toHaveAttribute("target", "_blank");
    expect(within(cards[2]!).queryByRole("link")).not.toBeInTheDocument();
    expect(list).toHaveAttribute("tabindex", "0");
  });

  it("does not merge or renumber source entries in the frontend", () => {
    render(<SourceList sources={[
      { title: "A", url: "https://loris.wlu.ca", source_type: "course_terms" },
      { title: "B", url: "https://loris.wlu.ca", source_type: "course_terms" },
    ]} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("omits the region for empty sources and navigation controls when everything fits", () => {
    const { rerender } = render(<SourceList sources={[]} />);
    expect(screen.queryByRole("region", { name: "Sources" })).not.toBeInTheDocument();
    rerender(<SourceList sources={sources} />);
    expect(screen.queryByRole("button", { name: "Next sources" })).not.toBeInTheDocument();
  });

  it.each([false, true])("scrolls with arrow controls and respects reduced motion (%s)", async (reduced) => {
    overflow();
    const original = window.matchMedia;
    vi.spyOn(window, "matchMedia").mockImplementation((query) => ({ ...original(query), matches: reduced }));
    render(<SourceList sources={sources} />);
    const list = screen.getByRole("list", { name: "Source links" });
    const scrollBy = vi.fn();
    list.scrollBy = scrollBy;
    const user = userEvent.setup();

    expect(screen.getByRole("button", { name: "Previous sources" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Next sources" }));
    expect(scrollBy).toHaveBeenCalledWith({ left: 240, behavior: reduced ? "instant" : "smooth" });
    list.scrollLeft = 600;
    fireEvent.scroll(list);
    expect(screen.getByRole("button", { name: "Next sources" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Previous sources" }));
    expect(scrollBy).toHaveBeenLastCalledWith({ left: -240, behavior: reduced ? "instant" : "smooth" });
  });

  it("drags with the mouse without opening a link, then allows an ordinary click", () => {
    render(<SourceList sources={sources} />);
    const list = screen.getByRole("list", { name: "Source links" });
    const link = within(list).getAllByRole("link")[0]!;
    list.setPointerCapture = vi.fn();
    list.hasPointerCapture = vi.fn().mockReturnValue(true);
    list.releasePointerCapture = vi.fn();
    pointer(link, "pointerdown", 200);
    pointer(list, "pointermove", 100);
    expect(list.scrollLeft).toBe(100);
    pointer(list, "pointerup", 100);
    expect(fireEvent.click(link, { detail: 1 })).toBe(false);
    expect(list.releasePointerCapture).toHaveBeenCalledWith(1);

    pointer(link, "pointerdown", 100);
    pointer(link, "pointerup", 100);
    expect(fireEvent.click(link, { detail: 1 })).toBe(true);
  });

  it("leaves touch gestures to the browser", () => {
    render(<SourceList sources={sources} />);
    const list = screen.getByRole("list", { name: "Source links" });
    list.setPointerCapture = vi.fn();
    pointer(list, "pointerdown", 200, "touch");
    pointer(list, "pointermove", 100, "touch");
    expect(list.setPointerCapture).not.toHaveBeenCalled();
    expect(list.scrollLeft).toBe(0);
  });

  it("does not start dragging after the mouse was released outside the list", () => {
    render(<SourceList sources={sources} />);
    const list = screen.getByRole("list", { name: "Source links" });
    list.setPointerCapture = vi.fn();
    pointer(list, "pointerdown", 200);
    const move = new MouseEvent("pointermove", { bubbles: true, button: 0, buttons: 0, clientX: 100 });
    Object.defineProperties(move, { pointerId: { value: 1 }, pointerType: { value: "mouse" } });
    fireEvent(list, move);
    expect(list.setPointerCapture).not.toHaveBeenCalled();
    expect(list.scrollLeft).toBe(0);
  });
});
