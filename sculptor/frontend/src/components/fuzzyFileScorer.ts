/**
 * Fuzzy file path scorer.
 *
 * Key design choices:
 * - Character pre-filter: quickly rejects paths that cannot possibly match
 *   (all query chars must appear as a subsequence in the path). This
 *   eliminates ~95% of candidates in O(n+m) before any scoring begins.
 * - Filename bias: tries to match the query against just the final path
 *   segment first and multiplies the score by FILENAME_BONUS_MULTIPLIER.
 *   Matches in the filename are almost always what the user wants.
 * - Scoring bonuses: consecutive matches, word-boundary matches (/, ., -, _,
 *   space, camelCase transitions), and start-of-string matches all score
 *   higher.
 * - Compactness: a dense match (query chars close together) scores higher
 *   than a sparse one, implemented via a density ratio multiplier.
 */

const WORD_BOUNDARY_CHARS = new Set(["/", ".", "-", "_", " "]);

const CONSECUTIVE_BONUS = 5;
const WORD_BOUNDARY_BONUS = 8;
const START_BONUS = 10;
const FILENAME_BONUS_MULTIPLIER = 1.5;
const MAX_RESULTS = 200;

/**
 * Returns true if every character of `query` appears in `str` as a
 * subsequence (i.e. in order, not necessarily adjacent). Both are expected
 * to already be lower-cased by the caller.
 */
const isSubsequence = (query: string, str: string): boolean => {
  let strIdx = 0;
  for (let qi = 0; qi < query.length; qi++) {
    strIdx = str.indexOf(query[qi], strIdx);
    if (strIdx === -1) return false;
    strIdx++;
  }
  return true;
};

/**
 * Score `query` against a single string segment. `lowerStr` is the
 * lower-cased version of `originalStr`; both must be the same length.
 * Returns 0 if not all query characters can be matched in order.
 */
const scoreAgainstString = (query: string, lowerStr: string, originalStr: string): number => {
  let score = 0;
  let strIdx = 0;
  let consecutiveCount = 0;
  let firstMatch = -1;
  let lastMatch = -1;

  for (let qi = 0; qi < query.length; qi++) {
    const found = lowerStr.indexOf(query[qi], strIdx);
    if (found === -1) return 0;

    if (firstMatch === -1) firstMatch = found;
    lastMatch = found;

    // Consecutive match bonus (exponential per run)
    if (found === strIdx) {
      consecutiveCount++;
      score += CONSECUTIVE_BONUS * consecutiveCount;
    } else {
      consecutiveCount = 0;
    }

    // Word-boundary bonus: match starts a new word
    if (found === 0 || WORD_BOUNDARY_CHARS.has(lowerStr[found - 1])) {
      score += WORD_BOUNDARY_BONUS;
    }

    // camelCase boundary bonus: lowercase char immediately before uppercase
    if (
      found > 0 &&
      originalStr[found - 1] >= "a" &&
      originalStr[found - 1] <= "z" &&
      originalStr[found] >= "A" &&
      originalStr[found] <= "Z"
    ) {
      score += WORD_BOUNDARY_BONUS;
    }

    strIdx = found + 1;
  }

  // Bonus for matching at the very start of the string
  if (firstMatch === 0) score += START_BONUS;

  // Compactness: scale by density of the match window.
  // Dense matches (query chars close together) score higher than sparse ones.
  if (firstMatch !== -1 && lastMatch !== firstMatch) {
    const span = lastMatch - firstMatch + 1;
    score *= query.length / span;
  }

  return score;
};

export type ScoredFile = {
  path: string;
  score: number;
};

/**
 * Score a single `query` against a file `path`.
 * Returns 0 if the path does not match the query.
 */
export const scoreFilePath = (query: string, path: string): number => {
  if (query.length === 0) return 0;

  const lowerQuery = query.toLowerCase();
  const lowerPath = path.toLowerCase();

  // Fast pre-filter: reject paths that don't contain all query chars in order
  if (!isSubsequence(lowerQuery, lowerPath)) return 0;

  // Prefer matches in the filename (last segment)
  const lastSlash = path.lastIndexOf("/");
  const filename = lastSlash === -1 ? path : path.slice(lastSlash + 1);
  const lowerFilename = filename.toLowerCase();

  const filenameScore = scoreAgainstString(lowerQuery, lowerFilename, filename);
  if (filenameScore > 0) {
    return filenameScore * FILENAME_BONUS_MULTIPLIER;
  }

  // Fall back to matching against the full path
  return scoreAgainstString(lowerQuery, lowerPath, path);
};

/**
 * Score `query` against all `paths`, returning the top `maxResults` results
 * sorted by descending score.
 */
export const fuzzySearchFiles = (
  query: string,
  paths: ReadonlyArray<string>,
  maxResults: number = MAX_RESULTS,
): Array<ScoredFile> => {
  if (query.length === 0) return [];

  const results: Array<ScoredFile> = [];
  for (const path of paths) {
    const score = scoreFilePath(query, path);
    if (score > 0) {
      results.push({ path, score });
    }
  }

  results.sort((a, b) => b.score - a.score);
  return results.length <= maxResults ? results : results.slice(0, maxResults);
};
