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
  elements.logsTabs?.querySelectorAll("[data-log-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      const nextTab = button.dataset.logTab === "sessions" ? "sessions" : "questions";
      if (state.activeLogsTab === nextTab) return;
      state.activeLogsTab = nextTab;
      resetLogPage();
      renderActivityLogs();
    });
  });
  elements.logsClearSessionButton?.addEventListener("click", () => {
    if (!state.selectedLogSessionId) return;
    state.selectedLogSessionId = "";
    resetLogPage();
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
    state.activityLogSessions = [];
    state.activityLogSummary = null;
    resetLogPage();
    renderActivityLogs();
    return;
  }

  state.isLoadingLogs = true;
  state.logError = "";
  renderActivityLogs();
  const params = buildLogQueryParams();
  const sessionsParams = buildLogQueryParams({ includeSession: false });

  try {
    const [logsResponse, summaryResponse, sessionsResponse] = await Promise.all([
      fetch(`/api/admin/logs?${params.toString()}`, {
        cache: "no-store",
        headers: adminAuthHeaders(),
      }),
      fetch(`/api/admin/logs/summary?${params.toString()}`, {
        cache: "no-store",
        headers: adminAuthHeaders(),
      }),
      fetch(`/api/admin/logs/sessions?${sessionsParams.toString()}`, {
        cache: "no-store",
        headers: adminAuthHeaders(),
      }),
    ]);
    const logsPayload = await readJsonResponse(logsResponse);
    const summaryPayload = await readJsonResponse(summaryResponse);
    const sessionsPayload = await readJsonResponse(sessionsResponse);
    if (!logsResponse.ok) {
      throw new Error(formatApiError(logsPayload.detail, "Unable to load logs."));
    }
    if (!summaryResponse.ok) {
      throw new Error(
        formatApiError(summaryPayload.detail, "Unable to load log summary."),
      );
    }
    if (!sessionsResponse.ok) {
      throw new Error(
        formatApiError(sessionsPayload.detail, "Unable to load log sessions."),
      );
    }
    state.activityLogs = Array.isArray(logsPayload) ? logsPayload : [];
    state.activityLogSessions = Array.isArray(sessionsPayload) ? sessionsPayload : [];
    state.activityLogSummary = summaryPayload || null;
    clampLogPage(filterActivityLogs(state.activityLogs).length);
  } catch (error) {
    state.activityLogs = [];
    state.activityLogSessions = [];
    state.activityLogSummary = null;
    state.logError = error.message || "Unable to load logs.";
  } finally {
    state.isLoadingLogs = false;
    renderActivityLogs();
  }
}

