import { existsSync, readFileSync } from "node:fs";

// Parse a `.env` file into a mapping of variable names to values. Mirrors
// sculptor/sculptor/services/workspace_service/environment_manager/env_file_parser.py:
// supports `export` prefixes, single/double quoted values, and inline comments.
// Returns an empty mapping if the file does not exist. (Task 7.6 layers the
// global/project precedence on top of this primitive.)

function extractValue(rawValue: string): string {
  if (rawValue.startsWith('"')) {
    const closeIndex = rawValue.indexOf('"', 1);
    return closeIndex === -1
      ? rawValue.slice(1)
      : rawValue.slice(1, closeIndex);
  }
  if (rawValue.startsWith("'")) {
    const closeIndex = rawValue.indexOf("'", 1);
    return closeIndex === -1
      ? rawValue.slice(1)
      : rawValue.slice(1, closeIndex);
  }
  const spaceHashIndex = rawValue.indexOf(" #");
  const trimmed =
    spaceHashIndex === -1 ? rawValue : rawValue.slice(0, spaceHashIndex);
  return trimmed.trim();
}

export function parseEnvFile(path: string): Record<string, string> {
  if (!existsSync(path)) {
    return {};
  }
  const result: Record<string, string> = {};
  for (const line of readFileSync(path, "utf8").split(/\r?\n/)) {
    let stripped = line.trim();
    if (stripped === "" || stripped.startsWith("#")) {
      continue;
    }
    if (stripped.startsWith("export ")) {
      stripped = stripped.slice("export ".length);
    }
    const eqIndex = stripped.indexOf("=");
    if (eqIndex === -1) {
      continue;
    }
    const name = stripped.slice(0, eqIndex).trim();
    if (name === "" || name.includes(" ") || name.includes("\t")) {
      continue;
    }
    result[name] = extractValue(stripped.slice(eqIndex + 1));
  }
  return result;
}

export function parseEnvFileNames(path: string): string[] {
  return Object.keys(parseEnvFile(path));
}
