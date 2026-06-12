/**
 * Tests for the sculptor/no-var-fallback stylelint rule.
 *
 * Run with: node --test scripts/stylelint-plugin-design-tokens/no-var-fallback.test.mjs
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import stylelint from "stylelint";

const config = {
  plugins: ["./scripts/stylelint-plugin-design-tokens/index.js"],
  rules: {
    "sculptor/no-var-fallback": true,
  },
};

const lint = async (code) => {
  const result = await stylelint.lint({
    code,
    config,
    codeFilename: "test.scss",
  });
  return result.results[0].warnings;
};

describe("sculptor/no-var-fallback", () => {
  it("rejects var() with a fallback value", async () => {
    const warnings = await lint(".a { color: var(--gold-12, #3B352B); }");
    assert.equal(warnings.length, 1);
    assert.ok(warnings[0].text.includes("--gold-12"));
    assert.ok(warnings[0].text.includes("without a fallback"));
  });

  it("rejects var() with a pixel fallback", async () => {
    const warnings = await lint(
      ".a { border-radius: var(--radius-2, 4px); }",
    );
    assert.equal(warnings.length, 1);
    assert.ok(warnings[0].text.includes("--radius-2"));
  });

  it("rejects var() with a keyword fallback", async () => {
    const warnings = await lint(
      ".a { font-family: var(--Typography-Font-family-text, Inter); }",
    );
    assert.equal(warnings.length, 1);
  });

  it("accepts var() without a fallback", async () => {
    const warnings = await lint(".a { color: var(--gold-12); }");
    assert.equal(warnings.length, 0);
  });

  it("accepts nested var() without fallback", async () => {
    const warnings = await lint(
      ".a { background: var(--artifact-base-bg); }",
    );
    assert.equal(warnings.length, 0);
  });

  it("reports multiple fallbacks in one declaration", async () => {
    const warnings = await lint(
      ".a { border-radius: var(--radius-2, 4px) var(--radius-2, 4px) 0 0; }",
    );
    assert.equal(warnings.length, 2);
  });

  it("rejects rgba fallback", async () => {
    const warnings = await lint(
      ".a { box-shadow: 0 4px 16px var(--shadow-color, rgba(0, 0, 0, 10%)); }",
    );
    assert.equal(warnings.length, 1);
  });
});
