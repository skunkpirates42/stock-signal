<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# Response parsing

Flask JSON enters the app through a `Read<T>` reader from `src/lib/parse.ts`, applied where the body is fetched. Lint rejects casting or annotating `response.json()`.

Hand-written readers are deliberate while response shapes stay flat. Switch to Zod schemas, deriving types with `z.infer`, as a single migration when either trigger arrives:

- nested demo records (`Availability<T>`, `Result`, `NormalizedRun`) need full validation instead of `readContractRecord`'s `record_type` check
- `parse.ts` needs a new primitive (unions, refinements, transforms)

The migration ends with `parse.ts` deleted and `@/lib/parse` banned through `no-restricted-imports` in `eslint.config.mjs`.
