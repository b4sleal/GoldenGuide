/** Light/dark theme: follows the system until the student picks one, then remembers the choice. */
export type Theme = "light" | "dark";

const STORAGE_KEY = "gg-theme";

function stored(): Theme | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null; // storage blocked (private mode, policy): fall back to the system theme
  }
}

export function currentTheme(): Theme {
  return stored() ?? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

export function saveTheme(theme: Theme): void {
  // Switch the palette immediately; animating inherited colors on every element causes visible lag.
  applyTheme(theme);
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Not remembered; the choice still applies to this page.
  }
}
