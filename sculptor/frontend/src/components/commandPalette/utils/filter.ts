/**
 * Custom rank function for the command palette.
 *
 * cmdk passes `(value, search, keywords?)` and expects a positive number
 * where higher = better match and 0 hides the row. We use widely-spaced
 * tiers so that adjustments (page-scoped penalty, primary boost) never
 * reorder commands across tiers — only within a tier.
 *
 * Title tiers (the haystack is the title, parsed out of the cmdk `value`):
 *
 *   exact match            → 1000
 *   full-string prefix     → 500
 *   word-boundary prefix   → 200
 *   contiguous substring   → 50
 *   ordered subsequence    → 1.0 + density bonus (capped under 2.0)
 *   no match               → 0
 *
 * Keywords are scored separately with a CAP at the substring tier (50). A
 * keyword match can never beat a title prefix or exact title match. This
 * fixes the "type 'light' → Toggle Right Panel ranks above Light" bug
 * where 'right' contained an in-order subsequence of 'ight'.
 *
 * The page-scoped penalty (×0.25) only kicks in for commands surfaced from
 * a sub-page when the user is searching at the root. With wide tiers, a
 * penalised exact-title match (1000 × 0.25 = 250) still beats any
 * subsequence match (≤ 2.0).
 */

/**
 * Separator between title and id in the cmdk `value` prop. Imported by
 * CommandPalette.tsx so the producer and consumer never drift.
 */
export const ROW_VALUE_SEP = "__";

/**
 * Build the cmdk `value` for a command row. Encodes title + id so two
 * commands sharing the same title don't collide in cmdk's internal state.
 */
export const buildItemValue = (cmd: { title: string; id: string }): string => `${cmd.title}${ROW_VALUE_SEP}${cmd.id}`;

const norm = (s: string): string => s.toLowerCase();

const SCORE_EXACT = 1000;
const SCORE_PREFIX = 500;
const SCORE_WORD_PREFIX = 200;
const SCORE_SUBSTRING = 50;
const SCORE_SUBSEQ_FLOOR = 1.0;
const SCORE_SUBSEQ_DENSITY = 1.0; // up to ~2.0 with full density

const subsequenceScore = (haystack: string, needle: string): number => {
  if (needle.length === 0) return SCORE_EXACT;
  let i = 0;
  let consecutive = 0;
  let bestRun = 0;
  for (const ch of haystack) {
    if (ch === needle[i]) {
      i += 1;
      consecutive += 1;
      if (consecutive > bestRun) bestRun = consecutive;
    } else {
      consecutive = 0;
    }
    if (i === needle.length) break;
  }
  if (i < needle.length) return 0;
  const density = bestRun / needle.length;
  return SCORE_SUBSEQ_FLOOR + SCORE_SUBSEQ_DENSITY * density;
};

const matchOne = (haystack: string, needle: string, cap: number): number => {
  if (needle === "") return SCORE_EXACT;
  const h = norm(haystack);
  const n = norm(needle);
  let score: number;
  if (h === n) {
    score = SCORE_EXACT;
  } else if (h.startsWith(n)) {
    score = SCORE_PREFIX;
  } else {
    const words = h.split(/[\s\-_.]+/);
    if (words.some((w) => w.startsWith(n))) {
      score = SCORE_WORD_PREFIX;
    } else if (h.includes(n)) {
      score = SCORE_SUBSTRING;
    } else {
      score = subsequenceScore(h, n);
    }
  }
  return Math.min(score, cap);
};

/**
 * Rank the title against the search query, with no cap. The title is the
 * primary haystack and gets full access to the tier ladder.
 */
const rankTitle = (title: string, search: string): number => matchOne(title, search, SCORE_EXACT);

/**
 * Rank a keyword list against the search query, capped at the substring
 * tier. This keeps "right" (a keyword/subsequence somewhere) from beating
 * a real title hit on "Light".
 */
const rankKeywords = (keywords: ReadonlyArray<string>, search: string): number => {
  let best = 0;
  for (const k of keywords) {
    const s = matchOne(k, search, SCORE_SUBSTRING);
    if (s > best) best = s;
    if (best === SCORE_SUBSTRING) break;
  }
  return best;
};

/**
 * cmdk filter. The `value` cmdk hands us is `${title}${ROW_VALUE_SEP}${id}`.
 * We split on the separator so the id slug doesn't pollute the title
 * haystack.
 */
export const paletteFilter = (value: string, search: string, keywords?: Array<string>): number => {
  if (search.trim().length === 0) return SCORE_EXACT;
  const title = value.split(ROW_VALUE_SEP)[0] ?? value;
  const titleScore = rankTitle(title, search);
  const keywordScore = keywords && keywords.length > 0 ? rankKeywords(keywords, search) : 0;
  return Math.max(titleScore, keywordScore);
};

/**
 * Multiplier applied to page-scoped commands when the user is searching at
 * the root. Tiers are wide enough that a penalised exact match (250) still
 * beats any unscoped subsequence match (≤ 2.0); within a tier, the penalty
 * just orders sub-page items below their root counterparts.
 */
const PAGE_SCOPED_PENALTY = 0.25;

/**
 * Multiplier for commands flagged `primary` — applied AFTER the
 * page-scoped penalty so primary page-openers (like "Switch workspace…")
 * still rank above same-tier siblings even when surfaced from a sub-page.
 */
const PRIMARY_BOOST = 1.5;

/**
 * Build a cmdk filter that knows about command scoping, primary
 * commands, and per-command boosts. All adjustments are bounded — the
 * tier ladder is wide enough that the boosts in use today
 * (≤ 8×) cannot promote a subsequence match above a substring match.
 *
 * Factories take callbacks (`isPageScoped`, `isPrimary`, `getBoost`)
 * instead of direct registry access so the filter stays pure and
 * unit-testable.
 */
export const makePaletteFilter = (opts: {
  isPageScoped: (id: string) => boolean;
  isPrimary?: (id: string) => boolean;
  /**
   * Per-command multiplier. Values > 1 boost (e.g. lifting panel toggles
   * above same-tier Settings rows); values strictly between 0 and 1
   * demote (e.g. pushing Settings sub-page rows below any other match).
   * Values ≤ 0 and exactly 1 are ignored — 0 would hide the row outright,
   * which the `when` predicate handles more cleanly.
   */
  getBoost?: (id: string) => number | undefined;
  isAtRoot: boolean;
}): ((value: string, search: string, keywords?: Array<string>) => number) => {
  return (value, search, keywords): number => {
    const score = paletteFilter(value, search, keywords);
    if (score === 0) return score;
    const id = value.split(ROW_VALUE_SEP)[1] ?? "";
    let adjusted = score;
    if (opts.isAtRoot && opts.isPageScoped(id)) {
      adjusted *= PAGE_SCOPED_PENALTY;
    }

    if (opts.isPrimary && opts.isPrimary(id)) {
      adjusted *= PRIMARY_BOOST;
    }

    if (opts.getBoost) {
      const boost = opts.getBoost(id);
      if (boost != null && boost > 0 && boost !== 1) adjusted *= boost;
    }
    return adjusted;
  };
};
