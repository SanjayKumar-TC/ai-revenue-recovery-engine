import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/health": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/decide": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/audit": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
  },
});
