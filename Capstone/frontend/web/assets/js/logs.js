function bindAdminLogs() {
  if (!elements.logsList) return;
  setDefaultLogDateRange();

  [elements.logsStartDate, elements.logsEndDate].forEach((input) => {
    input?.addEventListener("change", () => {
      state.logDateRange = {
        start: elements.logsStartDate?.value || "",
        end: elements.logsEndDate?.value || "",
      };
      resetLogPage();
      void loadActivityLogs();
    });
  });
  elements.logsRefreshButton?.addEventListener("click", () => {
    void loadActivityLogs();
  });
}

function setDefaultLogDateRange() {
  if (state.logDateRange) {
    return;
  }
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - 29);
  state.logDateRange = {
    start: toDateInputValue(start),
    end: toDateInputValue(end),
  };
  syncLogDateInputs();
}

async function loadActivityLogs() {
  if (!elements.logsList) return;
  setDefaultLogDateRange();
  if (!isAdminSession()) {
    state.activityLogs = [];
    state.activityLogSummary = null;
    resetLogPage();
    renderActivityLogs();
    return;
  }

  state.isLoadingLogs = true;
  state.logError = "";
  renderActivityLogs();
  const params = buildLogQueryParams();

  try {
    const [logsResponse, summaryResponse] = await Promise.all([
      fetch(`/api/admin/logs?${params.toString()}`, {
        cache: "no-store",
        headers: adminAuthHeaders(),
      }),
      fetch(`/api/admin/logs/summary?${params.toString()}`, {
        cache: "no-store",
        headers: adminAuthHeaders(),
      }),
    ]);
    const logsPayload = await readJsonResponse(logsResponse);
    const summaryPayload = await readJsonResponse(summaryResponse);
    if (!logsResponse.ok) {
      throw new Error(formatApiError(logsPayload.detail, "Unable to load logs."));
    }
    if (!summaryResponse.ok) {
      throw new Error(
        formatApiError(summaryPayload.detail, "Unable to load log summary."),
      );
    }
    state.activityLogs = Array.isArray(logsPayload) ? logsPayload : [];
    state.activityLogSummary = summaryPayload || null;
    clampLogPage(filterActivityLogs(state.activityLogs).length);
  } catch (error) {
    state.activityLogs = [];
    state.activityLogSummary = null;
    state.logError = error.message || "Unable to load logs.";
  } finally {
    state.isLoadingLogs = false;
    renderActivityLogs();
  }
}

function buildLogQueryParams() {
  const params = new URLSearchParams({ limit: "100" });
  const range = state.logDateRange || {};
  if (range.start) params.set("start_date", range.start);
  if (range.end) params.set("end_date", range.end);
  return params;
}

function refreshActivityLogsIfVisible() {
  if (isAdminSession() && state.activeScreen === "logs") {
    void loadActivityLogs();
  }
}

function renderActivityLogs() {
  if (!elements.logsList) return;
  elements.logsList.innerHTML = "";
  if (elements.logsPagination) elements.logsPagination.innerHTML = "";
  elements.logsStatus.classList.remove("is-error");
  elements.logsRefreshButton?.classList.toggle("is-loading", state.isLoadingLogs);
  syncLogDateInputs();
  renderActivitySummary();

  if (!isAdminSession()) {
    elements.logsStatus.textContent = "";
    updateLogResultCount(0);
    return;
  }

  if (state.isLoadingLogs) {
    elements.logsStatus.textContent = "Loading activity...";
    elements.logsList.appendChild(createLogsSkeleton());
    updateLogResultCount(0);
    return;
  }

  if (state.logError) {
    elements.logsStatus.textContent = state.logError;
    elements.logsStatus.classList.add("is-error");
    updateLogResultCount(0);
    return;
  }

  const visibleItems = filterActivityLogs(state.activityLogs);
  clampLogPage(visibleItems.length);
  updateLogResultCount(visibleItems.length);

  if (!visibleItems.length) {
    elements.logsStatus.textContent =
      "No chatbot activity in the selected date range.";
    elements.logsList.appendChild(createLogsEmptyState());
    return;
  }

  elements.logsStatus.textContent = "";
  const pagination = getLogPagination(visibleItems.length);
  const pageItems = visibleItems.slice(pagination.startIndex, pagination.endIndex);
  elements.logsList.appendChild(createLogsTable(pageItems, pagination.startIndex));
  renderLogPagination(visibleItems.length);
}

function filterActivityLogs(items) {
  return items;
}

