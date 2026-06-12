import stylelint from "stylelint";
import ruleFunction, { ruleName } from "./rule.js";
import noVarFallbackRule, {
  ruleName as noVarFallbackRuleName,
} from "./no-var-fallback.js";
import noUppercaseCustomPropertyRule, {
  ruleName as noUppercaseCustomPropertyRuleName,
} from "./no-uppercase-custom-property.js";

export default [
  stylelint.createPlugin(ruleName, ruleFunction),
  stylelint.createPlugin(noVarFallbackRuleName, noVarFallbackRule),
  stylelint.createPlugin(
    noUppercaseCustomPropertyRuleName,
    noUppercaseCustomPropertyRule,
  ),
];
