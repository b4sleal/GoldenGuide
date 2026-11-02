/** The site a source link points to, e.g. `www.wlu.ca`; null for a missing or malformed URL. */
export function hostOf(url: string): string | null {
  try {
    return new URL(url).host;
  } catch {
    return null;
  }
}
