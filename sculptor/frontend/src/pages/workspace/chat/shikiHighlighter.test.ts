import { describe, expect, it } from "vitest";

import { highlightCode } from "./shikiHighlighter.ts";

const THEMES = { light: "github-light", dark: "github-dark" };

describe("highlightCode", () => {
  it("returns tokens for a supported language", async () => {
    const result = await highlightCode("const x = 1;", "javascript", THEMES);
    expect(result).not.toBeNull();
    expect(result!.length).toBeGreaterThan(0);
    // Each line is an array of tokens with content
    for (const line of result!) {
      for (const token of line) {
        expect(typeof token.content).toBe("string");
      }
    }
  });

  it("returns null for an unsupported language", async () => {
    const result = await highlightCode("x", "not-a-real-language-xyz", THEMES);
    expect(result).toBeNull();
  });

  it("produces tokens with dual-theme colors", async () => {
    const result = await highlightCode("function hello() {}", "javascript", THEMES);
    expect(result).not.toBeNull();
    // At least one token should have color information
    const allTokens = result!.flat();
    const tokensWithColor = allTokens.filter((t) => t.lightColor || t.darkColor);
    expect(tokensWithColor.length).toBeGreaterThan(0);
  });

  it("produces multiple lines for multi-line code", async () => {
    const code = "const a = 1;\nconst b = 2;\nconst c = 3;";
    const result = await highlightCode(code, "javascript", THEMES);
    expect(result).not.toBeNull();
    expect(result!.length).toBe(3);
  });

  it("handles empty code without crashing", async () => {
    const result = await highlightCode("", "javascript", THEMES);
    expect(result).not.toBeNull();
    // Shiki produces at least one (empty) line
    expect(result!.length).toBeGreaterThanOrEqual(1);
  });

  it("preserves token content so concatenation reconstructs the source", async () => {
    const code = "if (x > 0) { return true; }";
    const result = await highlightCode(code, "javascript", THEMES);
    expect(result).not.toBeNull();
    const reconstructed = result!.map((line) => line.map((t) => t.content).join("")).join("\n");
    expect(reconstructed).toBe(code);
  });
});
