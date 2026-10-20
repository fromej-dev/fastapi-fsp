import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Forward /api to the FastAPI backend so the browser sees one origin (no CORS setup).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
