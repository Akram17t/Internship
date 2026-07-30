function bindAdminLogs() {
  if (!elements.logsList) return;
  setDefaultLogDateRange();

  elements.logsNameSearch?.addEventListener("input", () => {
    state.logNameQuery = (elements.logsNameSearch.value || "").trim().toLowerCase();
    resetLogPage();
    renderActivityLogs();
  });

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

  [
    elements.logsTotalChatCard,
    elements.logsTotalSessionsCard,
    elements.logsFeedbackSummaryCard,
  ].forEach((button) => {
    button?.addEventListener("click", () => {
      const nextView = normalizeLogsView(button.dataset.logView);
      if (state.activeLogsView === nextView && !state.selectedLogSessionId) return;
      state.activeLogsView = nextView;
      state.selectedLogSessionId = "";
      resetLogPage();
      void loadActivityLogs();
    });
  });

  elements.logsRefreshButton?.addEventListener("click", () => {
    void loadActivityLogs();
  });
  elements.logsClearSessionButton?.addEventListener("click", () => {
    if (!state.selectedLogSessionId) return;
    state.selectedLogSessionId = "";
    state.activeLogsView = "questions";
    resetLogPage();
    void loadActivityLogs();
  });
}

function setDefaultLogDateRange() {
  if (state.logDateRange) return;
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

  const logsParams = buildLogQueryParams({
    feedbackOnly: state.activeLogsView === "feedback",
    includeSession: state.activeLogsView === "questions",
  });
  const summaryParams = buildLogQueryParams({
    includeSession: state.activeLogsView === "questions",
  });
  const sessionsParams = buildLogQueryParams({ includeSession: false });

  try {
    const [logsResponse, summaryResponse, sessionsResponse] = await Promise.all([
      fetch(`/api/admin/logs?${logsParams.toString()}`, {
        cache: "no-store",
        headers: adminAuthHeaders(),
      }),
      fetch(`/api/admin/logs/summary?${summaryParams.toString()}`, {
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
    clampLogPage(getActiveLogItemCount());
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
  const params = new URLSearchParams({ limit: "1000" });
  if (LOCAL_TIME_ZONE) params.set("tz", LOCAL_TIME_ZONE);
  const range = state.logDateRange || {};
  if (range.start) params.set("start_date", range.start);
  if (range.end) params.set("end_date", range.end);
  if (options.includeSession === true && state.selectedLogSessionId) {
    params.set("conversation_id", state.selectedLogSessionId);
  }
  if (options.feedbackOnly === true) params.set("feedback", "negative");
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
  syncLogViewControls();
  renderActiveSessionFilter();
  renderActivitySummary();

  if (!isAdminSession()) {
    elements.logsStatus.textContent = "";
    state.activityLogSessions = [];
    return;
  }

  if (state.isLoadingLogs) {
    elements.logsStatus.textContent = "Loading activity...";
    elements.logsList.appendChild(createLogsSkeleton());
    return;
  }

  if (state.logError) {
    elements.logsStatus.textContent = state.logError;
    elements.logsStatus.classList.add("is-error");
    return;
  }

  if (state.activeLogsView === "sessions") {
    renderActivityLogSessions();
    return;
  }

  if (state.activeLogsView === "feedback") {
    renderActivityLogFeedback();
    return;
  }

  renderActivityLogQuestions();
}

function renderActivityLogQuestions() {
  const visibleItems = getVisibleQuestionLogs();
  clampLogPage(visibleItems.length);
  if (!visibleItems.length) {
    elements.logsStatus.textContent = state.logNameQuery
      ? "No questions match that name."
      : "No chatbot activity in the selected date range.";
    elements.logsList.appendChild(createLogsEmptyState("forum", "No questions yet"));
    return;
  }

  elements.logsStatus.textContent = "";
  const pagination = getLogPagination(visibleItems.length);
  const pageItems = visibleItems.slice(pagination.startIndex, pagination.endIndex);
  elements.logsList.appendChild(createLogsTable(pageItems, pagination.startIndex));
  renderLogPagination(visibleItems.length, "questions");
}

function renderActivityLogSessions() {
  const sessions = getVisibleSessionLogs();
  if (!sessions.length) {
    elements.logsStatus.textContent = state.logNameQuery
      ? "No chatbot sessions match that name."
      : "No chatbot sessions in the selected date range.";
    elements.logsList.appendChild(createLogsEmptyState("forum", "No sessions yet"));
    return;
  }

  elements.logsStatus.textContent = "";
  elements.logsList.appendChild(createLogSessionsTable(sessions));
}

function renderActivityLogFeedback() {
  const feedbackItems = getVisibleFeedbackLogs();
  clampLogPage(feedbackItems.length);
  if (!feedbackItems.length) {
    elements.logsStatus.textContent = state.logNameQuery
      ? "No feedback matches that name."
      : "No feedback in the selected date range.";
    elements.logsList.appendChild(createLogsEmptyState("thumb_down", "No feedback yet"));
    return;
  }

  elements.logsStatus.textContent = "";
  const pagination = getLogPagination(feedbackItems.length);
  const pageItems = feedbackItems.slice(pagination.startIndex, pagination.endIndex);
  elements.logsList.appendChild(createFeedbackStream(pageItems, pagination.startIndex));
  renderLogPagination(feedbackItems.length, "feedback");
}

function logDisplayName(name, email) {
  return (name || "").trim() || (email || "").trim() || "Unknown user";
}

function matchesLogNameQuery(name, email) {
  const query = (state.logNameQuery || "").trim();
  if (!query) return true;
  const haystack = `${name || ""} ${email || ""}`.toLowerCase();
  return haystack.includes(query);
}

function getVisibleQuestionLogs() {
  const items = Array.isArray(state.activityLogs) ? state.activityLogs : [];
  return items.filter((item) =>
    matchesLogNameQuery(item.details?.user_name, item.details?.user_email),
  );
}

function getVisibleFeedbackLogs() {
  return getVisibleQuestionLogs().filter((item) => hasNegativeFeedback(item));
}

function getVisibleSessionLogs() {
  const sessions = Array.isArray(state.activityLogSessions)
    ? state.activityLogSessions
    : [];
  return sessions.filter((item) =>
    matchesLogNameQuery(item.user_name, item.user_email),
  );
}

function getActiveLogItemCount() {
  if (state.activeLogsView === "sessions") {
    return getVisibleSessionLogs().length;
  }
  if (state.activeLogsView === "feedback") {
    return getVisibleFeedbackLogs().length;
  }
  return getVisibleQuestionLogs().length;
}

function renderActivitySummary() {
  const summary = state.activityLogSummary || {};
  setLogMetric(elements.logsTotalChat, summary.total_chat);
  setLogMetric(elements.logsTotalSessions, summary.total_sessions);
  setLogMetric(elements.logsNegativeFeedback, summary.negative_feedback);
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

function createFeedbackStream(items, startIndex = 0) {
  const feed = document.createElement("div");
  feed.className = "logs-table logs-feedback-stream";
  items.forEach((item, index) => {
    feed.appendChild(createLogFeedbackRow(item, startIndex + index));
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
  const questionCountText = `${formatLogNumber(item.question_count)} ${
    Number(item.question_count) === 1 ? "question" : "questions"
  }`;
  meta.textContent = `${questionCountText} · ${logDisplayName(item.user_name, item.user_email)}`;
  detail.append(topLine, meta);

  const timestamp = createLogTimestamp(item.last_at);
  const action = document.createElement("span");
  action.className = "material-symbols-outlined log-row-chevron";
  action.textContent = "chevron_right";
  action.setAttribute("aria-hidden", "true");

  openButton.append(detail, timestamp);
  openButton.addEventListener("click", () => {
    state.selectedLogSessionId = item.conversation_id || "";
    state.activeLogsView = "questions";
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
  row.classList.toggle("has-feedback", hasNegativeFeedback(item));
  row.dataset.logId = String(item.id || "");
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
  const user = document.createElement("span");
  user.className = "log-question-meta";
  user.textContent = logDisplayName(item.details?.user_name, item.details?.user_email);
  detail.append(questionLine, user);

  const timestamp = createLogTimestamp(item.created_at);
  const deleteButton = createLogDeleteButton(item);

  toggle.append(detail, timestamp);
  attachLogPanel(row, toggle, createLogConversationPanel(item), index);
  row.append(toggle, deleteButton, row._logPanel);
  return row;
}

function createLogFeedbackRow(item, index) {
  const row = document.createElement("article");
  row.className = "log-row log-feedback-row has-feedback";
  row.dataset.logId = String(item.id || "");
  row.dataset.status = "success";
  row.style.setProperty("--row-index", String(Math.min(index, 8)));

  const toggle = document.createElement("button");
  toggle.className = "log-row-toggle log-feedback-toggle";
  toggle.type = "button";
  toggle.setAttribute("aria-expanded", "false");

  const icon = document.createElement("span");
  icon.className = "material-symbols-outlined log-feedback-icon";
  icon.textContent = "thumb_down";
  icon.setAttribute("aria-hidden", "true");

  const copy = document.createElement("div");
  copy.className = "log-feedback-copy";
  const kicker = document.createElement("span");
  kicker.textContent = "User feedback";
  const user = document.createElement("small");
  user.className = "log-feedback-user";
  user.textContent = logDisplayName(item.details?.user_name, item.details?.user_email);
  const reason = document.createElement("p");
  reason.className = "log-feedback-reason";
  reason.textContent = feedbackReasonText(item);
  copy.append(kicker, user, reason);

  toggle.append(icon, copy);
  attachLogPanel(row, toggle, createLogFeedbackPanel(item), index);
  row.append(toggle, createLogDeleteButton(item), row._logPanel);
  return row;
}

function attachLogPanel(row, toggle, panel, index, options = {}) {
  const panelId = `log-detail-${row.dataset.status || "item"}-${index}`;
  const isOpen = row.classList.contains("is-open");
  panel.id = panelId;
  panel.setAttribute("aria-hidden", String(!isOpen));
  toggle.setAttribute("aria-controls", panelId);
  toggle.setAttribute("aria-expanded", String(isOpen));
  toggle.addEventListener("click", () => {
    const willOpen = !row.classList.contains("is-open");
    const table = row.closest(".logs-table");
    table?.querySelectorAll(".log-row.is-open").forEach((openRow) => {
      if (openRow !== row) setLogRowOpen(openRow, false);
    });
    setLogRowOpen(row, willOpen);
    options.onToggle?.(willOpen);
  });
  row._logPanel = panel;
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
    clampLogPage(getActiveLogItemCount());
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
    state.activityLogSessions = state.activityLogSessions.filter(
      (item) => item.conversation_id !== conversationId,
    );
    state.activityLogs = state.activityLogs.filter(
      (item) => item.details?.conversation_id !== conversationId,
    );
    if (state.selectedLogSessionId === conversationId) state.selectedLogSessionId = "";
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
  if (hasNegativeFeedback(item)) {
    panelInner.appendChild(createLogFeedbackDetail(item.details.feedback));
  }
  panelInner.appendChild(createLogMessage("Answer", answer, "assistant"));
  panel.appendChild(panelInner);
  window.requestAnimationFrame(() => setupLogReadMore(panel, answer));
  return panel;
}

function createLogFeedbackPanel(item) {
  const panel = document.createElement("div");
  panel.className = "log-row-panel log-feedback-panel";
  const panelInner = document.createElement("div");
  panelInner.className = "log-row-panel-inner";
  const question =
    item.details?.question ||
    item.summary ||
    "No question recorded.";
  const answer =
    item.details?.answer ||
    item.details?.answer_preview ||
    "No answer recorded.";
  panelInner.appendChild(createLogMessage("Question", question, "user"));
  panelInner.appendChild(createLogMessage("Assistant answer", answer, "assistant"));
  panel.appendChild(panelInner);
  window.requestAnimationFrame(() => setupLogReadMore(panel, answer));
  return panel;
}

function hasNegativeFeedback(item) {
  return item?.details?.feedback?.rating === "thumbs_down";
}

function feedbackReasonText(item) {
  return item?.details?.feedback?.reason || "No reason recorded.";
}

function createLogFeedbackDetail(feedback) {
  const detail = document.createElement("section");
  detail.className = "log-feedback-detail";
  const icon = document.createElement("span");
  icon.className = "material-symbols-outlined";
  icon.textContent = "thumb_down";
  icon.setAttribute("aria-hidden", "true");
  const copy = document.createElement("div");
  const heading = document.createElement("span");
  heading.className = "log-message-label";
  heading.textContent = "Feedback";
  const reason = document.createElement("p");
  reason.className = "log-message-content";
  reason.textContent = feedback?.reason || "No reason recorded.";
  copy.append(heading, reason);
  detail.append(icon, copy);
  return detail;
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
  const message =
    panel.querySelector(".log-message.is-assistant") ||
    panel.querySelector(".log-message");
  const content = message?.querySelector(".log-message-content");
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

function renderLogPagination(total, label = "questions") {
  if (!elements.logsPagination) return;
  elements.logsPagination.innerHTML = "";
  const pageSize = getLogPageSize();
  if (total <= pageSize) return;

  const pagination = getLogPagination(total);
  const nav = document.createElement("nav");
  nav.className = "logs-page-controls";
  nav.setAttribute("aria-label", "Logs pagination");

  const countLabel = label === "feedback" ? "feedback" : "questions";
  const range = document.createElement("span");
  range.className = "logs-page-label";
  range.textContent = `${formatLogNumber(pagination.startIndex + 1)}-${formatLogNumber(
    pagination.endIndex,
  )} of ${formatLogNumber(total)} ${countLabel}`;

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

  nav.append(range, previous, next);
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

function renderActiveSessionFilter() {
  if (!elements.logsSessionFilter) return;
  const sessionId =
    state.activeLogsView === "questions" ? state.selectedLogSessionId || "" : "";
  elements.logsSessionFilter.hidden = !sessionId;
  if (elements.logsActiveSessionLabel) {
    elements.logsActiveSessionLabel.textContent = sessionId
      ? "Filtered session"
      : "Session";
  }
}

function syncLogViewControls() {
  const activeView = normalizeLogsView(state.activeLogsView);
  state.activeLogsView = activeView;
  [
    elements.logsTotalChatCard,
    elements.logsTotalSessionsCard,
    elements.logsFeedbackSummaryCard,
  ].forEach((button) => {
    const isActive = normalizeLogsView(button?.dataset.logView) === activeView;
    button?.classList.toggle("is-active", isActive);
    button?.classList.toggle("is-primary", isActive);
    button?.setAttribute("aria-pressed", String(isActive));
  });
  elements.logsActivityPanel?.classList.toggle(
    "is-feedback-mode",
    activeView === "feedback",
  );
  elements.logsActivityPanel?.classList.toggle(
    "is-session-mode",
    activeView === "sessions",
  );
  if (elements.logsActivityTitle) {
    elements.logsActivityTitle.textContent = {
      questions: "Recent questions",
      sessions: "Chat sessions",
      feedback: "Feedback",
    }[activeView];
  }
}

function normalizeLogsView(value) {
  if (value === "sessions" || value === "feedback") return value;
  return "questions";
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

// Whichever machine is viewing the dashboard, not a hardcoded region.
const LOCAL_TIME_ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone;

function parseLogTimestamp(value) {
  if (!value) return null;
  const rawValue = String(value).trim();
  if (!rawValue) return null;
  const hasExplicitTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(rawValue);
  if (hasExplicitTimezone) {
    const date = new Date(rawValue);
    return Number.isNaN(date.getTime()) ? null : { date, timeZone: LOCAL_TIME_ZONE };
  }

  const match = rawValue.match(
    /^(\d{4})-(\d{2})-(\d{2})(?:[T\s](\d{2}):(\d{2})(?::(\d{2}))?)?/,
  );
  if (match) {
    const [, year, month, day, hour = "00", minute = "00", second = "00"] = match;
    const date = new Date(
      Date.UTC(
        Number(year),
        Number(month) - 1,
        Number(day),
        Number(hour),
        Number(minute),
        Number(second),
      ),
    );
    return Number.isNaN(date.getTime()) ? null : { date, timeZone: "UTC" };
  }

  const date = new Date(rawValue);
  return Number.isNaN(date.getTime()) ? null : { date, timeZone: undefined };
}

function formatLogTimeParts(value) {
  const parsed = parseLogTimestamp(value);
  if (!parsed) return { date: "-", time: "" };
  return {
    date: parsed.date.toLocaleDateString("en-US", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      timeZone: parsed.timeZone,
    }),
    time: parsed.date.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: parsed.timeZone,
    }),
  };
}
