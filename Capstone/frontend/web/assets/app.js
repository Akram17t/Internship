const CHAT_STORAGE_KEY = "ics-hr-ai-chat-v3";
const AUTH_STORAGE_KEY = "ics-hr-ai-auth-v1";
const CONVERSATION_STORAGE_KEY = "ics-hr-ai-conversation-v1";
const REINDEX_STORAGE_KEY = "ics-hr-ai-reindex-required-v1";
const MOBILE_QUERY = "(max-width: 640px)";
const PDFJS_WORKER_URL =
  "https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/pdf.worker.min.js";

const initialMessages = [];

const screens = {
  chat: "Active Session",
  faq: "Frequently Asked Questions",
  policy: "Document Library",
  logs: "Activity Logs",
};
const adminScreens = new Set(["policy", "logs"]);

const loadingStageLabels = [
  "Memahami pertanyaan...",
  "Mencari dokumen...",
  "Menyusun jawaban...",
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
  faqItems: [],
  editingFaqId: "",
  isMutatingFaq: false,
  activeFaqGeneration: null,
  needsReindex: loadReindexRequired(),
  isReindexing: false,
  pendingReplacePath: "",
  isMutatingDocument: false,
  documentUndo: null,
  documentUndoStack: [],
  documentChanges: [],
  activityLogs: [],
  activityLogSummary: null,
  logDateRange: null,
  logPage: 1,
  logPageSize: 10,
  isLoadingLogs: false,
  logError: "",
  pendingFormFill: null,
  pendingTemplateDownload: null,
  typingAnimationEnabled: true,
};

let publicConfigPromise = null;

if (window.pdfjsLib?.GlobalWorkerOptions) {
  window.pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS_WORKER_URL;
}

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
  logsNavLink: document.querySelector('.nav-link[data-screen="logs"]'),
  logsStartDate: document.getElementById("logsStartDate"),
  logsEndDate: document.getElementById("logsEndDate"),
  logsRefreshButton: document.getElementById("logsRefreshButton"),
  logsResultCount: document.getElementById("logsResultCount"),
  logsPagination: document.getElementById("logsPagination"),
  logsList: document.getElementById("logsList"),
  logsStatus: document.getElementById("logsStatus"),
  logsTotalChat: document.getElementById("logsTotalChat"),
  logsTotalSessions: document.getElementById("logsTotalSessions"),
  logsAverageChat: document.getElementById("logsAverageChat"),
  logsFallbackError: document.getElementById("logsFallbackError"),
  filterButton: document.getElementById("filterButton"),
  chatLink: document.getElementById("chatLink"),
  formDraftMenu: document.getElementById("formDraftMenu"),
  formDraftButton: document.getElementById("formDraftButton"),
  formDraftCount: document.getElementById("formDraftCount"),
  formDraftPopover: document.getElementById("formDraftPopover"),
  formDraftList: document.getElementById("formDraftList"),
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
  authModal: document.getElementById("authModal"),
  authForm: document.getElementById("authForm"),
  adminEmail: document.getElementById("adminEmail"),
  adminPassword: document.getElementById("adminPassword"),
  authError: document.getElementById("authError"),
  authCloseButton: document.getElementById("authCloseButton"),
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
  formFillModal: document.getElementById("formFillModal"),
  formFillForm: document.getElementById("formFillForm"),
  formFillCloseButton: document.getElementById("formFillCloseButton"),
  formFillTitle: document.getElementById("formFillTitle"),
  formFillSubtitle: document.getElementById("formFillSubtitle"),
  formFillStatus: document.getElementById("formFillStatus"),
  formFillPreview: document.getElementById("formFillPreview"),
  formFillFields: document.getElementById("formFillFields"),
  formFillClearDraftButton: document.getElementById("formFillClearDraftButton"),
  adminDocumentPanel: document.getElementById("adminDocumentPanel"),
  adminDocumentForm: document.getElementById("adminDocumentForm"),
  documentFileInput: document.getElementById("documentFileInput"),
  documentFileLabel: document.getElementById("documentFileLabel"),
  documentUploadButton: document.getElementById("documentUploadButton"),
  documentUndoButton: document.getElementById("documentUndoButton"),
  documentReindexButton: document.getElementById("documentReindexButton"),
  documentReplaceInput: document.getElementById("documentReplaceInput"),
  adminDocumentStatus: document.getElementById("adminDocumentStatus"),
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
  bindAdminLogs();
  window.FormDraftLauncher.init({ state, elements });
  syncAuth();
  syncReindexState();
  updateComposer();
  renderMessages();
  renderFaqs();
  syncScreenFromHash();
  void loadFaqs();
  window.addEventListener("resize", updateComposer);
}

async function loadPublicConfig() {
  try {
    const response = await fetch("/api/config", { cache: "no-store" });
    if (!response.ok) return;
    const payload = await response.json();
    state.typingAnimationEnabled =
      payload.typing_animation_enabled !== false;
  } catch (error) {
    console.warn("Frontend config gagal dimuat.", error);
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
  closeMobileNav();
}

function navigateTo(screen) {
  const target =
    adminScreens.has(screen) && !isAdminSession() ? "chat" : screen || "chat";
  window.location.hash = target;
}

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
  const guest = {
    role: "guest",
    email: "",
    name: "Guest",
    token: "",
    expires_at: "",
  };
  const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
  if (!raw) return guest;

  try {
    const parsed = JSON.parse(raw);
    const session = {
      role: parsed.role === "admin" ? "admin" : "guest",
      email: String(parsed.email || "").toLowerCase(),
      name: String(parsed.name || "Admin"),
      token: String(parsed.token || ""),
      expires_at: String(parsed.expires_at || ""),
    };
    return isSessionExpired(session) || !session.token ? guest : session;
  } catch {
    return guest;
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
