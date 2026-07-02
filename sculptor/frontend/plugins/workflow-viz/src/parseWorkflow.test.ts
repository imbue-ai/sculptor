import { describe, expect, it } from "vitest";

import { parseWorkflowInput } from "./parseWorkflow.ts";

describe("parseWorkflowInput", () => {
  it("extracts name, description, and phases from a meta literal", () => {
    const script = `
      export const meta = {
        name: "Deploy service",
        description: "Ship the current branch to staging",
        phases: [
          { title: "Build", detail: "Compile and bundle" },
          { title: "Test" },
          { title: "Release", detail: "Promote to staging" },
        ],
      };
      export default async function run() {}
    `;
    expect(parseWorkflowInput({ script })).toEqual({
      source: "script",
      name: "Deploy service",
      description: "Ship the current branch to staging",
      phases: [
        { title: "Build", detail: "Compile and bundle" },
        { title: "Test" },
        { title: "Release", detail: "Promote to staging" },
      ],
    });
  });

  it("handles single quotes and a brace inside a string value", () => {
    const script = `export const meta = { name: 'Format { and } braces', phases: [{ title: 'One' }] };`;
    expect(parseWorkflowInput({ script })).toEqual({
      source: "script",
      name: "Format { and } braces",
      phases: [{ title: "One" }],
    });
  });

  it("reads a phases array of bare strings", () => {
    const script = `export const meta = { name: "Bare", phases: ["Alpha", "Beta"] };`;
    expect(parseWorkflowInput({ script })).toEqual({
      source: "script",
      name: "Bare",
      phases: [{ title: "Alpha" }, { title: "Beta" }],
    });
  });

  it("falls back to phase() call sites when meta has no phases", () => {
    const script = `
      export const meta = { name: "Imperative" };
      export default async function run(ctx) {
        await phase("Gather inputs");
        await phase('Do the work');
      }
    `;
    expect(parseWorkflowInput({ script })).toEqual({
      source: "script",
      name: "Imperative",
      phases: [{ title: "Gather inputs" }, { title: "Do the work" }],
    });
  });

  it("recovers phases from phase() calls even without a meta literal", () => {
    const script = `export default async function run() { await phase("Only phase"); }`;
    expect(parseWorkflowInput({ script })).toEqual({
      source: "script",
      phases: [{ title: "Only phase" }],
    });
  });

  it("returns a script parse with empty phases when meta exists but has none", () => {
    const script = `export const meta = { name: "Nameless phases" };`;
    expect(parseWorkflowInput({ script })).toEqual({
      source: "script",
      name: "Nameless phases",
      phases: [],
    });
  });

  it("returns null for a script with neither a meta literal nor phase() calls", () => {
    expect(parseWorkflowInput({ script: "const x = 1; console.log(x);" })).toBeNull();
  });

  it("handles the scriptPath input shape", () => {
    expect(parseWorkflowInput({ scriptPath: "/workflows/deploy.ts" })).toEqual({
      source: "scriptPath",
      scriptPath: "/workflows/deploy.ts",
      phases: [],
    });
  });

  it("handles the named-workflow input shape", () => {
    expect(parseWorkflowInput({ name: "nightly-sync" })).toEqual({
      source: "name",
      name: "nightly-sync",
      phases: [],
    });
  });

  it("prefers script over scriptPath and name when several are present", () => {
    const input = { script: `export const meta = { name: "Wins", phases: [] };`, scriptPath: "/x.ts", name: "y" };
    expect(parseWorkflowInput(input)?.source).toBe("script");
  });

  it("returns null for null input and for an unrecognized shape", () => {
    expect(parseWorkflowInput(null)).toBeNull();
    expect(parseWorkflowInput({ other: "value" })).toBeNull();
    expect(parseWorkflowInput({ script: "" })).toBeNull();
  });

  it("returns null when the meta literal never closes its brace", () => {
    // An unterminated literal yields no meta fields and no phases, so the parse
    // has nothing recognizable to show and declines.
    expect(parseWorkflowInput({ script: `export const meta = { name: "Broken", phases: [` })).toBeNull();
  });
});
