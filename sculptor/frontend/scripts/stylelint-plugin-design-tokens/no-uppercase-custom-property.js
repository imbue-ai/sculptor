import stylelint from "stylelint";

const {
  utils: { report, ruleMessages, validateOptions },
} = stylelint;

const ruleName = "sculptor/no-uppercase-custom-property";

const messages = ruleMessages(ruleName, {
  rejected: (varName) =>
    `Unexpected uppercase letter in custom property "${varName}". Use lowercase with hyphens (e.g., --my-variable).`,
});

/** Pattern matching var(--Name-With-Caps). */
const varPattern = /var\(\s*(--[\w-]+)/g;

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
      const { prop, value } = decl;

      // Check custom property declarations (--MyVar: value)
      if (prop.startsWith("--") && /[A-Z]/.test(prop)) {
        report({
          message: messages.rejected(prop),
          node: decl,
          result,
          ruleName,
        });
      }

      // Check var() references in values
      let match;
      varPattern.lastIndex = 0;
      while ((match = varPattern.exec(value)) !== null) {
        const varName = match[1];
        if (/[A-Z]/.test(varName)) {
          report({
            message: messages.rejected(varName),
            node: decl,
            result,
            ruleName,
          });
        }
      }
    });
  };
};

ruleFunction.ruleName = ruleName;
ruleFunction.messages = messages;

export default ruleFunction;
export { ruleName };
