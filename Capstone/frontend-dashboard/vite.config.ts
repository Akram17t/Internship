import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Served from the main app's existing /assets static mount
  // (backend/api/core.py mounts frontend/web/assets at /assets), so the
  // dashboard is embedded into the same origin/tab as the rest of the app,
  // not a separate route/port.
  base: "/assets/dashboard/",
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "../frontend/web/assets/dashboard",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // Fixed filenames (no content hash) so index.html can reference
        // them directly with plain <script>/<link> tags, matching the
        // vanilla app's existing asset-loading pattern.
        entryFileNames: "dashboard.js",
        chunkFileNames: "dashboard-[name].js",
        assetFileNames: (assetInfo) => {
          if (assetInfo.name?.endsWith(".css")) return "dashboard.css";
          return "dashboard-[name][extname]";
        },
      },
    },
  },
});
