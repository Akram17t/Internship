// Bridges the vanilla-JS SPA's screen navigation to the embedded React
// analytics dashboard (built from frontend-dashboard/, output to
// /assets/dashboard/dashboard.js + dashboard.css). The React bundle exposes
// window.mountAnalyticsDashboard() (see frontend-dashboard/src/main.tsx) and
// mounts into #analyticsDashboardRoot exactly once.
function refreshAnalyticsIfVisible() {
  if (isAdminSession() && state.activeScreen === "analytics") {
    window.mountAnalyticsDashboard?.();
  }
}
