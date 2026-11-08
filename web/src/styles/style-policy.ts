import { generate, lexer, parse, walk, type CssNode, type Declaration } from "css-tree";

type Violation = { property: string; value: string; rule: string; line: number | undefined };

function valueNodes(declaration: Declaration) {
  if (declaration.value.type !== "Value") return [];
  return declaration.value.children.toArray();
}

function isToken(node: CssNode, tokens: Set<string>) {
  if (node.type !== "Function" || node.name.toLowerCase() !== "var") return false;
  const argumentsList = node.children.toArray();
  return (
    argumentsList.length === 1 &&
    argumentsList[0].type === "Identifier" &&
    tokens.has(argumentsList[0].name)
  );
}

function hasLiteralColor(declaration: Declaration) {
  let found = false;
  walk(declaration.value, function (node) {
    if (node.type === "Url" || node.type === "String") return this.skip;
    if (node.type === "Hash") found = true;
    if (node.type === "Function" && node.name.toLowerCase() === "var") return;
    if (
      node.type === "Function" &&
      ["rgb", "rgba", "hsl", "hsla", "hwb", "lab", "lch", "oklab", "oklch", "color"].includes(
        node.name.toLowerCase(),
      )
    )
      found = true;
    if (
      node.type === "Identifier" &&
      !["transparent", "currentcolor"].includes(node.name.toLowerCase()) &&
      lexer.matchType("color", node).matched
    )
      found = true;
  });
  return found;
}

function isSpacingValue(node: CssNode, tokens: Set<string>): boolean {
  if (isToken(node, tokens)) return true;
  if (node.type === "Number") return Number(node.value) === 0;
  if (node.type === "Identifier") return node.name === "auto";
  if (node.type !== "Function" || node.name.toLowerCase() !== "calc") return false;
  let hasSpacingToken = false;
  let isValid = true;
  walk(node, function (child) {
    if (child === node) return;
    if (isToken(child, tokens)) {
      hasSpacingToken = true;
      return this.skip;
    }
    if (child.type === "Number" || child.type === "Operator" || child.type === "Parentheses")
      return;
    if (child.type === "Function" && child.name.toLowerCase() === "calc") return;
    isValid = false;
    return this.skip;
  });
  return hasSpacingToken && isValid;
}

export function definedTokens(source: string, prefix: string) {
  const tokens = new Set<string>();
  walk(parse(source), {
    visit: "Declaration",
    enter(node) {
      if (node.property.startsWith(prefix)) tokens.add(node.property);
    },
  });
  return tokens;
}

export function stylesheetViolations(source: string, tokenSource: string): Violation[] {
  const typeTokens = definedTokens(tokenSource, "--text-");
  const radiusTokens = definedTokens(tokenSource, "--radius");
  const spacingTokens = definedTokens(tokenSource, "--space");
  const violations: Violation[] = [];
  const stylesheet = parse(source, {
    positions: true,
    parseCustomProperty: true,
    onParseError(error) {
      throw error;
    },
  });
  walk(stylesheet, {
    visit: "Declaration",
    enter(declaration) {
      const property = declaration.property.toLowerCase();
      const nodes = valueNodes(declaration);
      const value = generate(declaration.value);
      const fail = (rule: string) =>
        violations.push({ property, value, rule, line: declaration.loc?.start.line });
      if (hasLiteralColor(declaration)) fail("Colors must come from tokens.css");
      if (property === "font-size" && !(nodes.length === 1 && isToken(nodes[0], typeTokens))) {
        fail("Font sizes must use a defined type-scale token");
      }
      if (property === "font" && value !== "inherit") fail("Font shorthand must inherit");
      const isSpacingProperty = ["padding", "margin", "gap", "row-gap", "column-gap"].some(
        (prefix) => property === prefix || property.startsWith(`${prefix}-`),
      );
      const isScreenReaderMargin =
        property === "margin" &&
        value === "-1px" &&
        this.rule?.prelude?.type === "SelectorList" &&
        generate(this.rule.prelude) === ".sr-only";
      if (
        isSpacingProperty &&
        !isScreenReaderMargin &&
        !nodes.every((node) => isSpacingValue(node, spacingTokens))
      ) {
        fail("Spacing must use defined spacing tokens, zero or auto");
      }
      if (
        (property === "border-radius" || property.endsWith("-radius")) &&
        !nodes.every(
          (node) =>
            isToken(node, radiusTokens) ||
            (node.type === "Number" && Number(node.value) === 0) ||
            (node.type === "Operator" && node.value === "/"),
        )
      ) {
        fail("Corner radii must use defined radius tokens or zero");
      }
    },
  });
  return violations;
}
