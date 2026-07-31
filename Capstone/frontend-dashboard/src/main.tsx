import { StrictMode } from "react";
import { createRoot, type Root } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";

// Embedded mode: this bundle is loaded inside frontend/web/index.html (the
// main vanilla-JS app), not as a standalone page. It mounts into
// #analyticsDashboardRoot only when that element exists, and only once,
// so app.js can safely call window.mountAnalyticsDashboard() every time the
// admin navigates to the Analytics screen without double-mounting React.
let mountedRoot: Root | null = null;

function mount() {
  const container = document.getElementById("analyticsDashboardRoot");
  if (!container || mountedRoot) return;
  mountedRoot = createRoot(container);
  mountedRoot.render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

// Support both: a standalone dev page with a #root element (npm run dev),
// and embedding inside the main app which calls this explicitly on nav.
const standaloneRoot = document.getElementById("root");
if (standaloneRoot) {
  createRoot(standaloneRoot).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
} else {
  (window as unknown as { mountAnalyticsDashboard?: () => void }).mountAnalyticsDashboard = mount;
  // If the mount point is already present at script-load time, mount
  // immediately; otherwise app.js will call mountAnalyticsDashboard() when
  // the Analytics screen becomes visible.
  mount();
}
