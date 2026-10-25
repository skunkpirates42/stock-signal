# web

The stock-signal dashboard: Next.js 16, React 19 and TypeScript. It reads from the Flask
API in `../dashboard` (`FLASK_API_URL`, default `http://127.0.0.1:8000`).

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
