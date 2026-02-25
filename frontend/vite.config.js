import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    // i18n files are pure JS — no DOM required
    environment: "node",
  },
  resolve: {
    alias: {
      // Absolute imports from src/
      src: path.resolve(__dirname, "./src"),
    },
  },
  server: {
    // Dev proxy — routes /ws and /api to the local backend
    proxy: {
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
        changeOrigin: true,
      },
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
