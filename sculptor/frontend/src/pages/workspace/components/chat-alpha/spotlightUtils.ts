import type { SpotlightData } from "~/pages/workspace/components/diffPanel/types.ts";

const SPOTLIGHT_SPAN_RE =
  /<span\s+data-sculptor-node(?:\s+[^>]*)?\s+data-spotlight-file="([^"]*)"[^>]*>([\s\S]*?)<\/span>/g;

type ExtractedSpotlight = SpotlightData;

const escapeAngleBrackets = (value: string): string => value.replace(/</g, "&lt;").replace(/>/g, "&gt;");

const unescapeHtml = (value: string): string =>
  value
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");

const extractAttribute = (span: string, name: string): string | undefined => {
  const re = new RegExp(`data-spotlight-${name}="([^"]*)"`, "i");
  const match = re.exec(span);
  return match?.[1] !== undefined ? unescapeHtml(match[1]) : undefined;
};

const parseSpotlightSpan = (span: string): ExtractedSpotlight | null => {
  const file = extractAttribute(span, "file");
  if (!file) return null;
  return {
    file,
    lineStart: parseInt(extractAttribute(span, "line-start") ?? "0", 10),
    lineEnd: parseInt(extractAttribute(span, "line-end") ?? "0", 10),
    side: (extractAttribute(span, "side") as "old" | "new" | null) || null,
    snippet: extractAttribute(span, "snippet") || "",
    snippetCapturedAt: extractAttribute(span, "snippet-captured-at") || "",
    scope: (extractAttribute(span, "scope") as SpotlightData["scope"]) || "file-view",
    commitRef: extractAttribute(span, "commit-ref"),
  };
};

export const extractSpotlightsFromMarkdown = (markdown: string): Array<ExtractedSpotlight> => {
  const spotlights: Array<ExtractedSpotlight> = [];
  for (const match of markdown.matchAll(SPOTLIGHT_SPAN_RE)) {
    const parsed = parseSpotlightSpan(match[0]);
    if (parsed) {
      spotlights.push(parsed);
    }
  }
  return spotlights;
};

const formatSpotlightEntry = (s: ExtractedSpotlight): string => {
  const range = s.lineStart === s.lineEnd ? `${s.lineStart}` : `${s.lineStart}-${s.lineEnd}`;
  const fileRef = s.side ? `${s.file}:${range} (${s.side})` : `${s.file}:${range}`;
  const snippetLine = `  ${s.snippet.split("\n")[0]}`;
  return `- ${fileRef}:\n${escapeAngleBrackets(snippetLine)}`;
};

export const buildSpotlightSystemReminder = (spotlights: Array<ExtractedSpotlight>): string | null => {
  if (spotlights.length === 0) return null;

  const capturedAt = spotlights[0].snippetCapturedAt || new Date().toISOString();
  const scopes = new Set(spotlights.map((s) => s.scope));
  const hasDiff = scopes.has("uncommitted-diff") || scopes.has("target-branch-diff");
  const hasCommitDiff = scopes.has("commit-diff");
  const isFileView = scopes.size === 1 && scopes.has("file-view");

  const entries = spotlights.map(formatSpotlightEntry).join("\n\n");

  let caveat = "";
  if (isFileView) {
    caveat = "The file may have changed since capture.";
  } else if (hasCommitDiff) {
    const commitRefs = spotlights.filter((s) => s.commitRef).map((s) => s.commitRef);
    const uniques = [...new Set(commitRefs)];
    caveat = "These files may have changed since capture. Use the quoted snippets if the line numbers no longer match.";
    if (uniques.length > 0) {
      caveat += `\nTo see the full diff context, run: git show ${uniques[0]}`;
    }

    if (uniques.length > 1) {
      caveat += `\nAll commits referenced: ${uniques.join(" ")}`;
    }
  } else if (hasDiff) {
    caveat =
      "These files may have changed since capture. Use the quoted snippets if the line numbers no longer match. For the diff hunk context, see the current uncommitted changes.";
  }

  return `<system-reminder>
Spotlight references captured at ${capturedAt}:

${entries}

${caveat}
</system-reminder>
`;
};