function renderActivitySummary() {
  const summary = state.activityLogSummary || {};
  setLogMetric(elements.logsTotalChat, summary.total_chat);
  setLogMetric(elements.logsTotalSessions, summary.total_sessions);
  setLogMetric(elements.logsAverageChat, summary.average_chat_per_session);
  setLogMetric(elements.logsFallbackError, summary.fallback_or_error);
}

function setLogMetric(element, value) {
  if (!element) return;
  element.textContent = formatLogNumber(value);
}

function createLogsTable(items, startIndex = 0) {
  const feed = document.createElement("div");
  feed.className = "logs-table";
  items.forEach((item, index) =>
    feed.appendChild(createLogRow(item, startIndex + index)),
  );
  return feed;
}

function createLogRow(item, index) {
  const row = document.createElement("article");
  row.className = "log-row";
  row.dataset.status = item.status || "success";
  row.style.setProperty("--row-index", String(Math.min(index, 8)));

  const toggle = document.createElement("button");
  toggle.className = "log-row-toggle logs-table-row";
  toggle.type = "button";
  toggle.setAttribute("aria-expanded", "false");

  const detail = document.createElement("div");
  detail.className = "log-detail";
  const questionLine = document.createElement("div");
  questionLine.className = "log-question-line";
  const statusDot = document.createElement("span");
  statusDot.className = "log-status-dot";
  statusDot.setAttribute("aria-hidden", "true");
  const question = document.createElement("span");
  question.className = "log-question";
  question.textContent = item.details?.question || item.summary || "Chat question";
  questionLine.append(statusDot, question);
  detail.append(questionLine);

  const timestamp = createLogTimestamp(item.created_at);

  const chevron = document.createElement("span");
  chevron.className = "material-symbols-outlined log-row-chevron";
  chevron.textContent = "expand_more";
  chevron.setAttribute("aria-hidden", "true");

  toggle.append(detail, timestamp, chevron);

  const panel = createLogConversationPanel(item);
  const panelId = `log-detail-${item.id || index}`;
  panel.id = panelId;
  panel.setAttribute("aria-hidden", "true");
  toggle.setAttribute("aria-controls", panelId);

  toggle.addEventListener("click", () => {
    const willOpen = !row.classList.contains("is-open");
    const table = row.closest(".logs-table");
    table?.querySelectorAll(".log-row.is-open").forEach((openRow) => {
      if (openRow !== row) setLogRowOpen(openRow, false);
    });
    setLogRowOpen(row, willOpen);
  });

  row.append(toggle, panel);
  return row;
}

function setLogRowOpen(row, isOpen) {
  row.classList.toggle("is-open", isOpen);
  row.querySelector(".log-row-toggle")?.setAttribute(
    "aria-expanded",
    String(isOpen),
  );
  row.querySelector(".log-row-panel")?.setAttribute("aria-hidden", String(!isOpen));
}

function createLogConversationPanel(item) {
  const panel = document.createElement("div");
  panel.className = "log-row-panel";
  const panelInner = document.createElement("div");
  panelInner.className = "log-row-panel-inner";

  const answer =
    item.status === "error"
      ? item.details?.error || "The response could not be generated."
      : item.details?.answer ||
        item.details?.answer_preview ||
        "Full answer is not available for this older log.";
  panelInner.appendChild(createLogMessage("Answer", answer, "assistant"));
  panel.appendChild(panelInner);
  window.requestAnimationFrame(() => setupLogReadMore(panel, answer));
  return panel;
}

function createLogMessage(label, text, type) {
  const message = document.createElement("section");
  message.className = `log-message is-${type}`;
  const heading = document.createElement("span");
  heading.className = "log-message-label";
  heading.textContent = label;
  let content;
  if (type === "assistant" && typeof formatMessage === "function") {
    const cleanText =
      typeof stripCitationMarkers === "function"
        ? stripCitationMarkers(text)
        : text;
    content = formatMessage(cleanText);
    content.classList.add("log-message-content");
  } else {
    content = document.createElement("p");
    content.className = "log-message-content";
    content.textContent = text;
  }
  message.append(heading, content);
  return message;
}

function setupLogReadMore(panel, answer) {
  const content = panel.querySelector(".log-message-content");
  const message = panel.querySelector(".log-message");
  if (!content || !message) return;
  const plainAnswer = String(answer || "");
  const isLongText = plainAnswer.length > 650 || plainAnswer.split(/\r?\n/).length > 8;
  const overflows = content.scrollHeight > 170;
  if (!isLongText && !overflows) return;

  message.classList.add("is-collapsible");
  content.classList.add("is-collapsed");

  const button = document.createElement("button");
  button.className = "log-read-more";
  button.type = "button";
  button.textContent = "Read more";
  button.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    const expanded = message.classList.toggle("is-answer-expanded");
    content.classList.toggle("is-collapsed", !expanded);
    button.textContent = expanded ? "Show less" : "Read more";
  });
  message.appendChild(button);
}

