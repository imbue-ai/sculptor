/**
 * Tests for the sculptor/no-hardcoded-values stylelint plugin.
 *
 * Uses Node's built-in test runner (node --test) because stylelint is ESM-only
 * and incompatible with the project's Jest/Babel setup.
 *
 * Run with: node --test scripts/stylelint-plugin-design-tokens/rule.test.mjs
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import stylelint from "stylelint";

const config = {
  plugins: ["./scripts/stylelint-plugin-design-tokens/index.js"],
  rules: {
    "sculptor/no-hardcoded-values": true,
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

describe("sculptor/no-hardcoded-values", () => {
  describe("font-size", () => {
    it("rejects hardcoded px font-size", async () => {
      const warnings = await lint(".a { font-size: 14px; }");
      assert.equal(warnings.length, 1);
      assert.ok(warnings[0].text.includes("fontSize"));
      assert.ok(warnings[0].text.includes("14px"));
    });

    it("accepts font-size using var()", async () => {
      const warnings = await lint(".a { font-size: var(--font-size-2); }");
      assert.equal(warnings.length, 0);
    });

    it("accepts font-size using calc()", async () => {
      const warnings = await lint(".a { font-size: calc(1em * 0.85); }");
      assert.equal(warnings.length, 0);
    });

    it("accepts relative font-size values like em", async () => {
      const warnings = await lint(".a { font-size: 0.85em; }");
      assert.equal(warnings.length, 0);
    });
  });

  describe("font-weight", () => {
    it("rejects hardcoded numeric font-weight", async () => {
      const warnings = await lint(".a { font-weight: 600; }");
      assert.equal(warnings.length, 1);
      assert.ok(warnings[0].text.includes("fontWeight"));
      assert.ok(warnings[0].text.includes("600"));
    });

    it("accepts font-weight using var()", async () => {
      const warnings = await lint(
        ".a { font-weight: var(--font-weight-semibold); }",
      );
      assert.equal(warnings.length, 0);
    });

    it("does not reject non-standard numeric weights like 200", async () => {
      const warnings = await lint(".a { font-weight: 200; }");
      assert.equal(warnings.length, 0);
    });

    it("accepts keyword font-weight", async () => {
      const warnings = await lint(".a { font-weight: bold; }");
      assert.equal(warnings.length, 0);
    });
  });

  describe("border-radius", () => {
    it("rejects hardcoded px border-radius", async () => {
      const warnings = await lint(".a { border-radius: 6px; }");
      assert.equal(warnings.length, 1);
      assert.ok(warnings[0].text.includes("borderRadius"));
      assert.ok(warnings[0].text.includes("6px"));
    });

    it("accepts border-radius using var()", async () => {
      const warnings = await lint(".a { border-radius: var(--radius-3); }");
      assert.equal(warnings.length, 0);
    });

    it("accepts percentage border-radius", async () => {
      const warnings = await lint(".a { border-radius: 50%; }");
      assert.equal(warnings.length, 0);
    });
  });

  describe("z-index", () => {
    it("rejects hardcoded z-index >= 10", async () => {
      const warnings = await lint(".a { z-index: 100; }");
      assert.equal(warnings.length, 1);
      assert.ok(warnings[0].text.includes("zIndex"));
      assert.ok(warnings[0].text.includes("100"));
    });

    it("accepts small z-index values (< 10)", async () => {
      const warnings = await lint(".a { z-index: 5; }");
      assert.equal(warnings.length, 0);
    });

    it("accepts z-index using var()", async () => {
      const warnings = await lint(".a { z-index: var(--z-modal); }");
      assert.equal(warnings.length, 0);
    });
  });

  describe("transition", () => {
    it("rejects hardcoded transition duration in ms", async () => {
      const warnings = await lint(".a { transition: opacity 200ms ease; }");
      assert.equal(warnings.length, 1);
      assert.ok(warnings[0].text.includes("transition"));
      assert.ok(warnings[0].text.includes("200ms"));
    });

    it("rejects hardcoded transition duration in seconds", async () => {
      const warnings = await lint(".a { transition: opacity 0.3s ease; }");
      assert.equal(warnings.length, 1);
      assert.ok(warnings[0].text.includes("transition"));
    });

    it("accepts transition using var()", async () => {
      const warnings = await lint(
        ".a { transition: opacity var(--duration-normal) ease; }",
      );
      assert.equal(warnings.length, 0);
    });

    it("rejects hardcoded transition-duration", async () => {
      const warnings = await lint(".a { transition-duration: 150ms; }");
      assert.equal(warnings.length, 1);
      assert.ok(warnings[0].text.includes("transition"));
    });
  });

  describe("spacing properties", () => {
    it("rejects hardcoded spacing in padding", async () => {
      const warnings = await lint(".a { padding: 16px; }");
      assert.equal(warnings.length, 1);
      assert.ok(warnings[0].text.includes("spacing"));
      assert.ok(warnings[0].text.includes("16px"));
    });

    it("rejects hardcoded spacing in margin", async () => {
      const warnings = await lint(".a { margin-top: 8px; }");
      assert.equal(warnings.length, 1);
      assert.ok(warnings[0].text.includes("spacing"));
    });

    it("rejects hardcoded spacing in gap", async () => {
      const warnings = await lint(".a { gap: 4px; }");
      assert.equal(warnings.length, 1);
      assert.ok(warnings[0].text.includes("spacing"));
    });

    it("accepts spacing using var()", async () => {
      const warnings = await lint(".a { padding: var(--space-3); }");
      assert.equal(warnings.length, 0);
    });

    it("accepts spacing using calc()", async () => {
      const warnings = await lint(
        ".a { margin: calc(-1 * var(--space-4)); }",
      );
      assert.equal(warnings.length, 0);
    });
  });

  describe("hex colors", () => {
    it("rejects hardcoded hex colors", async () => {
      const warnings = await lint(".a { color: #ff6b6b; }");
      assert.equal(warnings.length, 1);
      assert.ok(warnings[0].text.includes("#ff6b6b"));
    });

    it("rejects short hex colors", async () => {
      const warnings = await lint(".a { background: #fff; }");
      assert.equal(warnings.length, 1);
      assert.ok(warnings[0].text.includes("#fff"));
    });

    it("accepts color using var()", async () => {
      const warnings = await lint(".a { color: var(--gold-12); }");
      assert.equal(warnings.length, 0);
    });

    it("rejects hex colors in any property", async () => {
      const warnings = await lint(".a { border: 1px solid #ccc; }");
      assert.equal(warnings.length, 1);
      assert.ok(warnings[0].text.includes("#ccc"));
    });
  });

  describe("values using var() or calc() are always accepted", () => {
    it("accepts any property with var()", async () => {
      const warnings = await lint(
        ".a { font-size: var(--font-size-2); font-weight: var(--font-weight-bold); border-radius: var(--radius-3); }",
      );
      assert.equal(warnings.length, 0);
    });

    it("accepts any property with calc()", async () => {
      const warnings = await lint(
        ".a { font-size: calc(14px * var(--scaling)); }",
      );
      assert.equal(warnings.length, 0);
    });
  });

  describe("properties not checked by the rule", () => {
    it("does not flag width with px values", async () => {
      const warnings = await lint(".a { width: 100px; }");
      assert.equal(warnings.length, 0);
    });

    it("does not flag height with px values", async () => {
      const warnings = await lint(".a { height: 50px; }");
      assert.equal(warnings.length, 0);
    });

    it("does not flag display property", async () => {
      const warnings = await lint(".a { display: flex; }");
      assert.equal(warnings.length, 0);
    });
  });

  describe("multiple violations in one rule", () => {
    it("reports multiple spacing violations", async () => {
      const warnings = await lint(".a { padding: 8px 16px; }");
      assert.equal(warnings.length, 2);
    });

    it("reports multiple hex colors in one value", async () => {
      const warnings = await lint(
        ".a { background: linear-gradient(#ff0000, #00ff00); }",
      );
      assert.equal(warnings.length, 2);
    });
  });

  describe("suggestion messages", () => {
    it("suggests token for known font-weight value", async () => {
      const warnings = await lint(".a { font-weight: 400; }");
      assert.equal(warnings.length, 1);
      assert.ok(warnings[0].text.includes("--font-weight-"));
    });

    it("suggests token for known z-index value", async () => {
      const warnings = await lint(".a { z-index: 1000; }");
      assert.equal(warnings.length, 1);
      assert.ok(warnings[0].text.includes("--z-modal"));
    });
  });
});
