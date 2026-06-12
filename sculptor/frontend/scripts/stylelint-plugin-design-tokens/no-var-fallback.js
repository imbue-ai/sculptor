import stylelint from "stylelint";

const {
  utils: { report, ruleMessages, validateOptions },
} = stylelint;

const ruleName = "sculptor/no-var-fallback";

const messages = ruleMessages(ruleName, {
  rejected: (varName) =>
    `Unexpected fallback value in var(${varName}). Use var(${varName}) without a fallback.`,
});

/** Pattern matching var(--name, fallback) including nested var(). */
const varFallbackPattern = /var\((\s*--[\w-]+)\s*,/g;

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

    root.walkDecls((decl) => {
      const { value } = decl;

      let match;
      varFallbackPattern.lastIndex = 0;
      while ((match = varFallbackPattern.exec(value)) !== null) {
        const varName = match[1].trim();
        report({
          message: messages.rejected(varName),
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
