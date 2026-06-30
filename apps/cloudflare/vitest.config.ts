import { defineConfig } from "vitest/config";

// render.js is a pure (string-only) module, so the default node environment is
// enough — no DOM needed.
export default defineConfig({
  test: {
    environment: "node",
    include: ["test/**/*.{test,spec}.{js,ts}"],
  },
});
