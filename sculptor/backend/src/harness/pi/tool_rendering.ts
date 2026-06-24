// Adapt pi's tool-execution lane onto Sculptor's harness-agnostic tool blocks,
// ported from `pi_agent/tool_rendering.py`. Pi's core tools are lowercase with
// their own arg schemas; Sculptor's renderers key on Claude's PascalCase names
// and arg shapes, so the four core tools are mapped; any other pi tool passes
// through unmapped (rendered generically).

import type {
  DiffToolContent,
  GenericToolContent,
} from "~/harness/claude/stream_parser";

// Claude tool names whose results render as a file chip (DiffToolContent).
const FILE_DIFF_TOOL_NAMES: ReadonlySet<string> = new Set([
  "Write",
  "Edit",
  "MultiEdit",
]);
export const FILE_CHANGE_TOOL_NAMES: ReadonlySet<string> = FILE_DIFF_TOOL_NAMES;

const SIMPLE_NAME_MAP: Readonly<Record<string, string>> = {
  read: "Read",
  write: "Write",
  bash: "Bash",
};

// The pi tool name for the Sculptor-pinned sub-agent extension, mapped onto
// Claude's `Agent` so the frontend groups children under the same pill.
export const SUBAGENT_TOOL_NAME = "subagent";
export const SUBAGENT_DISPLAY_NAME = "Agent";
// The background-task extension tool — deliberately NOT mapped onto a Claude
// name (passes through generically; its lifecycle rides the BackgroundTask*
// contracts).
export const BACKGROUND_TOOL_NAME = "background";

function firstStr(args: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const value = args[key];
    if (typeof value === "string") {
      return value;
    }
  }
  return "";
}

function summarizeSubagentTasks(args: Record<string, unknown>): {
  subagentType: string;
  prompt: string;
} {
  const tasks = args.tasks;
  if (Array.isArray(tasks) && tasks.length > 0) {
    const sections: string[] = [];
    tasks.forEach((entry, index) => {
      if (typeof entry !== "object" || entry === null) {
        return;
      }
      const e = entry as Record<string, unknown>;
      const taskText = firstStr(e, "task");
      if (!taskText) {
        return;
      }
      const label = firstStr(e, "label") || `Sub-agent ${index + 1}`;
      sections.push(`${label}: ${taskText}`);
    });
    return {
      subagentType: `subagent (x${tasks.length})`,
      prompt: sections.join("\n\n"),
    };
  }
  return { subagentType: "subagent", prompt: firstStr(args, "task", "prompt") };
}

function adaptEdits(
  rawEdits: unknown,
): { old_string: string; new_string: string }[] {
  if (!Array.isArray(rawEdits)) {
    return [];
  }
  const adapted: { old_string: string; new_string: string }[] = [];
  for (const edit of rawEdits) {
    if (typeof edit === "object" && edit !== null) {
      const e = edit as Record<string, unknown>;
      adapted.push({
        old_string: typeof e.oldText === "string" ? e.oldText : "",
        new_string: typeof e.newText === "string" ? e.newText : "",
      });
    }
  }
  return adapted;
}

// Map a pi tool name + args onto a Claude tool name + input. Mirrors
// `map_pi_tool_call` (permissive: malformed args yield empty values).
export function mapPiToolCall(
  piToolName: string,
  piArgs: Record<string, unknown>,
): { name: string; input: Record<string, unknown> } {
  const simple = SIMPLE_NAME_MAP[piToolName];
  if (simple !== undefined) {
    if (piToolName === "read") {
      return {
        name: simple,
        input: { file_path: firstStr(piArgs, "path", "file_path") },
      };
    }
    if (piToolName === "write") {
      return {
        name: simple,
        input: {
          file_path: firstStr(piArgs, "path", "file_path"),
          content: firstStr(piArgs, "content"),
        },
      };
    }
    return { name: simple, input: { command: firstStr(piArgs, "command") } };
  }
  if (piToolName === SUBAGENT_TOOL_NAME) {
    const { subagentType, prompt } = summarizeSubagentTasks(piArgs);
    return {
      name: SUBAGENT_DISPLAY_NAME,
      input: { subagent_type: subagentType, prompt },
    };
  }
  if (piToolName === "edit") {
    const filePath = firstStr(piArgs, "path", "file_path");
    const edits = adaptEdits(piArgs.edits);
    if (edits.length === 1) {
      const edit = edits[0] as { old_string: string; new_string: string };
      return {
        name: "Edit",
        input: {
          file_path: filePath,
          old_string: edit.old_string,
          new_string: edit.new_string,
        },
      };
    }
    return { name: "MultiEdit", input: { file_path: filePath, edits } };
  }
  return { name: piToolName, input: { ...piArgs } };
}

