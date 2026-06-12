import stylelint from "stylelint";
import { buildTokenMappings } from "./token-parser.js";

const {
  createPlugin,
  utils: { report, ruleMessages, validateOptions },
} = stylelint;

const ruleName = "sculptor/no-hardcoded-values";

const messages = ruleMessages(ruleName, {
  rejected: (value, category, suggestion) =>
    `Hardcoded ${category} value "${value}". Use var(${suggestion}) instead.`,
  rejectedColor: (value) =>
    `Hardcoded color "${value}". Use a Radix color variable (e.g., --gray-*, --accent-*) or a semantic token from tokens.css.`,
});

/** Check whether a value string contains var( or calc(, meaning it already uses tokens. */
const usesTokenOrCalc = (value) =>
  value.includes("var(") || value.includes("calc(");

const getSuggestion = (value, category, mappings) => {
  const normalized = value.toLowerCase().trim();
  const categoryMap = mappings[category];
  if (!categoryMap) {
    return null;
  }
  for (const [key, token] of Object.entries(categoryMap)) {
    if (key.toLowerCase() === normalized || key === value) {
      return token;
    }
  }
  return null;
};

const spacingProps = new Set([
  "margin",
  "margin-top",
  "margin-right",
  "margin-bottom",
  "margin-left",
  "margin-block",
  "margin-block-start",
  "margin-block-end",
  "margin-inline",
  "margin-inline-start",
  "margin-inline-end",
  "padding",
  "padding-top",
  "padding-right",
  "padding-bottom",
  "padding-left",
  "padding-block",
  "padding-block-start",
  "padding-block-end",
  "padding-inline",
  "padding-inline-start",
  "padding-inline-end",
  "gap",
  "row-gap",
  "column-gap",
  "top",
  "right",
  "bottom",
  "left",
]);

/** @type {import('stylelint').Rule} */
const ruleFunction = (primary) => {
  return (root, result) => {
    const validOptions = validateOptions(result, ruleName, {
      actual: primary,
      possible: [true],
    });
    if (!validOptions) {
      return;
    }

    const mappings = buildTokenMappings();
    const knownSpacingPx = new Set(
      Object.keys(mappings.spacing).map((k) => parseInt(k)),
    );

    root.walkDecls((decl) => {
      const { prop, value } = decl;

      if (usesTokenOrCalc(value)) {
        return;
      }

      // font-size: Npx
      if (prop === "font-size") {
        const match = value.match(/^(\d+)px$/);
        if (match) {
          const raw = `${match[1]}px`;
          const suggestion =
            getSuggestion(raw, "fontSize", mappings) ??
            "Check Radix tokens or tokens.css for appropriate fontSize token";
          report({
            message: messages.rejected(raw, "fontSize", suggestion),
            node: decl,
            result,
            ruleName,
          });
        }
        return;
      }

      // font-weight: 300-700
      if (prop === "font-weight") {
        const match = value.match(/^(300|400|500|600|700)$/);
        if (match) {
          const raw = match[1];
          const suggestion =
            getSuggestion(raw, "fontWeight", mappings) ??
            "Check Radix tokens or tokens.css for appropriate fontWeight token";
          report({
            message: messages.rejected(raw, "fontWeight", suggestion),
            node: decl,
            result,
            ruleName,
          });
        }
        return;
      }

      // border-radius: Npx
      if (prop === "border-radius") {
        const match = value.match(/(\d+)px/);
        if (match) {
          const raw = `${match[1]}px`;
          const suggestion =
            getSuggestion(raw, "borderRadius", mappings) ??
            "Check Radix tokens or tokens.css for appropriate borderRadius token";
          report({
            message: messages.rejected(raw, "borderRadius", suggestion),
            node: decl,
            result,
            ruleName,
          });
        }
        return;
      }

      // z-index: N (>= 10)
      if (prop === "z-index") {
        const match = value.match(/^(\d+)$/);
        if (match && parseInt(match[1]) >= 10) {
          const raw = match[1];
          const suggestion =
            getSuggestion(raw, "zIndex", mappings) ??
            "Check tokens.css for appropriate zIndex token";
          report({
            message: messages.rejected(raw, "zIndex", suggestion),
            node: decl,
            result,
            ruleName,
          });
        }
        return;
      }

      // transition / transition-duration: durations
      if (prop === "transition" || prop === "transition-duration") {
        const match = value.match(/(\d+(?:\.\d+)?)(ms|s)(?![a-z])/i);
        if (match) {
          const raw = `${match[1]}${match[2]}`;
          const suggestion =
            getSuggestion(raw, "transition", mappings) ??
            "Check tokens.css for appropriate duration token";
          report({
            message: messages.rejected(raw, "transition", suggestion),
            node: decl,
            result,
            ruleName,
          });
        }
        return;
      }

      // spacing properties: known px values
      if (spacingProps.has(prop)) {
        const spacingPxValues = [...knownSpacingPx];
        if (spacingPxValues.length > 0) {
          const pattern = new RegExp(
            `\\b(${spacingPxValues.join("|")})px\\b`,
            "g",
          );
          let spacingMatch;
          while ((spacingMatch = pattern.exec(value)) !== null) {
            const raw = `${spacingMatch[1]}px`;
            const suggestion =
              getSuggestion(raw, "spacing", mappings) ??
              "Check Radix tokens for appropriate spacing token";
            report({
              message: messages.rejected(raw, "spacing", suggestion),
              node: decl,
              result,
              ruleName,
            });
          }
        }
        return;
      }

      // hex colors in any declaration
      const hexPattern = /#[0-9a-fA-F]{3,8}(?![0-9a-fA-F])/g;
      let hexMatch;
      while ((hexMatch = hexPattern.exec(value)) !== null) {
        report({
          message: messages.rejectedColor(hexMatch[0]),
          node: decl,
          result,
          ruleName,
        });
      }
    });
  };
};

ruleFunction.ruleName = ruleName;
ruleFunction.messages = messages;

export default ruleFunction;
export { ruleName };
