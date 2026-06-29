import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In dev, proxy the API so the SPA and FastAPI share an origin.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/v1": { target: "http://localhost:8080", changeOrigin: true },
    },
  },
});
