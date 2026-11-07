import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  test: { environment: "node", include: ["src/**/*.test.{ts,tsx}"] },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
      // Vitest runs server modules outside Next's compiler-enforced component boundary.
      "server-only": path.resolve(
        __dirname,
        "node_modules/next/dist/compiled/server-only/empty.js",
      ),
    },
  },
});