// Flatten a pi tool result/partialResult payload to display text. Mirrors
// `extract_text_from_tool_payload`.
export function extractTextFromToolPayload(payload: unknown): string {
  if (payload === null || payload === undefined) {
    return "";
  }
  if (typeof payload === "string") {
    return payload;
  }
  if (typeof payload === "object") {
    const p = payload as Record<string, unknown>;
    if (Object.keys(p).length === 0) {
      return "";
    }
    const content = p.content;
    if (Array.isArray(content)) {
      const texts = content
        .filter(
          (b): b is Record<string, unknown> =>
            typeof b === "object" &&
            b !== null &&
            (b as Record<string, unknown>).type === "text" &&
            typeof (b as Record<string, unknown>).text === "string",
        )
        .map((b) => b.text as string);
      if (texts.length > 0) {
        return texts.join("");
      }
    }
    for (const key of ["text", "result", "output", "message"]) {
      const value = p[key];
      if (typeof value === "string" && value) {
        return value;
      }
    }
  }
  return String(payload);
}

function syntheticNewFileDiff(filePath: string, content: string): string {
  const rel = filePath.replace(/^\/+/, "");
  const lines = content.split("\n");
  const additions = lines.map((l) => "+" + l).join("\n");
  return (
    `diff --git a/${rel} b/${rel}\n` +
    `new file mode 100644\n` +
    `--- /dev/null\n` +
    `+++ b/${rel}\n` +
    `@@ -0,0 +1,${lines.length} @@\n` +
    `${additions}\n`
  );
}

function gitDiffFromPiPatch(filePath: string, patch: string): string {
  const rel = filePath.replace(/^\/+/, "");
  const hunkStart = patch.indexOf("@@");
  if (hunkStart === -1) {
    return `diff --git a/${rel} b/${rel}\n`;
  }
  let hunk = patch.slice(hunkStart);
  if (!hunk.endsWith("\n")) {
    hunk += "\n";
  }
  return `diff --git a/${rel} b/${rel}\n--- a/${rel}\n+++ b/${rel}\n${hunk}`;
}

// Build the rendered result content for a finished tool call. Mirrors
// `build_tool_result_content`: a diff (file chip) for file-mutating tools,
// generic text otherwise.
export function buildToolResultContent(
  claudeName: string,
  claudeInput: Record<string, unknown>,
  resultPayload: unknown,
  fallbackText = "",
): GenericToolContent | DiffToolContent {
  if (FILE_DIFF_TOOL_NAMES.has(claudeName)) {
    const filePath =
      typeof claudeInput.file_path === "string" ? claudeInput.file_path : "";
    let patch: string | null = null;
    if (typeof resultPayload === "object" && resultPayload !== null) {
      const details = (resultPayload as Record<string, unknown>).details;
      if (
        typeof details === "object" &&
        details !== null &&
        typeof (details as Record<string, unknown>).patch === "string"
      ) {
        patch = (details as Record<string, unknown>).patch as string;
      }
    }
    let diff: string;
    if (patch) {
      diff = gitDiffFromPiPatch(filePath, patch);
    } else if (claudeName === "Write") {
      const content =
        typeof claudeInput.content === "string" ? claudeInput.content : "";
      diff = syntheticNewFileDiff(filePath, content);
    } else {
      diff = `diff --git a/${filePath.replace(/^\/+/, "")} b/${filePath.replace(/^\/+/, "")}\n`;
    }
    return { content_type: "diff", diff, file_path: filePath };
  }
  return {
    content_type: "generic",
    text: extractTextFromToolPayload(resultPayload) || fallbackText,
  };
}
