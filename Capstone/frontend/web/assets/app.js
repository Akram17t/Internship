const CHAT_STORAGE_KEY = "ics-hr-ai-chat-v3";
const AUTH_STORAGE_KEY = "ics-hr-ai-auth-v1";
const CONVERSATION_STORAGE_KEY = "ics-hr-ai-conversation-v1";
const REINDEX_STORAGE_KEY = "ics-hr-ai-reindex-required-v1";
const MOBILE_QUERY = "(max-width: 640px)";

const initialMessages = [];

const screens = {
  chat: "Active Session",
  faq: "Frequently Asked Questions",
  policy: "Document Library",
  guardrails: "Guardrails",
  logs: "Activity Logs",
  analytics: "Usage Analytics",
};
const adminScreens = new Set(["guardrails", "logs", "analytics"]);

const loadingStageLabels = [
  "Understanding the question...",
  "Searching documents...",
  "Composing the answer...",
];

const state = {
  activeScreen: "chat",
  isSubmitting: false,
  activeRequestController: null,
  activeRequestStartedAt: null,
  activeLoadingStageTimeouts: [],
  activeAutoAskRun: null,
  stickToBottom: true,
  chatScrollBound: false,
  activeReveal: null,
  conversationId: loadConversationId(),
  messages: loadMessages(),
  documents: [],
  filter: "",
  session: loadSession(),
  googleClientId: "",
  conversations: [],
  isLoadingConversations: false,
  faqItems: [],
  editingFaqId: "",
  isMutatingFaq: false,
  activeFaqGeneration: null,
  needsReindex: loadReindexRequired(),
  isReindexing: false,
  pendingReplacePath: "",
  pendingFormSopPath: "",
  activeDocumentFormPath: "",
  isMutatingDocument: false,
  documentUndo: null,
  documentUndoStack: [],
  documentChanges: [],
  activityLogs: [],
  activityLogSessions: [],
  activityLogSummary: null,
  activeLogsView: "questions",
  selectedLogSessionId: "",
  logDateRange: null,
  logPage: 1,
  logPageSize: 10,
  isLoadingLogs: false,
  logError: "",
  pendingFeedbackMessage: null,
  isSubmittingFeedback: false,
  pendingTemplateDownload: null,
  typingAnimationEnabled: true,
};

let publicConfigPromise = null;

