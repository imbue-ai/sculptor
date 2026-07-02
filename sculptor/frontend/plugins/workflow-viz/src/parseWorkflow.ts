/**
 * Parses the input of Claude Code's `Workflow` tool into a small, display-ready
 * shape. The tool's input arrives in one of three forms:
 *
 * - `{ script: "<js source>" }` — an inline workflow script whose first
 *   statement is `export const meta = { name, description, phases: [...] }`.
 * - `{ scriptPath: "<path>" }` — a reference to a script file on disk; the
 *   source text is not available to the renderer, so only the path is shown.
 * - `{ name: "<saved workflow name>" }` — a workflow saved under a name.
 *
 * The script is parsed with lenient string extraction (regex + bracket
 * matching), never `eval`/`new Function`/dynamic import: agent-authored code
 * must never execute in the renderer. Extraction is best-effort — a field it
 * cannot recover is simply omitted rather than failing the whole parse.
 *
 * `parseWorkflowInput` returns `null` for any input shape it does not
 * understand, which is what the plugin's `canRender` keys off to decline the
 * call and fall back to stock rendering.
 */

/** One phase of a workflow, as recovered from the script. */
export type WorkflowPhase = {
  title: string;
  detail?: string;
};

/** The three input shapes discriminated by which field is present. */
export type WorkflowSource = "script" | "scriptPath" | "name";

/** A parsed `Workflow` tool input, ready to render. */
export type ParsedWorkflow = {
  source: WorkflowSource;
  /** The workflow's display name, when recoverable (script `meta.name` or the saved name). */
  name?: string;
  /** The workflow's description from `meta.description`, when present. */
  description?: string;
  /** Phases in declaration order. Empty when none could be recovered. */
  phases: ReadonlyArray<WorkflowPhase>;
  /** The referenced file path, for the `scriptPath` shape. */
  scriptPath?: string;
};

/**
 * Returns the substring of `source` for the object/array literal that opens at
 * `openIndex` (which must point at `{` or `[`), balancing brackets while
 * skipping over string and template literals so a brace inside a string does
 * not end the match early. Returns `null` if the literal never closes.
 */
const matchBalanced = (source: string, openIndex: number): string | null => {
  const open = source[openIndex];
  const close = open === "{" ? "}" : "]";
  let depth = 0;
  let quote: string | null = null;
  for (let i = openIndex; i < source.length; i++) {
    const char = source[i];
    if (quote !== null) {
      if (char === "\\") {
        i++; // skip the escaped character
        continue;
      }
      if (char === quote) quote = null;
      continue;
    }
    if (char === '"' || char === "'" || char === "`") {
      quote = char;
      continue;
    }
    if (char === open) depth++;
    else if (char === close) {
      depth--;
      if (depth === 0) return source.slice(openIndex, i + 1);
    }
  }
  return null;
};

/**
 * Reads a single-line string value for `key` out of an object-literal body,
 * e.g. `name: "Deploy"` → `Deploy`. Handles single, double, and backtick
 * quotes but only flat (non-interpolated) values, which covers the metadata a
 * workflow's `meta` literal carries.
 */
const extractStringField = (body: string, key: string): string | undefined => {
  const pattern = new RegExp(`${key}\\s*:\\s*(['"\`])((?:\\\\.|(?!\\1).)*)\\1`);
  const match = body.match(pattern);
  if (!match) return undefined;
  // Un-escape the common escapes; leave everything else verbatim.
  return match[2].replace(/\\(['"`\\])/g, "$1");
};

/**
 * Extracts phases from a `phases: [ ... ]` array literal. Each entry is either
 * an object with a `title` (and optional `detail`) or a bare string. Entries
 * whose title cannot be recovered are dropped.
 */
const extractPhasesFromMeta = (body: string): ReadonlyArray<WorkflowPhase> => {
  const arrayStart = body.search(/phases\s*:\s*\[/);
  if (arrayStart === -1) return [];
  const bracketIndex = body.indexOf("[", arrayStart);
  const literal = matchBalanced(body, bracketIndex);
  if (literal === null) return [];

  const phases: Array<WorkflowPhase> = [];
  // Walk each top-level object entry `{ ... }` inside the array.
  for (let i = 0; i < literal.length; i++) {
    if (literal[i] !== "{") continue;
    const objectLiteral = matchBalanced(literal, i);
    if (objectLiteral === null) break;
    i += objectLiteral.length - 1;
    const title = extractStringField(objectLiteral, "title");
    if (title === undefined) continue;
    const detail = extractStringField(objectLiteral, "detail");
    phases.push(detail === undefined ? { title } : { title, detail });
  }
  if (phases.length > 0) return phases;

  // No object entries — fall back to treating the array as bare strings.
  const stringEntries = literal.matchAll(/(['"`])((?:\\.|(?!\1).)*)\1/g);
  for (const entry of stringEntries) {
    phases.push({ title: entry[2].replace(/\\(['"`\\])/g, "$1") });
  }
  return phases;
};

/**
 * Recovers phases from `phase('…')` call sites in the script body, the fallback
 * for scripts that drive their phases imperatively instead of declaring them in
 * `meta.phases`.
 */
const extractPhasesFromCalls = (script: string): ReadonlyArray<WorkflowPhase> => {
  const phases: Array<WorkflowPhase> = [];
  const calls = script.matchAll(/\bphase\s*\(\s*(['"`])((?:\\.|(?!\1).)*)\1/g);
  for (const call of calls) {
    phases.push({ title: call[2].replace(/\\(['"`\\])/g, "$1") });
  }
  return phases;
};

/**
 * Parses a workflow script's leading `export const meta = { ... }` literal for
 * name/description/phases, falling back to `phase('…')` call sites for phases
 * when `meta.phases` is absent. Returns `null` when nothing recognizable was
 * recovered (no name, no description, no phases), so a plain non-workflow string
 * declines rather than rendering empty.
 */
const parseScript = (script: string): ParsedWorkflow | null => {
  const metaStart = script.search(/export\s+const\s+meta\s*=\s*\{/);
  let name: string | undefined;
  let description: string | undefined;
  let phases: ReadonlyArray<WorkflowPhase> = [];

  if (metaStart !== -1) {
    const braceIndex = script.indexOf("{", metaStart);
    const metaBody = matchBalanced(script, braceIndex);
    if (metaBody !== null) {
      name = extractStringField(metaBody, "name");
      description = extractStringField(metaBody, "description");
      phases = extractPhasesFromMeta(metaBody);
    }
  }

  if (phases.length === 0) {
    phases = extractPhasesFromCalls(script);
  }

  // Nothing recognizable was recovered (no meta fields, no phases) — decline so
  // stock rendering handles the call. This also covers a `meta` literal whose
  // brace never closes, which yields no fields.
  if (name === undefined && description === undefined && phases.length === 0) return null;

  const parsed: ParsedWorkflow = { source: "script", phases };
  if (name !== undefined) parsed.name = name;
  if (description !== undefined) parsed.description = description;
  return parsed;
};

const asString = (value: unknown): string | undefined =>
  typeof value === "string" && value.length > 0 ? value : undefined;

export const parseWorkflowInput = (input: Readonly<Record<string, unknown>> | null): ParsedWorkflow | null => {
  if (input === null) return null;

  const script = asString(input.script);
  if (script !== undefined) return parseScript(script);

  const scriptPath = asString(input.scriptPath);
  if (scriptPath !== undefined) return { source: "scriptPath", scriptPath, phases: [] };

  const name = asString(input.name);
  if (name !== undefined) return { source: "name", name, phases: [] };

  return null;
};
