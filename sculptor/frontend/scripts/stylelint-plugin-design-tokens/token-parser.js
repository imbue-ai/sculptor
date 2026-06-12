import * as fs from "fs";
import * as path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(__dirname, "../..");

/** Module-level cache so tokens are parsed once per stylelint run. */
let cachedMappings = null;

/**
 * Parse Radix base.css to extract token-to-value mappings.
 * Handles patterns like: --space-1: calc(4px * var(--scaling));
 */
const parseRadixTokens = (radixBasePath) => {
  const mappings = {
    spacing: {},
    fontSize: {},
    borderRadius: {},
    fontWeight: {},
  };

  if (!fs.existsSync(radixBasePath)) {
    return mappings;
  }

  const content = fs.readFileSync(radixBasePath, "utf-8");

  for (const match of content.matchAll(/--space-(\d+):\s*calc\((\d+)px/g)) {
    mappings.spacing[`${match[2]}px`] = `--space-${match[1]}`;
  }

  for (const match of content.matchAll(
    /--font-size-(\d+):\s*calc\((\d+)px/g,
  )) {
    mappings.fontSize[`${match[2]}px`] = `--font-size-${match[1]}`;
  }

  for (const match of content.matchAll(/--radius-(\d+):\s*calc\((\d+)px/g)) {
    mappings.borderRadius[`${match[2]}px`] = `--radius-${match[1]}`;
  }
  mappings.borderRadius["9999px"] = "--radius-full";

  for (const match of content.matchAll(/--font-weight-(\w+):\s*(\d+)/g)) {
    mappings.fontWeight[match[2]] = `--font-weight-${match[1]}`;
  }

  return mappings;
};

/**
 * Parse our custom tokens.css to extract token-to-value mappings.
 * Handles patterns like: --duration-fast: 100ms;
 */
const parseCustomTokens = (tokensPath) => {
  const mappings = {
    transition: {},
    zIndex: {},
    fontSize: {},
    fontWeight: {},
  };

  if (!fs.existsSync(tokensPath)) {
    return mappings;
  }

  const content = fs.readFileSync(tokensPath, "utf-8");

  for (const match of content.matchAll(/--(duration-\w+):\s*(\d+)ms/g)) {
    const ms = match[2];
    const seconds = (parseInt(ms) / 1000).toString();
    mappings.transition[`${ms}ms`] = `--${match[1]}`;
    mappings.transition[`${seconds}s`] = `--${match[1]}`;
  }

  for (const match of content.matchAll(/--(z-\w+):\s*(\d+)/g)) {
    mappings.zIndex[match[2]] = `--${match[1]}`;
  }

  for (const match of content.matchAll(
    /--(font-size-[\w-]+):\s*calc\((\d+)px/g,
  )) {
    mappings.fontSize[`${match[2]}px`] = `--${match[1]}`;
  }

  for (const match of content.matchAll(/--(font-weight-\w+):\s*(\d+)/g)) {
    mappings.fontWeight[match[2]] = `--${match[1]}`;
  }

  return mappings;
};

/**
 * Build and cache complete token mappings by parsing source files.
 */
export const buildTokenMappings = () => {
  if (cachedMappings) {
    return cachedMappings;
  }

  const radixBasePath = path.join(
    frontendDir,
    "node_modules/@radix-ui/themes/tokens/base.css",
  );
  const tokensPath = path.join(frontendDir, "src/styles/tokens.css");

  const radixMappings = parseRadixTokens(radixBasePath);
  const customMappings = parseCustomTokens(tokensPath);

  const merged = { ...radixMappings };
  for (const [category, values] of Object.entries(customMappings)) {
    merged[category] = { ...merged[category], ...values };
  }

  cachedMappings = merged;
  return merged;
};
