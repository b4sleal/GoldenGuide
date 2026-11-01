import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Composer } from "./Composer";

describe("Composer", () => {
  it("preserves a draft through automatic URL assignment and clears it on an explicit conversation switch", async () => {
    const user = userEvent.setup();
    const props = { streaming: false, onSend: vi.fn(), onStop: vi.fn() };
    const { rerender } = render(<Composer {...props} />);
    const input = screen.getByRole("textbox");
    await user.type(input, "A follow-up draft");

    rerender(<Composer {...props} conversationId="newly-created" preserveDraft />);
    expect(screen.getByRole("textbox")).toBe(input);
    expect(input).toHaveValue("A follow-up draft");
    expect(input).toHaveFocus();

    rerender(<Composer {...props} conversationId="another-chat" />);
    expect(input).toHaveValue("");
    await user.type(input, "Another draft");
    rerender(<Composer {...props} conversationId={null} />);
    expect(input).toHaveValue("");
  });

  it("keeps Enter, Shift+Enter and Stop behavior while the input stays mounted", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    const onStop = vi.fn();
    const { rerender } = render(<Composer streaming={false} onSend={onSend} onStop={onStop} />);
    const input = screen.getByRole("textbox");
    await user.type(input, "First line{Shift>}{Enter}{/Shift}Second line{Enter}");
    expect(onSend).toHaveBeenCalledExactlyOnceWith("First line\nSecond line");
    expect(input).toHaveValue("");

    rerender(<Composer streaming onSend={onSend} onStop={onStop} />);
    expect(input).toHaveFocus();
    await user.type(input, "Next question{Enter}");
    expect(onSend).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Stop answer" }));
    expect(onStop).toHaveBeenCalledOnce();
  });
});