function createLogsSkeleton() {
  const skeleton = document.createElement("div");
  skeleton.className = "logs-skeleton";
  for (let index = 0; index < 3; index += 1) {
    const row = document.createElement("span");
    row.className = "logs-skeleton-row";
    skeleton.appendChild(row);
  }
  return skeleton;
}

function createLogsEmptyState() {
  const empty = document.createElement("div");
  empty.className = "logs-empty-state";
  const icon = document.createElement("span");
  icon.className = "material-symbols-outlined";
  icon.textContent = "forum";
  icon.setAttribute("aria-hidden", "true");
  const title = document.createElement("span");
  title.textContent = "No questions yet";
  empty.append(icon, title);
  return empty;
}

function createLogTimestamp(value) {
  const time = document.createElement("time");
  time.className = "log-row-time";
  time.dateTime = value || "";
  const parts = formatLogTimeParts(value);
  const date = document.createElement("span");
  date.textContent = parts.date;
  const clock = document.createElement("small");
  clock.textContent = parts.time;
  time.append(date, clock);
  return time;
}

function updateLogResultCount(count) {
  if (!elements.logsResultCount) return;
  const label = count === 1 ? "question" : "questions";
  elements.logsResultCount.textContent = `${formatLogNumber(count)} ${label}`;
}

function renderLogPagination(total) {
  if (!elements.logsPagination) return;
  elements.logsPagination.innerHTML = "";
  const pageSize = getLogPageSize();
  if (total <= pageSize) return;

  const pagination = getLogPagination(total);
  const nav = document.createElement("nav");
  nav.className = "logs-page-controls";
  nav.setAttribute("aria-label", "Logs pagination");

  const label = document.createElement("span");
  label.className = "logs-page-label";
  label.textContent = `${formatLogNumber(pagination.startIndex + 1)}-${formatLogNumber(
    pagination.endIndex,
  )} of ${formatLogNumber(total)} questions`;

  const previous = createLogPageButton("chevron_left", "Previous page", () => {
    state.logPage = Math.max(1, getLogPage() - 1);
    renderActivityLogs();
  });
  previous.disabled = pagination.page <= 1;

  const next = createLogPageButton("chevron_right", "Next page", () => {
    state.logPage = Math.min(pagination.totalPages, getLogPage() + 1);
    renderActivityLogs();
  });
  next.disabled = pagination.page >= pagination.totalPages;

  nav.append(label, previous, next);
  elements.logsPagination.appendChild(nav);
}

function createLogPageButton(iconName, label, onClick) {
  const button = document.createElement("button");
  button.className = "logs-page-button";
  button.type = "button";
  button.setAttribute("aria-label", label);
  button.title = label;
  const icon = document.createElement("span");
  icon.className = "material-symbols-outlined";
  icon.textContent = iconName;
  icon.setAttribute("aria-hidden", "true");
  button.appendChild(icon);
  button.addEventListener("click", onClick);
  return button;
}

function getLogPagination(total) {
  const pageSize = getLogPageSize();
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const page = Math.min(Math.max(getLogPage(), 1), totalPages);
  const startIndex = (page - 1) * pageSize;
  const endIndex = Math.min(startIndex + pageSize, total);
  return { page, pageSize, totalPages, startIndex, endIndex };
}

function getLogPage() {
  return Math.max(1, Number(state.logPage || 1));
}

function getLogPageSize() {
  return Math.max(1, Number(state.logPageSize || 10));
}

function resetLogPage() {
  state.logPage = 1;
}

function clampLogPage(total) {
  const totalPages = Math.max(1, Math.ceil(total / getLogPageSize()));
  state.logPage = Math.min(Math.max(getLogPage(), 1), totalPages);
}

function syncLogDateInputs() {
  if (!state.logDateRange) return;
  if (elements.logsStartDate && elements.logsStartDate.value !== state.logDateRange.start) {
    elements.logsStartDate.value = state.logDateRange.start || "";
  }
  if (elements.logsEndDate && elements.logsEndDate.value !== state.logDateRange.end) {
    elements.logsEndDate.value = state.logDateRange.end || "";
  }
}

function toDateInputValue(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatLogNumber(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return "0";
  return number.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function formatLogTimeParts(value) {
  const date = new Date(value || "");
  if (Number.isNaN(date.getTime())) return { date: "-", time: "" };
  return {
    date: date.toLocaleDateString("en-US", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    }),
    time: date.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
    }),
  };
}