function buildLogQueryParams(options = {}) {
  const includeSession = options.includeSession !== false;
  const params = new URLSearchParams({ limit: "100" });
  const range = state.logDateRange || {};
  if (range.start) params.set("start_date", range.start);
  if (range.end) params.set("end_date", range.end);
  if (includeSession && state.selectedLogSessionId) {
    params.set("conversation_id", state.selectedLogSessionId);
  }
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
  syncLogTabs();
  renderActiveSessionFilter();
  renderActivitySummary();

  if (!isAdminSession()) {
    elements.logsStatus.textContent = "";
    updateLogResultCount(0);
    state.activityLogSessions = [];
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

  if (state.activeLogsTab === "sessions") {
    renderActivityLogSessions();
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

function renderActivityLogSessions() {
  if (!elements.logsList) return;
  if (elements.logsPagination) elements.logsPagination.innerHTML = "";
  const sessions = Array.isArray(state.activityLogSessions)
    ? state.activityLogSessions
    : [];
  updateLogResultCount(sessions.length, "session");
  if (!sessions.length) {
    elements.logsStatus.textContent =
      "No chatbot sessions in the selected date range.";
    elements.logsList.appendChild(createLogsEmptyState("forum", "No sessions yet"));
    return;
  }
  elements.logsStatus.textContent = "";
  elements.logsList.appendChild(createLogSessionsTable(sessions));
}

function renderActivitySummary() {
  const summary = state.activityLogSummary || {};
  setLogMetric(elements.logsTotalChat, summary.total_chat);
  setLogMetric(elements.logsTotalSessions, summary.total_sessions);
  setLogMetric(elements.logsAverageChat, summary.average_chat_per_session);
  setLogMetric(elements.logsRangeDays, getSelectedLogRangeDays());
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

function createLogSessionsTable(sessions) {
  const feed = document.createElement("div");
  feed.className = "logs-table logs-sessions-table";
  sessions.forEach((item, index) => {
    feed.appendChild(createLogSessionRow(item, index));
  });
  return feed;
}

function createLogSessionRow(item, index) {
  const row = document.createElement("article");
  row.className = "logs-session-row";
  row.style.setProperty("--row-index", String(Math.min(index, 8)));

  const openButton = document.createElement("button");
  openButton.className = "logs-session-open";
  openButton.type = "button";

  const detail = document.createElement("div");
  detail.className = "log-detail";
  const topLine = document.createElement("div");
  topLine.className = "log-question-line";
  const dot = document.createElement("span");
  dot.className = "material-symbols-outlined logs-session-marker";
  dot.textContent = "chat_bubble";
  dot.setAttribute("aria-hidden", "true");
  const title = document.createElement("span");
  title.className = "log-question";
  title.textContent = item.first_question || item.latest_question || "Chat session";
  topLine.append(dot, title);

  const meta = document.createElement("small");
  meta.className = "logs-session-meta";
  meta.textContent = `${formatLogNumber(item.question_count)} ${
    Number(item.question_count) === 1 ? "question" : "questions"
  } · Last activity ${formatLogTimeParts(item.last_at).date}`;
  detail.append(topLine, meta);

  const timestamp = createLogTimestamp(item.last_at);
  const action = document.createElement("span");
  action.className = "material-symbols-outlined log-row-chevron";
  action.textContent = "chevron_right";
  action.setAttribute("aria-hidden", "true");

  openButton.append(detail, timestamp);
  openButton.addEventListener("click", () => {
    state.selectedLogSessionId = item.conversation_id || "";
    state.activeLogsTab = "questions";
    resetLogPage();
    void loadActivityLogs();
  });
  row.append(openButton, createLogSessionDeleteButton(item), action);
  return row;
}

function createLogSessionDeleteButton(item) {
  const button = document.createElement("button");
  button.className = "log-delete-button logs-session-delete";
  button.type = "button";
  button.setAttribute("aria-label", "Delete session logs");
  button.title = "Delete session logs";
  const icon = document.createElement("span");
  icon.className = "material-symbols-outlined";
  icon.textContent = "delete";
  icon.setAttribute("aria-hidden", "true");
  button.appendChild(icon);
  button.addEventListener("click", async (event) => {
    event.preventDefault();
    event.stopPropagation();
    await deleteActivityLogSession(item.conversation_id, button);
  });
  return button;
}

function createLogRow(item, index) {
  const row = document.createElement("article");
  row.className = "log-row";
  row.dataset.status = "success";
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

  const deleteButton = createLogDeleteButton(item);

  toggle.append(detail, timestamp);

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

  row.append(toggle, deleteButton, panel);
  return row;
}

function createLogDeleteButton(item) {
  const button = document.createElement("button");
  button.className = "log-delete-button";
  button.type = "button";
  button.setAttribute("aria-label", "Delete log");
  button.title = "Delete log";
  const icon = document.createElement("span");
  icon.className = "material-symbols-outlined";
  icon.textContent = "delete";
  icon.setAttribute("aria-hidden", "true");
  button.appendChild(icon);
  button.addEventListener("click", async (event) => {
    event.preventDefault();
    event.stopPropagation();
    await deleteActivityLog(item.id, button);
  });
  return button;
}

async function deleteActivityLog(logId, button) {
  if (!logId || button?.disabled) return;
  button.disabled = true;
  try {
    const response = await fetch(`/api/admin/logs/${encodeURIComponent(logId)}`, {
      method: "DELETE",
      cache: "no-store",
      headers: adminAuthHeaders(),
    });
    const payload = await readJsonResponse(response);
    if (!response.ok) {
      throw new Error(formatApiError(payload.detail, "Unable to delete log."));
    }
    state.activityLogs = state.activityLogs.filter((item) => item.id !== logId);
    clampLogPage(filterActivityLogs(state.activityLogs).length);
    renderActivityLogs();
    void loadActivityLogs();
  } catch (error) {
    state.logError = error.message || "Unable to delete log.";
    renderActivityLogs();
  } finally {
    button.disabled = false;
  }
}

async function deleteActivityLogSession(conversationId, button) {
  if (!conversationId || button?.disabled) return;
  button.disabled = true;
  try {
    const response = await fetch(
      `/api/admin/logs/sessions/${encodeURIComponent(conversationId)}`,
      {
        method: "DELETE",
        cache: "no-store",
        headers: adminAuthHeaders(),
      },
    );
    const payload = await readJsonResponse(response);
    if (!response.ok) {
      throw new Error(formatApiError(payload.detail, "Unable to delete session."));
    }
    if (state.selectedLogSessionId === conversationId) {
      state.selectedLogSessionId = "";
    }
    state.activityLogSessions = state.activityLogSessions.filter(
      (item) => item.conversation_id !== conversationId,
    );
    state.activityLogs = state.activityLogs.filter(
      (item) => item.details?.conversation_id !== conversationId,
    );
    renderActivityLogs();
    void loadActivityLogs();
  } catch (error) {
    state.logError = error.message || "Unable to delete session.";
    renderActivityLogs();
  } finally {
    button.disabled = false;
  }
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
    item.details?.answer ||
    item.details?.answer_preview ||
    "No answer recorded.";
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

function createLogsEmptyState(iconName = "forum", titleText = "No questions yet") {
  const empty = document.createElement("div");
  empty.className = "logs-empty-state";
  const icon = document.createElement("span");
  icon.className = "material-symbols-outlined";
  icon.textContent = iconName;
  icon.setAttribute("aria-hidden", "true");
  const title = document.createElement("span");
  title.textContent = titleText;
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

function updateLogResultCount(count, singular = "question") {
  if (!elements.logsResultCount) return;
  const plural = singular === "session" ? "sessions" : "questions";
  const label = count === 1 ? singular : plural;
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

function syncLogTabs() {
  elements.logsTabs?.querySelectorAll("[data-log-tab]").forEach((button) => {
    const isActive = button.dataset.logTab === state.activeLogsTab;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-selected", String(isActive));
  });
}

function renderActiveSessionFilter() {
  if (!elements.logsSessionFilter) return;
  const sessionId = state.selectedLogSessionId || "";
  elements.logsSessionFilter.hidden = !sessionId;
  if (elements.logsActiveSessionLabel) {
    elements.logsActiveSessionLabel.textContent = sessionId
      ? "Filtered session"
      : "Session";
  }
}


function toDateInputValue(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getSelectedLogRangeDays() {
  const range = state.logDateRange || {};
  const start = new Date(range.start || "");
  const end = new Date(range.end || "");
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
    return 0;
  }
  const dayMs = 24 * 60 * 60 * 1000;
  return Math.max(1, Math.round((end - start) / dayMs) + 1);
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
