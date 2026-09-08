import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// WHY a dev proxy instead of calling http://localhost:8000 directly:
// The browser enforces SAME-ORIGIN policy. Even though our API has CORS
// enabled, proxying keeps the frontend code origin-agnostic — it just
// calls "/api/..." relative paths. Vite forwards them to the backend.
// In production (nginx) the same trick works: one origin, route to apps.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/chat": "http://localhost:8000",
      "/ingest": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});