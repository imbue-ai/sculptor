/**
 * Given a tilde-based input path and the first result path from the backend,
 * attempts to detect the home directory prefix (e.g. "/Users/bob" or "/home/bob").
 *
 * Returns the detected prefix, or undefined if detection isn't possible.
 */
export const detectHomeDirPrefix = (inputPath: string, firstResultPath: string): string | undefined => {
  if (!inputPath.startsWith("~")) return undefined;

  const tildeRest = inputPath.slice(1); // e.g. "/foo" or "/foo/bar"

  if (tildeRest && tildeRest !== "/" && firstResultPath.includes(tildeRest)) {
    const idx = firstResultPath.indexOf(tildeRest);
    return firstResultPath.slice(0, idx);
  }

  if (tildeRest === "" || tildeRest === "/") {
    // Input was just "~" or "~/", parent dir of results is the home dir
    const lastSlash = firstResultPath.lastIndexOf("/");
    if (lastSlash > 0) {
      return firstResultPath.slice(0, lastSlash);
    }
  }

  return undefined;
};
