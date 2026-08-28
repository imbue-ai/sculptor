import { parse as parseYaml } from "yaml";

// Splitting frontmatter off the top of a `.md` file before it reaches
// `react-markdown`. Without this, a leading `---\nkey: value\n---` block is
// parsed by CommonMark as a setext heading (the closing `---` underlines the
// `key: value` lines into a giant `<h2>`), which is the visually-broken
// rendering this module fixes. The body returned here has the block removed,
// and the parsed metadata is rendered separately by `FrontmatterBlock`.

export type FrontmatterLang = "yaml" | "toml";

export type ParsedFrontmatter = {
  lang: FrontmatterLang;
  /** The text between the fences, verbatim (no surrounding delimiters). */
  raw: string;
  /**
   * The parsed key/value mapping, or `null` when the block isn't a mapping we
   * can render as rows — a YAML parse error, a non-object YAML scalar, or TOML
   * (not parsed into rows yet). `FrontmatterBlock` falls back to showing `raw`
   * when this is `null`, so nothing is silently dropped.
   */
  data: Record<string, unknown> | null;
};

export type FrontmatterParseResult = {
  frontmatter: ParsedFrontmatter | null;
  /** The document with any leading frontmatter block removed. */
  body: string;
};

type FenceSpec = { lang: FrontmatterLang; marker: string; markerPattern: string };

// Frontmatter is a fenced block at the very start of the file: YAML between
// `---` lines or TOML between `+++` lines. By only matching at offset 0 we
// leave a `---` thematic break later in the document untouched. The closing
// fence must sit on its own line. This matches the de-facto convention used by
// Jekyll, Hugo, Astro, and Obsidian.
const FENCES: ReadonlyArray<FenceSpec> = [
  { lang: "yaml", marker: "---", markerPattern: "---" },
  { lang: "toml", marker: "+++", markerPattern: "\\+\\+\\+" },
];

type FrontmatterSplit = { lang: FrontmatterLang; raw: string; body: string };

const splitFrontmatter = (content: string): FrontmatterSplit | null => {
  for (const fence of FENCES) {
    // Opening fence: the marker alone on the first line (trailing spaces/tabs
    // tolerated). `+++` standalone is a valid TOML opener but never a valid
    // markdown construct, so there's no ambiguity to guard against there;
    // `---` is only ambiguous mid-document, which offset-0 anchoring avoids.
    const open = new RegExp(`^${fence.markerPattern}[ \\t]*\\r?\\n`).exec(content);
    if (!open) continue;
    const rest = content.slice(open[0].length);
    // Closing fence: the same marker on its own line. A trailing newline after
    // it is consumed so the rendered body doesn't start with a blank line.
    const close = new RegExp(`\\r?\\n${fence.markerPattern}[ \\t]*(?:\\r?\\n|$)`).exec(rest);
    if (!close) continue;
    return {
      lang: fence.lang,
      raw: rest.slice(0, close.index),
      // Drop the blank lines that conventionally separate the closing fence
      // from the first real content, so the rendered body starts at the
      // heading/paragraph rather than a stray blank line.
      body: rest.slice(close.index + close[0].length).replace(/^(?:\r?\n)+/, ""),
    };
  }
  return null;
};

const parseYamlMapping = (raw: string): Record<string, unknown> | null => {
  try {
    const parsed: unknown = parseYaml(raw);
    if (parsed != null && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
    return null;
  } catch {
    return null;
  }
};

export const parseFrontmatter = (content: string): FrontmatterParseResult => {
  const split = splitFrontmatter(content);
  if (!split) return { frontmatter: null, body: content };
  const { lang, raw, body } = split;
  // TOML is detected and stripped (so it never mis-renders), but parsing its
  // body into key/value rows is a follow-up — it renders from `raw` for now.
  const data = lang === "yaml" ? parseYamlMapping(raw) : null;
  return { frontmatter: { lang, raw, data }, body };
};
