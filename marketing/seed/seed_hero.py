"""Seed the primary hero workspace: a sculptor agent mid-feature.

Produces a workspace on `feat/semantic-command-palette` (which the gh-shim PR
fixture renders as an open PR with green checks) containing a coherent
multi-file change, three commits plus uncommitted edits, a todo list, and a
canned test run — all scripted deterministically through FakeClaude.

Reuses the existing sculptor demo clone (other seeded workspaces hold worktrees
in it); run seed_all.py for a full fresh re-seed.

Run from the repo root:  uv run --project sculptor python marketing/seed/seed_hero.py
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fakeclaude import interleaved_prompt, tool, txt
from harness_client import (
    client,
    create_agent,
    create_workspace,
    delete_workspaces_by_branch,
    ensure_project,
    free_branch,
    wait_until_ready,
)
from repos import ensure_clone

PALETTE_DIR = "sculptor/frontend/src/components/CommandPalette"

SEMANTIC_RANKER = '''\
import type { Command } from "./types";

/**
 * Ranks command-palette entries by how well they match a free-text query,
 * blending exact-substring hits with lightweight token-overlap so the palette
 * can surface commands by intent, not just by literal prefix.
 */
export interface RankedCommand {
  command: Command;
  score: number;
}

const tokenize = (value: string): string[] =>
  value.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);

export function rankCommands(query: string, commands: Command[]): RankedCommand[] {
  const queryTokens = tokenize(query);
  if (queryTokens.length === 0) {
    return commands.map((command) => ({ command, score: 0 }));
  }
  return commands
    .map((command) => ({ command, score: scoreCommand(queryTokens, command) }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score);
}

function scoreCommand(queryTokens: string[], command: Command): number {
  const haystack = `${command.title} ${command.keywords?.join(" ") ?? ""}`.toLowerCase();
  const haystackTokens = new Set(tokenize(haystack));
  let score = 0;
  for (const token of queryTokens) {
    if (haystack.includes(token)) {
      score += 2;
    } else if ([...haystackTokens].some((h) => h.startsWith(token))) {
      score += 1;
    }
  }
  return score;
}
'''

RANKER_TEST = '''\
import { describe, expect, it } from "vitest";

import { rankCommands } from "./semanticRanker";

const commands = [
  { id: "toggle-terminal", title: "Toggle terminal panel", keywords: ["shell", "console"] },
  { id: "open-diff", title: "Open changes / diff", keywords: ["git", "review"] },
  { id: "new-workspace", title: "Create new workspace", keywords: ["agent", "branch"] },
];

describe("rankCommands", () => {
  it("ranks intent matches above unrelated commands", () => {
    const ranked = rankCommands("review git", commands);
    expect(ranked[0]?.command.id).toBe("open-diff");
  });

  it("returns nothing for a query with no overlap", () => {
    expect(rankCommands("deploy kubernetes", commands)).toHaveLength(0);
  });
});
'''

PALETTE_CONFIG = '''\
export interface PaletteConfig {
  maxResults: number;
  showRecent: boolean;
}

export const defaultPaletteConfig: PaletteConfig = {
  maxResults: 8,
  showRecent: true,
};
'''

USE_SEMANTIC_SEARCH = '''\
import { useMemo } from "react";

import { defaultPaletteConfig } from "./paletteConfig";
import { rankCommands } from "./semanticRanker";
import type { Command } from "./types";

/**
 * Returns palette commands ordered by semantic relevance to `query`, capped at
 * the configured result limit. Falls back to the full list for an empty query so
 * the palette still shows recent and most-used entries.
 */
export function useSemanticSearch(query: string, commands: Command[]): Command[] {
  return useMemo(() => {
    const ranked = rankCommands(query, commands);
    return ranked.slice(0, defaultPaletteConfig.maxResults).map((entry) => entry.command);
  }, [query, commands]);
}
'''

SEMANTIC_HINT = '''\
import { Flex, Text } from "@radix-ui/themes";

/**
 * Inline affordance under the palette input nudging users that they can search
 * by intent ("review my changes") instead of recalling exact command names.
 */
export function SemanticSearchHint() {
  return (
    <Flex align="center" gap="2" px="3" py="1">
      <Text size="1" color="gray">
        Tip: search by intent — try "review my changes" or "start a new agent"
      </Text>
    </Flex>
  );
}
'''

CANNED_TEST_RUN = (
    "printf '%s\\n' "
    "' RUN  v2.1.9  ' "
    "' ✓ src/components/CommandPalette/semanticRanker.test.ts (2 tests) 7ms' "
    "'' "
    "' Test Files  1 passed (1)' "
    "'      Tests  2 passed (2)' "
    "'   Duration  438ms'"
)


TYPES_TS = '''\
/** A single command-palette entry the ranker and UI operate on. */
export interface Command {
  id: string;
  title: string;
  keywords?: string[];
  run: () => void;
}
'''

HIGHLIGHT_MATCH = '''\
export interface HighlightSegment {
  text: string;
  matched: boolean;
}

/**
 * Splits a command title into highlighted / plain segments for the query, so the
 * palette can bold the characters that matched what the user typed.
 */
export function highlightMatch(title: string, query: string): HighlightSegment[] {
  const needle = query.trim().toLowerCase();
  if (needle.length === 0) {
    return [{ text: title, matched: false }];
  }
  const segments: HighlightSegment[] = [];
  let rest = title;
  while (rest.length > 0) {
    const idx = rest.toLowerCase().indexOf(needle);
    if (idx === -1) {
      segments.push({ text: rest, matched: false });
      break;
    }
    if (idx > 0) {
      segments.push({ text: rest.slice(0, idx), matched: false });
    }
    segments.push({ text: rest.slice(idx, idx + needle.length), matched: true });
    rest = rest.slice(idx + needle.length);
  }
  return segments;
}
'''

HIGHLIGHT_TEST = '''\
import { describe, expect, it } from "vitest";

import { highlightMatch } from "./highlightMatch";

describe("highlightMatch", () => {
  it("marks the matched span", () => {
    const segs = highlightMatch("Open changes", "chan");
    expect(segs.filter((s) => s.matched).map((s) => s.text)).toEqual(["chan"]);
  });

  it("returns the whole title as unmatched for an empty query", () => {
    expect(highlightMatch("Toggle terminal", "")).toEqual([{ text: "Toggle terminal", matched: false }]);
  });
});
'''

PALETTE_RESULTS = '''\
import { Flex, Text } from "@radix-ui/themes";

import { highlightMatch } from "./highlightMatch";
import type { Command } from "./types";
import { useSemanticSearch } from "./useSemanticSearch";

interface Props {
  query: string;
  commands: Command[];
}

/** The ranked, highlighted results list rendered under the palette input. */
export function CommandPaletteResults({ query, commands }: Props) {
  const results = useSemanticSearch(query, commands);
  return (
    <Flex direction="column">
      {results.map((command) => (
        <Flex key={command.id} align="center" px="3" py="1" gap="2">
          <Text size="2">
            {highlightMatch(command.title, query).map((seg, i) => (
              <Text key={i} weight={seg.matched ? "bold" : "regular"}>
                {seg.text}
              </Text>
            ))}
          </Text>
        </Flex>
      ))}
    </Flex>
  );
}
'''


def _commit(msg: str) -> dict:
    # The demo clone carries a neutral committer identity (repos.py), so a
    # plain commit never puts the user's real name in a screenshot. shlex.quote
    # keeps quotes/$/backticks in a message from breaking the scripted line.
    return tool(
        "Bash",
        command=f"git add -A && git commit -q -m {shlex.quote(msg)}",
        description=f"Commit: {msg}",
    )


def build_prompt() -> str:
    blocks = [
        txt(
            "I'll add semantic ranking to the command palette so it matches commands by "
            "intent, not just literal prefix — ranking core first, then match highlighting, "
            "then wiring it into the UI."
        ),
        tool("TaskCreate", id="1", subject="Add semantic ranking core", status="in_progress",
             activeForm="Adding semantic ranking core"),
        tool("Write", file_path=f"{PALETTE_DIR}/types.ts", content=TYPES_TS),
        tool("Write", file_path=f"{PALETTE_DIR}/semanticRanker.ts", content=SEMANTIC_RANKER),
        tool("Write", file_path=f"{PALETTE_DIR}/semanticRanker.test.ts", content=RANKER_TEST),
        _commit("Add semantic ranking core for the command palette"),
        tool("TaskUpdate", id="1", status="completed"),
        tool("TaskCreate", id="2", subject="Highlight matched tokens in results", status="in_progress",
             activeForm="Highlighting matched tokens"),
        txt("Ranking core is in. Now highlighting the characters that matched the query."),
        tool("Write", file_path=f"{PALETTE_DIR}/highlightMatch.ts", content=HIGHLIGHT_MATCH),
        tool("Write", file_path=f"{PALETTE_DIR}/highlightMatch.test.ts", content=HIGHLIGHT_TEST),
        _commit("Highlight matched tokens in palette results"),
        tool("TaskUpdate", id="2", status="completed"),
        tool("TaskCreate", id="3", subject="Wire ranking + highlight into the palette UI", status="in_progress",
             activeForm="Wiring the palette UI"),
        tool("Write", file_path=f"{PALETTE_DIR}/paletteConfig.ts", content=PALETTE_CONFIG),
        _commit("Add palette config with a semantic-search flag"),
        txt("Config committed. Wiring the hook, results list, and intent hint into the palette."),
        tool("Edit", file_path=f"{PALETTE_DIR}/paletteConfig.ts",
             old_string="  maxResults: 8,\n  showRecent: true,\n};",
             new_string="  maxResults: 8,\n  showRecent: true,\n  enableSemanticSearch: true,\n};"),
        tool("Write", file_path=f"{PALETTE_DIR}/useSemanticSearch.ts", content=USE_SEMANTIC_SEARCH),
        tool("Write", file_path=f"{PALETTE_DIR}/CommandPaletteResults.tsx", content=PALETTE_RESULTS),
        tool("Write", file_path=f"{PALETTE_DIR}/SemanticSearchHint.tsx", content=SEMANTIC_HINT),
        tool("Bash", command=CANNED_TEST_RUN, description="Run the palette tests"),
        tool("TaskUpdate", id="3", status="completed"),
        txt(
            'Semantic ranking, match highlighting, and the results list are in and the tests pass — '
            'three commits on the branch. The palette now scores entries by token overlap, so '
            '"review my changes" surfaces the diff command even though it shares no prefix. '
            "Left the UI wiring uncommitted for review."
        ),
    ]
    return interleaved_prompt(blocks)


BRANCH = "feat/semantic-command-palette"
NAME = "Semantic command palette"


def main() -> None:
    c = client()
    print(f"Seeding hero workspace ({BRANCH})...")
    clone = ensure_clone("sculptor")
    assert clone is not None  # the sculptor repo always resolves (this checkout)
    project_id = ensure_project(clone["path"], c)
    removed = delete_workspaces_by_branch(project_id, BRANCH, c)
    free_branch(clone["path"], BRANCH)
    if removed:
        print(f"  removed {removed} stale workspace(s) on {BRANCH}")
    ws = create_workspace(
        project_id=project_id,
        branch_name=BRANCH,
        name=NAME,
        source_branch=clone["default_branch"],
        target_branch=clone["default_branch"],
        c=c,
    )
    agent = create_agent(workspace_id=ws, prompt=build_prompt(), model_alias="fake", name=NAME, c=c)
    print(f"  workspace={ws}\n  agent={agent}")
    status = wait_until_ready(ws, agent, c)
    print(f"  agent status: {status}")


if __name__ == "__main__":
    main()
