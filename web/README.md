# web

The stock-signal dashboard: Next.js 16, React 19 and TypeScript. It reads from the Flask
API in `../dashboard` (`FLASK_API_URL`, default `http://127.0.0.1:8000`).

Use the Node version in the root [`.nvmrc`](../.nvmrc), which CI also reads.
Run `nvm install` and `nvm use` from the repository root before working here.
The package requires Node 26 or newer; `.npmrc` enables `engine-strict`, so pnpm
fails installation on an incompatible Node version. Use the pnpm version declared
in `package.json`.

```bash
pnpm install
pnpm dev     # http://localhost:3000
pnpm test    # vitest
pnpm lint
pnpm build
```

Logic lives in `src/lib/` with tests alongside, components in `src/components/`, and
design tokens in `src/styles/tokens.css`. `/system` shows every shared component in each
of its states. See the [main README](../README.md) for the pages, the design-system checks
and how to run the API with sample data.

## Browser smoke test

With the root `.venv` dependencies installed as described in the main README:

```bash
pnpm exec playwright install chromium
pnpm build
pnpm test:smoke
```

Playwright starts the production app on port 13000 and a Flask API on port 18000.
Both ports must be free. The API replays the bundled synthetic fixture into temporary
storage; it does not use your dashboard database or start a trading engine.
The six top-level pages must return 200, display their page title, and produce no
browser errors or error boundary. Failed tests retain traces in `test-results/`;
CI uploads them as `playwright-traces`.
