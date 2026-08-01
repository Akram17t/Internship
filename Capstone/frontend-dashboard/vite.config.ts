import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

// index.html is only the entry point for `npm run dev`; in production the
// bundle is embedded into frontend/web/index.html by <script>/<link> tags.
// Shipping the generated copy would expose a second, standalone
// /assets/dashboard/index.html page that renders the dashboard outside the
// host app's sign-in gate, so drop it from the build output.
function dropDevEntryHtml(): Plugin {
  return {
    name: "drop-dev-entry-html",
    enforce: "post",
    apply: "build",
    generateBundle(_options, bundle) {
      delete bundle["index.html"];
    },
  };
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), dropDevEntryHtml()],
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