const elements = {
  body: document.body,
  screenTitle: document.getElementById("screenTitle"),
  sidebar: document.getElementById("sidebar"),
  navLinks: Array.from(document.querySelectorAll(".nav-link")),
  screens: Array.from(document.querySelectorAll(".screen")),
  chatScreen: document.querySelector('[data-screen-panel="chat"]'),
  chatThread: document.getElementById("chatThread"),
  chatForm: document.getElementById("chatForm"),
  chatInput: document.getElementById("chatInput"),
  sendButton: document.getElementById("sendButton"),
  newChatButton: document.getElementById("newChatButton"),
  conversationList: document.getElementById("conversationList"),
  conversationItemTemplate: document.getElementById("conversationItemTemplate"),
  faqList: document.getElementById("faqList"),
  faqForm: document.getElementById("faqForm"),
  faqIdInput: document.getElementById("faqIdInput"),
  faqQuestionInput: document.getElementById("faqQuestionInput"),
  faqSubmitButton: document.getElementById("faqSubmitButton"),
  faqStopButton: document.getElementById("faqStopButton"),
  faqStatus: document.getElementById("faqStatus"),
  libraryList: document.getElementById("libraryList"),
  librarySearch: document.getElementById("librarySearch"),
  policySearchWrap: document.getElementById("policySearchWrap"),
  policyNavLink: document.querySelector('.nav-link[data-screen="policy"]'),
  guardrailsNavLink: document.querySelector('.nav-link[data-screen="guardrails"]'),
  guardrailsForm: document.getElementById("guardrailsForm"),
  guardrailsTextarea: document.getElementById("guardrailsTextarea"),
  guardrailsSaveButton: document.getElementById("guardrailsSaveButton"),
  guardrailsStatus: document.getElementById("guardrailsStatus"),
  logsNavLink: document.querySelector('.nav-link[data-screen="logs"]'),
  logsNameSearch: document.getElementById("logsNameSearch"),
  logsStartDate: document.getElementById("logsStartDate"),
  logsEndDate: document.getElementById("logsEndDate"),
  logsActivityPanel: document.querySelector(".logs-activity-panel"),
  logsActivityTitle: document.querySelector(".logs-list-toolbar h3"),
  logsRefreshButton: document.getElementById("logsRefreshButton"),
  logsTotalChatCard: document.getElementById("logsTotalChatCard"),
  logsTotalSessionsCard: document.getElementById("logsTotalSessionsCard"),
  logsFeedbackSummaryCard: document.getElementById("logsFeedbackSummaryCard"),
  logsSessionFilter: document.getElementById("logsSessionFilter"),
  logsActiveSessionLabel: document.getElementById("logsActiveSessionLabel"),
  logsClearSessionButton: document.getElementById("logsClearSessionButton"),
  logsPagination: document.getElementById("logsPagination"),
  logsList: document.getElementById("logsList"),
  logsStatus: document.getElementById("logsStatus"),
  logsTotalChat: document.getElementById("logsTotalChat"),
  logsTotalSessions: document.getElementById("logsTotalSessions"),
  logsNegativeFeedback: document.getElementById("logsNegativeFeedback"),
  analyticsNavLink: document.querySelector('.nav-link[data-screen="analytics"]'),
  filterButton: document.getElementById("filterButton"),
  chatLink: document.getElementById("chatLink"),
  menuToggle: document.getElementById("menuToggle"),
  pageBackdrop: document.getElementById("pageBackdrop"),
  accountPanel: document.querySelector(".account-panel"),
  accountAvatar: document.getElementById("accountAvatar"),
  accountRoleLabel: document.getElementById("accountRoleLabel"),
  accountName: document.getElementById("accountName"),
  accountHint: document.getElementById("accountHint"),
  accountActionButton: document.getElementById("accountActionButton"),
  accountActionIcon: document.getElementById("accountActionIcon"),
  accountActionText: document.getElementById("accountActionText"),
  accountPopover: document.getElementById("accountPopover"),
  accountPopoverRole: document.getElementById("accountPopoverRole"),
  accountPopoverName: document.getElementById("accountPopoverName"),
  accountPopoverHint: document.getElementById("accountPopoverHint"),
  newAdminButton: document.getElementById("newAdminButton"),
  signInGate: document.getElementById("signInGate"),
  googleSignInButton: document.getElementById("googleSignInButton"),
  signInError: document.getElementById("signInError"),
  feedbackModal: document.getElementById("feedbackModal"),
  feedbackForm: document.getElementById("feedbackForm"),
  feedbackReason: document.getElementById("feedbackReason"),
  feedbackStatus: document.getElementById("feedbackStatus"),
  feedbackCloseButton: document.getElementById("feedbackCloseButton"),
  feedbackCancelButton: document.getElementById("feedbackCancelButton"),
  feedbackSubmitButton: document.getElementById("feedbackSubmitButton"),
  newAdminModal: document.getElementById("newAdminModal"),
  newAdminForm: document.getElementById("newAdminForm"),
  newAdminEmail: document.getElementById("newAdminEmail"),
  newAdminStatus: document.getElementById("newAdminStatus"),
  newAdminCloseButton: document.getElementById("newAdminCloseButton"),
  logoutModal: document.getElementById("logoutModal"),
  logoutCancelButton: document.getElementById("logoutCancelButton"),
  logoutConfirmButton: document.getElementById("logoutConfirmButton"),
  documentErrorModal: document.getElementById("documentErrorModal"),
  documentErrorTitle: document.getElementById("documentErrorTitle"),
  documentErrorSummary: document.getElementById("documentErrorSummary"),
  documentErrorList: document.getElementById("documentErrorList"),
  documentErrorCloseButton: document.getElementById("documentErrorCloseButton"),
  templateDownloadModal: document.getElementById("templateDownloadModal"),
  templateDownloadName: document.getElementById("templateDownloadName"),
  templateDownloadPdfButton: document.getElementById("templateDownloadPdfButton"),
  templateDownloadWordButton: document.getElementById("templateDownloadWordButton"),
  templateDownloadCancelButton: document.getElementById("templateDownloadCancelButton"),
  adminDocumentPanel: document.getElementById("adminDocumentPanel"),
  adminDocumentForm: document.getElementById("adminDocumentForm"),
  documentFileInput: document.getElementById("documentFileInput"),
  documentFileLabel: document.getElementById("documentFileLabel"),
  documentUploadButton: document.getElementById("documentUploadButton"),
  documentUndoButton: document.getElementById("documentUndoButton"),
  documentReindexButton: document.getElementById("documentReindexButton"),
  documentReplaceInput: document.getElementById("documentReplaceInput"),
  formFileInput: document.getElementById("formFileInput"),
  adminDocumentStatus: document.getElementById("adminDocumentStatus"),
  appLockOverlay: document.getElementById("appLockOverlay"),
  messageTemplate: document.getElementById("messageTemplate"),
  faqTemplate: document.getElementById("faqTemplate"),
  libraryItemTemplate: document.getElementById("libraryItemTemplate"),
};

init();

function init() {
  publicConfigPromise = loadPublicConfig();
  bindNavigation();
  bindChat();
  bindAdminFaqs();
  bindPolicyActions();
  bindAuth();
  bindAdminDocuments();
  bindGuardrails();
  bindAdminLogs();
  bindSidebarConversations();
  syncAuth();
  syncReindexState();
  updateComposer();
  renderMessages();
  renderFaqs();
  syncScreenFromHash();
  void publicConfigPromise.then(() => initGoogleSignIn());
  window.addEventListener("resize", updateComposer);
}

