/** Australian financial year helpers (1 July – 30 June). */

/** First FY FrogsWork supports (product launch July 2026 → FY 2026–27). */
export const FIRST_AU_FY_START_YEAR = 2026;

export type AuFinancialYear = {
  token: string;
  start: string;
  end: string;
  display: string;
  fileSlug: string;
};

export function parseAuFinancialYear(
  fyRaw: string,
  today: Date = new Date()
): AuFinancialYear | null {
  let raw = String(fyRaw || "").trim();
  if (!raw) {
    const y = today.getFullYear();
    const m = today.getMonth() + 1;
    let startYear = m >= 7 ? y : y - 1;
    if (startYear < FIRST_AU_FY_START_YEAR) startYear = FIRST_AU_FY_START_YEAR;
    raw = `${startYear}-${String((startYear + 1) % 100).padStart(2, "0")}`;
  }
  const match = raw.match(/^(\d{4})[-/](\d{2})$/);
  if (!match) return null;
  const startYear = Number(match[1]);
  const endYy = Number(match[2]);
  if (endYy !== (startYear + 1) % 100) return null;
  const endYear = startYear + 1;
  return {
    token: `${startYear}-${String(endYy).padStart(2, "0")}`,
    start: `${startYear}-07-01`,
    end: `${endYear}-06-30`,
    display: `${startYear}–${String(endYear).slice(2)}`,
    fileSlug: `FY${String(startYear).slice(2)}_${String(endYear).slice(2)}`,
  };
}

/**
 * FY picker options from current FY back to the first supported year (2026–27).
 * Newer years appear first; earlier years are added as each July arrives.
 */
export function listAuFinancialYearOptions(today: Date = new Date()): AuFinancialYear[] {
  const current = parseAuFinancialYear("", today);
  if (!current) return [];
  let currentStart = Number(current.token.slice(0, 4));
  if (currentStart < FIRST_AU_FY_START_YEAR) currentStart = FIRST_AU_FY_START_YEAR;
  const out: AuFinancialYear[] = [];
  for (let y = currentStart; y >= FIRST_AU_FY_START_YEAR; y--) {
    const fy = parseAuFinancialYear(`${y}-${String((y + 1) % 100).padStart(2, "0")}`);
    if (fy) out.push(fy);
  }
  return out;
}
