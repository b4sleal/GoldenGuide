import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { applyTheme, currentTheme, saveTheme } from "./theme";

beforeEach(() => {
  localStorage.clear();
  document.documentElement.className = "";
});
afterEach(() => {
  vi.restoreAllMocks();
  document.documentElement.className = "";
  localStorage.clear();
});

describe("theme changes", () => {
  it("applies the initial theme without animating the first paint", () => {
    applyTheme("dark");
    expect(document.documentElement).toHaveClass("dark");
    expect(document.documentElement).not.toHaveClass("theme-transition");
  });

  it.each(["dark", "light"] as const)("applies and remembers %s immediately", (theme) => {
    applyTheme(theme === "dark" ? "light" : "dark");
    saveTheme(theme);
    expect(document.documentElement.classList.contains("dark")).toBe(theme === "dark");
    expect(currentTheme()).toBe(theme);
    expect(document.documentElement).not.toHaveClass("theme-transition");
    expect(document.documentElement.style.getPropertyValue("--theme-transition-duration")).toBe("");
  });

  it("keeps the latest choice when toggled repeatedly", () => {
    saveTheme("dark");
    saveTheme("light");
    saveTheme("dark");
    expect(document.documentElement).toHaveClass("dark");
    expect(document.documentElement).not.toHaveClass("theme-transition");
    expect(currentTheme()).toBe("dark");
  });

  it("skips transition motion when the student prefers reduced motion", () => {
    const original = window.matchMedia;
    vi.spyOn(window, "matchMedia").mockImplementation((query) => ({
      ...original(query), matches: query === "(prefers-reduced-motion: reduce)",
    }));
    saveTheme("dark");
    expect(document.documentElement).toHaveClass("dark");
    expect(document.documentElement).not.toHaveClass("theme-transition");
  });

  it("still switches theme when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("Blocked", "SecurityError"); });
    expect(() => saveTheme("dark")).not.toThrow();
    expect(document.documentElement).toHaveClass("dark");
  });
});
