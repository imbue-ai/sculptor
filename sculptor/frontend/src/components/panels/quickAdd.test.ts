import { Folder } from "lucide-react";
import { describe, expect, it } from "vitest";

import { pickQuickAdd } from "./quickAdd.ts";
import type { PanelDefinition } from "./types.ts";

const mk = (id: string): PanelDefinition => ({
  id,
  displayName: id,
  description: id,
  icon: Folder,
  defaultZone: "top-left",
  defaultShortcut: "",
  component: () => null,
});

const kinds = (items: ReturnType<typeof pickQuickAdd>): ReadonlyArray<string> =>
  items.map((item) => (item.kind === "panel" ? item.panel.id : item.kind));

describe("pickQuickAdd", () => {
  it("always offers New agent then New terminal, even with no unplaced panels", () => {
    expect(pickQuickAdd([])).toEqual([{ kind: "create-agent" }, { kind: "create-terminal" }]);
  });

  it("lists every unplaced panel in the fixed priority order", () => {
    const unplaced = ["actions", "browser", "changes", "commits", "files", "notes", "review-all", "skills"].map(mk);
    expect(kinds(pickQuickAdd(unplaced))).toEqual([
      "create-agent",
      "create-terminal",
      "files",
      "changes",
      "commits",
      "browser",
      "review-all",
      "skills",
      "notes",
      "actions",
    ]);
  });

  it("omits panels that are open (not in the unplaced list)", () => {
    // Only browser and notes are unplaced — everything open stays hidden.
    expect(kinds(pickQuickAdd([mk("notes"), mk("browser")]))).toEqual([
      "create-agent",
      "create-terminal",
      "browser",
      "notes",
    ]);
  });

  it("appends unplaced panels the fixed order doesn't know about", () => {
    expect(kinds(pickQuickAdd([mk("files"), mk("experimental-panel")]))).toEqual([
      "create-agent",
      "create-terminal",
      "files",
      "experimental-panel",
    ]);
  });
});
