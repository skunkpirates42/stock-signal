import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import requireResponseReader from "./eslint-rules/require-response-reader.mjs";

const unparsedResponseBody = [
  {
    selector:
      "TSAsExpression > CallExpression[callee.property.name='json'], TSAsExpression > AwaitExpression > CallExpression[callee.property.name='json']",
    message: "Parse response bodies with a reader from lib/ instead of casting them.",
  },
  {
    selector:
      "VariableDeclarator[id.typeAnnotation] > AwaitExpression > CallExpression[callee.property.name='json']",
    message: "Parse response bodies with a reader from lib/ instead of annotating them.",
  },
];

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["**/*.test.{ts,tsx}"],
    plugins: { responses: { rules: { "require-reader": requireResponseReader } } },
    rules: { "responses/require-reader": "error" },
  },
  {
    files: ["src/components/**/*.{ts,tsx}", "src/app/**/*.{ts,tsx}"],
    ignores: ["**/*.test.ts"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "MemberExpression[property.name=/^(toFixed|toLocaleString)$/]",
          message: "Format numbers through a helper in lib/format.ts.",
        },
        {
          selector: "MemberExpression[object.name='Intl']",
          message: "Format numbers and dates through a helper in lib/format.ts.",
        },
        ...unparsedResponseBody,
      ],
    },
  },
  {
    files: ["src/lib/**/*.ts", "src/hooks/**/*.ts"],
    ignores: ["**/*.test.ts"],
    rules: { "no-restricted-syntax": ["error", ...unparsedResponseBody] },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "playwright-report/**",
    "test-results/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