async function loadPublicConfig() {
  try {
    const response = await fetch("/api/config", { cache: "no-store" });
    if (!response.ok) return;
    const payload = await response.json();
    state.typingAnimationEnabled =
      payload.typing_animation_enabled !== false;
    state.googleClientId = String(payload.google_client_id || "");
  } catch (error) {
    console.warn("Failed to load frontend config.", error);
  }
}

function bindNavigation() {
  window.addEventListener("hashchange", syncScreenFromHash);
  elements.navLinks.forEach((button) => {
    button.addEventListener("click", () => navigateTo(button.dataset.screen));
  });
  elements.menuToggle.addEventListener("click", openMobileNav);
  elements.pageBackdrop.addEventListener("click", closeMobileNav);
}

function syncScreenFromHash() {
  const hash = window.location.hash.slice(1);
  const target =
    screens[hash] && (!adminScreens.has(hash) || isAdminSession()) ? hash : "chat";
  state.activeScreen = target;
  elements.body.dataset.activeScreen = target;
  elements.screenTitle.textContent = screens[target];

  elements.navLinks.forEach((button) =>
    button.classList.toggle("is-active", button.dataset.screen === target),
  );
  elements.screens.forEach((screen) =>
    screen.classList.toggle("is-active", screen.dataset.screenPanel === target),
  );
  if (target === "logs") refreshActivityLogsIfVisible();
  if (target === "analytics") refreshAnalyticsIfVisible();
  if (target === "guardrails") loadGuardrailsIfVisible();
  closeMobileNav();
}

function navigateTo(screen) {
  const target =
    adminScreens.has(screen) && !isAdminSession() ? "chat" : screen || "chat";
  window.location.hash = target;
}

// Bridge called from the embedded React analytics dashboard (separate
// bundle, see frontend-dashboard/) so clicking a user or topic there can
// jump into the existing vanilla Logs screen with a filter applied,
// without the two bundles needing to share any framework/state directly.
window.navigateToLogsWithFilter = function navigateToLogsWithFilter(type, value, label) {
  if (!isAdminSession()) return;
  state.logNameQuery = "";
  state.activeTopicFilter = null;
  if (elements.logsNameSearch) elements.logsNameSearch.value = "";

  if (type === "user" && value) {
    state.logNameQuery = String(value).trim().toLowerCase();
    if (elements.logsNameSearch) elements.logsNameSearch.value = value;
  } else if (type === "topic" && value) {
    state.activeTopicFilter = { code: value, name: label || value };
  }

  state.activeLogsView = "questions";
  state.selectedLogSessionId = "";
  resetLogPage();
  navigateTo("logs");
  void loadActivityLogs();
};

function openMobileNav() {
  elements.sidebar.scrollTop = 0;
  elements.body.classList.add("nav-open");
}

function closeMobileNav() {
  elements.body.classList.remove("nav-open");
}

function loadMessages() {
  const raw = window.localStorage.getItem(CHAT_STORAGE_KEY);
  if (!raw) return [...initialMessages];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [...initialMessages];
  } catch {
    return [...initialMessages];
  }
}

function persistMessages() {
  window.localStorage.setItem(
    CHAT_STORAGE_KEY,
    JSON.stringify(state.messages.filter((message) => !message.loading)),
  );
}

function createConversationId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `chat-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function loadConversationId() {
  const existing = window.localStorage.getItem(CONVERSATION_STORAGE_KEY);
  if (existing) return existing;

  const nextId = createConversationId();
  window.localStorage.setItem(CONVERSATION_STORAGE_KEY, nextId);
  return nextId;
}

function loadReindexRequired() {
  return window.localStorage.getItem(REINDEX_STORAGE_KEY) === "1";
}

function loadSession() {
  const signedOut = {
    role: "",
    email: "",
    name: "",
    token: "",
    expires_at: "",
  };
  const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
  if (!raw) return signedOut;

  try {
    const parsed = JSON.parse(raw);
    if (parsed.role !== "admin" && parsed.role !== "user") return signedOut;
    const session = {
      role: parsed.role,
      email: String(parsed.email || "").toLowerCase(),
      name: String(parsed.name || ""),
      token: String(parsed.token || ""),
      expires_at: String(parsed.expires_at || ""),
    };
    return isSessionExpired(session) || !session.token ? signedOut : session;
  } catch {
    return signedOut;
  }
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      const value = String(reader.result || "");
      resolve(value.includes(",") ? value.split(",").pop() : value);
    });
    reader.addEventListener("error", () => reject(reader.error));
    reader.readAsDataURL(file);
  });
}

async function readJsonResponse(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

function formatApiError(detail, fallback = "Request failed.") {
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => formatApiError(item, ""))
      .filter(Boolean);
    return messages.join("; ") || fallback;
  }
  if (typeof detail === "object") {
    if (typeof detail.message === "string") return detail.message;
    if (typeof detail.msg === "string") return detail.msg;
    if (typeof detail.detail === "string") return detail.detail;
    return JSON.stringify(detail);
  }
  return String(detail);
}
