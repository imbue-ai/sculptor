/**
 * Tests for the sculptor/no-uppercase-custom-property stylelint rule.
 *
 * Run with: node --test scripts/stylelint-plugin-design-tokens/no-uppercase-custom-property.test.mjs
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import stylelint from "stylelint";

const config = {
  plugins: ["./scripts/stylelint-plugin-design-tokens/index.js"],
  rules: {
    "sculptor/no-uppercase-custom-property": true,
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

describe("sculptor/no-uppercase-custom-property", () => {
  it("rejects var() with uppercase custom property name", async () => {
    const warnings = await lint(
      ".a { font-size: var(--Typography-Font-size-1); }",
    );
    assert.equal(warnings.length, 1);
    assert.ok(warnings[0].text.includes("--Typography-Font-size-1"));
    assert.ok(warnings[0].text.includes("lowercase"));
  });

  it("rejects Figma-style color variable names", async () => {
    const warnings = await lint(
      ".a { color: var(--Colors-Neutral-Neutral-12); }",
    );
    assert.equal(warnings.length, 1);
    assert.ok(warnings[0].text.includes("--Colors-Neutral-Neutral-12"));
  });

  it("rejects uppercase custom property declaration", async () => {
    const warnings = await lint(":root { --My-Custom-Var: red; }");
    assert.equal(warnings.length, 1);
    assert.ok(warnings[0].text.includes("--My-Custom-Var"));
  });

  it("accepts lowercase custom property in var()", async () => {
    const warnings = await lint(".a { font-size: var(--font-size-1); }");
    assert.equal(warnings.length, 0);
  });

  it("accepts lowercase custom property declaration", async () => {
    const warnings = await lint(":root { --my-custom-var: red; }");
    assert.equal(warnings.length, 0);
  });

  it("accepts lowercase with numbers", async () => {
    const warnings = await lint(".a { color: var(--gold-12); }");
    assert.equal(warnings.length, 0);
  });

  it("reports multiple uppercase vars in one declaration", async () => {
    const warnings = await lint(
      ".a { border-radius: var(--Radius-2-max) var(--Radius-3-max); }",
    );
    assert.equal(warnings.length, 2);
  });

  it("accepts camelCase-free hyphenated names", async () => {
    const warnings = await lint(
      ".a { transition: opacity var(--duration-normal) ease; }",
    );
    assert.equal(warnings.length, 0);
  });
});
