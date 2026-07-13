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
};

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
  pendingFormFill: null,
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
  formFillModal: document.getElementById("formFillModal"),
  formFillForm: document.getElementById("formFillForm"),
  formFillCloseButton: document.getElementById("formFillCloseButton"),
  formFillSubtitle: document.getElementById("formFillSubtitle"),
  formFillFields: document.getElementById("formFillFields"),
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
    screens[hash] && (hash !== "policy" || isAdminSession()) ? hash : "chat";
  state.activeScreen = target;
  elements.body.dataset.activeScreen = target;
  elements.screenTitle.textContent = screens[target];

  elements.navLinks.forEach((button) =>
    button.classList.toggle("is-active", button.dataset.screen === target),
  );
  elements.screens.forEach((screen) =>
    screen.classList.toggle("is-active", screen.dataset.screenPanel === target),
  );
  closeMobileNav();
}

function navigateTo(screen) {
  const target =
    screen === "policy" && !isAdminSession() ? "chat" : screen || "chat";
  window.location.hash = target;
}

function openMobileNav() {
  elements.sidebar.scrollTop = 0;
  elements.body.classList.add("nav-open");
}

function closeMobileNav() {
  elements.body.classList.remove("nav-open");
}

function bindChat() {
  elements.newChatButton.addEventListener("click", resetChat);

  elements.chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.isSubmitting) return;
    await submitQuestion(elements.chatInput.value);
  });

  elements.sendButton.addEventListener("click", (event) => {
    if (!state.isSubmitting) return;
    event.preventDefault();
    stopGeneration();
  });

  elements.chatInput.addEventListener("keydown", async (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (state.isSubmitting) return;
      await submitQuestion(elements.chatInput.value);
    }
  });
}

function normalizeAutoAskQuestions(input) {
  if (Array.isArray(input)) {
    return input.map((item) => String(item || "").trim()).filter(Boolean);
  }

  if (typeof input === "string") {
    return input
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  return [];
}

function wait(delayMs) {
  return new Promise((resolve) => window.setTimeout(resolve, delayMs));
}

async function runAutoAskSequence(input, options = {}) {
  const questions = normalizeAutoAskQuestions(input);
  if (!questions.length) {
    throw new Error("Daftar pertanyaan kosong.");
  }
  if (state.activeAutoAskRun?.running) {
    throw new Error("Auto-ask sedang berjalan.");
  }

  const config = {
    delayMs: Number.isFinite(options.delayMs) ? Number(options.delayMs) : 1200,
    reset: options.reset !== false,
  };
  const run = {
    running: true,
    stopped: false,
    questions,
    index: 0,
    startedAt: Date.now(),
    config,
    stop() {
      this.stopped = true;
    },
  };
  state.activeAutoAskRun = run;

  navigateTo("chat");
  if (config.reset) {
    resetChat();
  }

  try {
    for (let index = 0; index < questions.length; index += 1) {
      if (run.stopped) break;
      run.index = index;
      console.info(
        `[icsAutoAsk] Menjalankan ${index + 1}/${questions.length}: ${questions[index]}`,
      );
      await submitQuestion(questions[index]);
      if (run.stopped || index === questions.length - 1) continue;
      await wait(config.delayMs);
    }
  } finally {
    run.running = false;
    state.activeAutoAskRun = null;
  }

  return {
    stopped: run.stopped,
    total: questions.length,
    selesai: run.stopped ? run.index : questions.length,
  };
}

function stopAutoAskSequence() {
  state.activeAutoAskRun?.stop();
}

function getAutoAskStatus() {
  const run = state.activeAutoAskRun;
  if (!run?.running) {
    return { running: false };
  }

  return {
    running: true,
    index: run.index,
    total: run.questions.length,
    currentQuestion: run.questions[run.index] || "",
    startedAt: run.startedAt,
    delayMs: run.config.delayMs,
  };
}

window.icsAutoAsk = {
  run: runAutoAskSequence,
  stop: stopAutoAskSequence,
  status: getAutoAskStatus,
};

function resetChat() {
  if (state.isSubmitting) return;
  state.messages = [];
  state.conversationId = createConversationId();
  window.localStorage.removeItem(CHAT_STORAGE_KEY);
  window.localStorage.setItem(CONVERSATION_STORAGE_KEY, state.conversationId);
  elements.chatInput.value = "";
  renderMessages("smooth");
  navigateTo("chat");
  window.setTimeout(() => elements.chatInput.focus(), 0);
}

async function submitQuestion(rawQuestion) {
  const question = rawQuestion.trim();
  if (!question || state.isSubmitting) return;
  const startedAt = performance.now();
  const controller = new AbortController();

  state.isSubmitting = true;
  state.activeRequestController = controller;
  state.activeRequestStartedAt = startedAt;
  updateComposer();
  state.messages.push(
    { role: "user", content: question, timestamp: "Just now" },
    {
      role: "assistant",
      loading: true,
      loading_text: loadingStageLabels[0],
      timestamp: "thinking",
    },
  );
  elements.chatInput.value = "";
  // Saat user mengirim pertanyaan, selalu bawa tampilan ke bawah dulu.
  state.stickToBottom = true;
  renderMessages("smooth");
  beginLoadingStages();

  try {
    const response = await fetch("/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        conversation_id: state.conversationId,
      }),
      signal: controller.signal,
    });
    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const errorPayload = await response.json();
        detail = errorPayload.detail || detail;
      } catch (_) {
        // Keep the generic HTTP status when the server did not return JSON.
      }
      throw new Error(detail);
    }
    const payload = await response.json();
    if (payload.conversation_id) {
      state.conversationId = payload.conversation_id;
      window.localStorage.setItem(
        CONVERSATION_STORAGE_KEY,
        state.conversationId,
      );
    }

    const fullText = payload.answer || "No answer was returned.";
    if (publicConfigPromise) {
      await publicConfigPromise;
    }
    // Ganti bubble loading dengan pesan mode "streaming", lalu ketik bertahap.
    const streamMessage = {
      role: "assistant",
      streaming: true,
      content: "",
      citations: Array.isArray(payload.citations) ? payload.citations : [],
      form_downloads: Array.isArray(payload.form_downloads)
        ? payload.form_downloads
        : [],
      flowcharts: Array.isArray(payload.flowcharts) ? payload.flowcharts : [],
      duration_ms: Math.round(performance.now() - startedAt),
      timestamp: "Just now",
    };
    clearLoadingStages();
    replaceLoading(streamMessage);
    if (state.typingAnimationEnabled) {
      await animateAssistantReveal(streamMessage, fullText);
    } else {
      streamMessage.content = fullText;
    }
    // Selesai menampilkan jawaban: matikan mode streaming agar render final (markdown kaya).
    streamMessage.streaming = false;
    streamMessage.content = fullText;
  } catch (error) {
    if (error.name === "AbortError") return;
    replaceLoading({
      role: "assistant",
      content: `Aku belum bisa menyelesaikan jawaban ini. ${error.message || "Pastikan FastAPI, Ollama, dan database embedding sedang berjalan."}`,
      citations: [],
      flowcharts: [],
      duration_ms: Math.round(performance.now() - startedAt),
      timestamp: "Just now",
    });
    console.error(error);
  } finally {
    clearLoadingStages();
    state.isSubmitting = false;
    state.activeRequestController = null;
    state.activeRequestStartedAt = null;
    updateComposer();
    persistMessages();
    renderMessages("smooth");
  }
}

function stopGeneration() {
  if (!state.isSubmitting) return;

  // Jika jawaban sudah tiba dan sedang dianimasikan, cukup tuntaskan seketika.
  if (state.activeReveal) {
    state.activeReveal.finish();
    return;
  }

  const durationMs = state.activeRequestStartedAt
    ? Math.round(performance.now() - state.activeRequestStartedAt)
    : undefined;

  state.activeRequestController?.abort();
  clearLoadingStages();
  replaceLoading({
    role: "assistant",
    content: "Respons dihentikan.",
    citations: [],
    flowcharts: [],
    duration_ms: durationMs,
    timestamp: "Just now",
  });
  state.isSubmitting = false;
  state.activeRequestController = null;
  state.activeRequestStartedAt = null;
  updateComposer();
  persistMessages();
  renderMessages("smooth");
  elements.chatInput.focus();
}

function replaceLoading(message) {
  const index = state.messages.findIndex(
    (item) => item.loading || item.streaming,
  );
  if (index === -1) state.messages.push(message);
  else state.messages.splice(index, 1, message);
}

function animateAssistantReveal(message, fullText) {
  // Ungkap jawaban penuh secara bertahap (efek mengetik) lalu selesai.
  // Jawaban sudah lengkap dari server; ini murni animasi tampilan.
  return new Promise((resolve) => {
    message.loading = false;
    message.streaming = true;
    message.content = "";
    message.timestamp = "Just now";
    renderMessages("auto");

    const bubble = elements.chatThread.querySelector(
      ".message:last-child .message-bubble",
    );
    const charsPerSecond = 50;
    const minStep = 1;
    let shown = 0;
    let last = performance.now();
    let frame = null;

    const paint = () => {
      message.content = fullText.slice(0, shown);
      if (bubble) bubble.textContent = message.content;
      if (state.stickToBottom) {
        elements.chatThread.scrollTop = elements.chatThread.scrollHeight;
      }
    };

    const finish = () => {
      if (frame) window.cancelAnimationFrame(frame);
      frame = null;
      shown = fullText.length;
      paint();
      state.activeReveal = null;
      resolve();
    };

    const step = (now) => {
      const delta = now - last;
      last = now;
      shown = Math.min(
        fullText.length,
        shown + Math.max(minStep, Math.round((charsPerSecond * delta) / 1000)),
      );
      paint();
      if (shown >= fullText.length) {
        finish();
        return;
      }
      frame = window.requestAnimationFrame(step);
    };

    state.activeReveal = { finish };
    if (!fullText) {
      finish();
      return;
    }
    frame = window.requestAnimationFrame(step);
  });
}

function clearLoadingStages() {
  state.activeLoadingStageTimeouts.forEach((timeoutId) =>
    window.clearTimeout(timeoutId),
  );
  state.activeLoadingStageTimeouts = [];
}

function setLoadingStage(index) {
  const loadingMessage = state.messages.find((item) => item.loading);
  if (!loadingMessage) return;
  loadingMessage.loading_text =
    loadingStageLabels[index] || loadingStageLabels.at(-1);
  renderMessages("smooth");
}

function beginLoadingStages() {
  clearLoadingStages();
  setLoadingStage(0);

  const stageSchedule = [
    { index: 1, delay: 2200 },
    { index: 2, delay: 7000 },
  ];
  state.activeLoadingStageTimeouts = stageSchedule.map(({ index, delay }) =>
    window.setTimeout(() => {
      if (!state.isSubmitting) return;
      setLoadingStage(index);
    }, delay),
  );
}

function renderMessages(scrollBehavior = "auto") {
  elements.chatThread.innerHTML = "";
  elements.chatScreen.classList.toggle("is-empty", state.messages.length === 0);
  state.messages.forEach((message) => {
    const fragment = elements.messageTemplate.content.cloneNode(true);
    const article = fragment.querySelector(".message");
    const bubble = fragment.querySelector(".message-bubble");
    const meta = fragment.querySelector(".message-meta");
    const isAssistant = message.role === "assistant";

    article.classList.add(isAssistant ? "is-assistant" : "is-user");
    if (message.loading) {
      article.classList.add("message--loading");
      bubble.innerHTML = `<span class="loading-dots"><span></span><span></span><span></span></span>${message.loading_text || loadingStageLabels[0]}`;
    } else if (message.streaming) {
      article.classList.add("message--streaming");
      bubble.classList.add("is-streaming");
      bubble.textContent = message.content || "";
    } else {
      const formDownloads = normalizeFormDownloads(message.form_downloads);
      bubble.appendChild(
        formatMessage(message.content, message.citations, formDownloads),
      );
      renderFormDownloads(
        bubble,
        formDownloads.filter((item) => !item.used),
      );
      renderFlowchartScreenshots(bubble, message.flowcharts);
    }

    meta.textContent = `${isAssistant ? "AI Assistant" : "You"} • ${message.timestamp || "Just now"}`;
    if (isAssistant && Number.isFinite(message.duration_ms)) {
      const duration = document.createElement("span");
      duration.className = "message-duration";
      duration.textContent = formatDuration(message.duration_ms);
      meta.append(" • ", duration);
    }
    elements.chatThread.appendChild(fragment);
  });
  scrollChatToBottom(scrollBehavior);
}

function renderFlowchartScreenshots(container, flowcharts) {
  if (!Array.isArray(flowcharts)) return;
  flowcharts.forEach((flowchart) => {
    if (!flowchart?.image_url) return;
    const card = document.createElement("figure");
    card.className = "flowchart-screenshot";

    const caption = document.createElement("figcaption");
    const title = document.createElement("strong");
    title.textContent = flowchart.title || "Alur Proses";
    const meta = document.createElement("span");
    meta.textContent = [
      flowchart.source,
      flowchart.page ? `Halaman ${flowchart.page}` : "",
    ]
      .filter(Boolean)
      .join(" / ");
    caption.append(title, meta);

    const link = document.createElement("a");
    link.href = flowchart.image_url;
    link.target = "_blank";
    link.rel = "noopener";
    link.setAttribute("aria-label", `Buka ${flowchart.title || "flowchart"}`);
    const image = document.createElement("img");
    image.src = flowchart.image_url;
    image.alt = flowchart.title || "Flowchart dari dokumen SOP";
    image.loading = "lazy";
    link.appendChild(image);
    card.append(caption, link);
    container.appendChild(card);
  });
}

function isNearChatBottom(threshold = 120) {
  const thread = elements.chatThread;
  if (!thread) return true;
  return (
    thread.scrollHeight - thread.scrollTop - thread.clientHeight <= threshold
  );
}

function bindChatAutoScroll() {
  // Lacak apakah user sedang di dekat bawah; kalau scroll ke atas, jangan diseret balik.
  if (state.chatScrollBound || !elements.chatThread) return;
  state.chatScrollBound = true;
  elements.chatThread.addEventListener(
    "scroll",
    () => {
      state.stickToBottom = isNearChatBottom();
    },
    { passive: true },
  );
}

function scrollChatToBottom(behavior = "auto", { force = false } = {}) {
  bindChatAutoScroll();
  if (!force && !state.stickToBottom) return;

  const scrollToLatest = () => {
    if (!force && !state.stickToBottom) return;
    elements.chatThread.scrollTop = elements.chatThread.scrollHeight;
    document.scrollingElement?.scrollTo({
      top: document.scrollingElement.scrollHeight,
      behavior: "auto",
    });
  };

  window.requestAnimationFrame(() => {
    scrollToLatest();
    // Susulan singkat untuk konten yang muncul belakangan (chip/flowchart) di render final.
    if (behavior === "smooth") {
      window.setTimeout(scrollToLatest, 120);
      window.setTimeout(scrollToLatest, 320);
    }
  });
}

function renderMessageCitations(container, citations) {
  if (!Array.isArray(citations) || !citations.length) return;

  const list = document.createElement("div");
  list.className = "citation-chips";

  citations.forEach((citation, index) => {
    list.appendChild(createCitationChip(citation, index));
  });

  container.appendChild(list);
  container.hidden = false;
}

function createCitationChip(citation, index, isInline = false) {
  const fileType = getCitationFileType(citation);
  const canOpenDocument = Boolean(citation.download_url) && isAdminSession();
  const isPublicForm =
    Boolean(citation.download_url) && isFormSource(citation.source);
  const chip = isPublicForm
    ? document.createElement("a")
    : document.createElement("button");
  chip.className = `citation-chip citation-chip--${fileType}`;
  if (isInline) chip.classList.add("is-inline");
  chip.setAttribute("aria-label", formatCitationLabel(citation, index));
  chip.title = formatCitationLabel(citation, index);

  if (isPublicForm) {
    chip.href = citation.download_url;
    chip.target = "_blank";
    chip.rel = "noopener";
  } else {
    chip.type = "button";
    if (canOpenDocument) {
      chip.addEventListener("click", () =>
        downloadDocument(citation.download_url, citation.source),
      );
    }
  }

  const icon = document.createElement("span");
  icon.className = "material-symbols-outlined citation-chip-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = getCitationIcon(fileType);

  const tooltip = document.createElement("span");
  tooltip.className = "citation-tooltip";
  tooltip.setAttribute("role", "tooltip");

  const title = document.createElement("strong");
  title.textContent = citation.source || "Unknown source";

  const meta = document.createElement("span");
  meta.textContent = formatCitationLocation(citation);

  tooltip.append(title, meta);
  chip.append(icon, tooltip);
  return chip;
}

function renderFormDownloads(container, downloads = []) {
  const items = Array.isArray(downloads) ? downloads : [];
  if (!items.length) return;

  const wrapper = document.createElement("div");
  wrapper.className = "form-downloads";

  const label = document.createElement("span");
  label.className = "form-downloads-label";
  label.textContent = "Form yang bisa diunduh";

  const list = document.createElement("div");
  list.className = "form-downloads-list";

  items.forEach((item) => {
    list.appendChild(createFormDownloadRow(item));
  });

  wrapper.append(label, list);
  container.appendChild(wrapper);
}

function createFormDownloadRow(item) {
  const row = document.createElement("div");
  row.className = "form-download-row";

  const name = document.createElement("span");
  name.className = "form-download-name";
  const icon = document.createElement("span");
  icon.className = "material-symbols-outlined form-download-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = "picture_as_pdf";
  const text = document.createElement("span");
  text.textContent = item.label || item.name || "Form";
  name.append(icon, text);

  const fileName = `${item.label || item.name || "form"}.pdf`;

  const templateButton = document.createElement("button");
  templateButton.type = "button";
  templateButton.className = "form-download-action";
  templateButton.textContent = "Template";
  templateButton.title = "Unduh form kosong";
  templateButton.addEventListener("click", () => {
    if (item.download_url) downloadDocument(item.download_url, fileName);
  });

  const filledButton = document.createElement("button");
  filledButton.type = "button";
  filledButton.className = "form-download-action is-primary";
  filledButton.textContent = "Isi & download";
  filledButton.title = "Isi data lalu unduh form yang sudah terisi";
  filledButton.addEventListener("click", () => {
    if (item.download_url) openFormFillModal(item);
  });

  row.append(name, templateButton, filledButton);
  return row;
}

function normalizeFormDownloads(downloads = []) {
  if (!Array.isArray(downloads) || !downloads.length) return [];

  const seen = new Set();
  return downloads
    .filter((item) => {
      const key = item.download_url || item.name || item.display_name;
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .map((item) => ({
      ...item,
      label: item.display_name || item.name || "Form",
      used: false,
    }));
}

function createFormDownloadChip(item, isInline = false) {
  const link = document.createElement("a");
  link.className = "form-download-chip";
  if (isInline) link.classList.add("is-inline");
  link.href = item.download_url || "#";
  link.target = "_blank";
  link.rel = "noopener";
  link.setAttribute(
    "aria-label",
    `Download ${item.label || item.name || "form"}`,
  );
  link.title = `Download ${item.label || item.name || "form"}`;

  const icon = document.createElement("span");
  icon.className = "material-symbols-outlined form-download-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = "picture_as_pdf";

  const text = document.createElement("span");
  text.className = "form-download-label";
  text.textContent = isInline ? "PDF" : item.label || item.name || "Form";

  link.append(icon, text);
  return link;
}

function isFormSource(source) {
  // Template form dikenali dari awalan nama file "Form" (semua dokumen kini PDF).
  return String(source || "")
    .trim()
    .toLowerCase()
    .startsWith("form");
}

function getCitationFileType(citation) {
  const source = String(citation.source || "").toLowerCase();
  if (source.endsWith(".pdf")) return "pdf";
  if (source.endsWith(".doc") || source.endsWith(".docx")) return "doc";
  if (source.endsWith(".txt")) return "txt";
  return "file";
}

function getCitationIcon(fileType) {
  if (fileType === "pdf") return "picture_as_pdf";
  if (fileType === "doc") return "article";
  if (fileType === "txt") return "text_snippet";
  return "description";
}

function formatCitationLocation(citation) {
  return (
    [
      citation.section || null,
      citation.page ? `PDF halaman ${citation.page}` : null,
    ]
      .filter(Boolean)
      .join(" - ") || "Lokasi tidak tersedia"
  );
}

function formatCitationLabel(citation, index) {
  return `Sumber ${citation.id || index + 1}: ${
    citation.source || "Unknown source"
  } - ${formatCitationLocation(citation)}`;
}

function formatMessage(content, citations = [], formDownloads = []) {
  const wrapper = document.createElement("div");
  const lines = String(content).split(/\r?\n/);
  const citationMap = buildCitationMap(citations);
  let list = null;
  let listType = null;

  const appendListItem = (tag, text, startNumber) => {
    if (!list || listType !== tag) {
      list = document.createElement(tag);
      list.className = "message-list";
      if (tag === "ol" && startNumber > 1) list.start = startNumber;
      wrapper.appendChild(list);
      listType = tag;
    }
    const item = document.createElement("li");
    appendFormattedText(item, text, citationMap, formDownloads);
    list.appendChild(item);
  };

  for (let index = 0; index < lines.length; index += 1) {
    const tableRange = getMarkdownTableRange(lines, index);
    if (tableRange) {
      list = null;
      listType = null;
      wrapper.appendChild(
        createMarkdownTable(
          lines.slice(tableRange.start, tableRange.end),
          citationMap,
          formDownloads,
        ),
      );
      index = tableRange.end - 1;
      continue;
    }

    const value = lines[index].trim();
    if (!value) {
      list = null;
      listType = null;
      continue;
    }

    const heading = value.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      list = null;
      listType = null;
      const element = document.createElement(
        heading[1].length <= 2 ? "h3" : "h4",
      );
      element.className = "message-heading";
      appendFormattedText(
        element,
        heading[2].trim(),
        citationMap,
        formDownloads,
      );
      wrapper.appendChild(element);
      continue;
    }

    const ordered = value.match(/^(\d+)[.)]\s+(.*)$/);
    if (ordered) {
      appendListItem("ol", ordered[2].trim(), Number(ordered[1]) || 1);
      continue;
    }

    const bullet = value.match(/^[-*•]\s+(.*)$/);
    if (bullet) {
      appendListItem("ul", bullet[1].trim());
      continue;
    }

    list = null;
    listType = null;
    const paragraph = document.createElement("p");
    appendFormattedText(paragraph, value, citationMap, formDownloads);
    wrapper.appendChild(paragraph);
  }
  return wrapper;
}

function getMarkdownTableRange(lines, start) {
  if (!isMarkdownTableRow(lines[start])) return null;
  if (!isMarkdownTableSeparator(lines[start + 1] || "")) return null;

  let end = start + 2;
  while (end < lines.length && isMarkdownTableRow(lines[end])) {
    end += 1;
  }

  return end > start + 2 ? { start, end } : null;
}

function isMarkdownTableRow(line) {
  const value = String(line || "").trim();
  return (
    value.startsWith("|") && value.endsWith("|") && value.split("|").length > 3
  );
}

function isMarkdownTableSeparator(line) {
  const cells = splitMarkdownTableRow(line);
  return (
    cells.length > 1 &&
    cells.every((cell) => /^:?-{3,}:?$/.test(cell.replace(/\s/g, "")))
  );
}

function splitMarkdownTableRow(line) {
  return String(line || "")
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function createMarkdownTable(lines, citationMap, formDownloads = []) {
  const wrapper = document.createElement("div");
  wrapper.className = "message-table-wrap";
  const table = document.createElement("table");
  table.className = "message-table";
  const headerCells = splitMarkdownTableRow(lines[0]);
  const bodyRows = lines.slice(2).map(splitMarkdownTableRow);
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  headerCells.forEach((cell) => {
    const th = document.createElement("th");
    appendFormattedText(th, cell, citationMap, formDownloads);
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  bodyRows.forEach((row) => {
    const tr = document.createElement("tr");
    headerCells.forEach((_, cellIndex) => {
      const td = document.createElement("td");
      appendFormattedText(td, row[cellIndex] || "", citationMap, formDownloads);
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  wrapper.appendChild(table);
  return wrapper;
}

function buildCitationMap(citations) {
  const entries = Array.isArray(citations) ? citations : [];
  return new Map(
    entries.map((citation, index) => [
      String(citation.id || index + 1),
      { citation, index },
    ]),
  );
}

function sanitizeMarkdownEmphasis(text) {
  const preservedNestedSegments = [];
  const value = String(text).replace(
    /\*\*[^*\n]*\*[^*\n]+\*[^*\n]*\*\*/g,
    (match) => {
      const token = `__MD_NESTED_${preservedNestedSegments.length}__`;
      preservedNestedSegments.push(match);
      return token;
    },
  );

  return value
    .replace(/(^|[\s(])\*\*\*([^*\n]+?)\*\*\*(?=$|[\s.,;:!?)]|$)/g, "$1**$2**")
    .replace(/(^|[\s(])\*([^*\n]+?)\*\*\*(?=$|[\s.,;:!?)]|$)/g, "$1**$2**")
    .replace(/(^|[\s(])\*\*\*([^*\n]+?)\*(?=$|[\s.,;:!?)]|$)/g, "$1**$2**")
    .replace(/__MD_NESTED_(\d+)__/g, (_, index) => {
      return preservedNestedSegments[Number(index)] || "";
    });
}

function appendFormattedText(container, text, citationMap, formDownloads = []) {
  const safeText = sanitizeMarkdownEmphasis(text);
  const formMatches = findFormDownloadMatches(safeText, formDownloads);
  const tokenPattern =
    /(\[(\d+)\]|\*\*([^*\n]*?)\*([^*\n]+?)\*([^*\n]*?)\*\*|\*\*([^*]+)\*\*|\*([^*\s][^*]*?)\*)/g;
  let cursor = 0;
  let match = tokenPattern.exec(safeText);

  while (match) {
    if (match.index > cursor) {
      appendTextWithFormChips(
        container,
        safeText.slice(cursor, match.index),
        cursor,
        formMatches,
      );
    }

    if (match[2]) {
      const citationEntry = citationMap.get(match[2]);
      if (citationEntry) {
        container.append(
          createCitationChip(citationEntry.citation, citationEntry.index, true),
        );
      } else {
        container.append(document.createTextNode(match[0]));
      }
    } else if (match[4] !== undefined) {
      const strong = document.createElement("strong");
      const leadingText = match[3] || "";
      const emphasizedText = match[4] || "";
      const trailingText = match[5] || "";
      let strongOffset = match.index + 2;
      appendTextWithFormChips(
        strong,
        leadingText,
        strongOffset,
        formMatches,
      );
      strongOffset += leadingText.length + 1;
      const emphasis = document.createElement("em");
      appendTextWithFormChips(
        emphasis,
        emphasizedText,
        strongOffset,
        formMatches,
      );
      strong.append(emphasis);
      strongOffset += emphasizedText.length + 1;
      appendTextWithFormChips(strong, trailingText, strongOffset, formMatches);
      container.append(strong);
    } else if (match[6]) {
      const strong = document.createElement("strong");
      appendTextWithFormChips(strong, match[6], match.index + 2, formMatches);
      container.append(strong);
    } else if (match[7]) {
      const emphasis = document.createElement("em");
      appendTextWithFormChips(emphasis, match[7], match.index + 1, formMatches);
      container.append(emphasis);
    }

    cursor = tokenPattern.lastIndex;
    match = tokenPattern.exec(safeText);
  }

  if (cursor < safeText.length) {
    appendTextWithFormChips(
      container,
      safeText.slice(cursor),
      cursor,
      formMatches,
    );
  }
}

function findFormDownloadMatches() {
  // Form downloads always render in the bottom "Form yang bisa diunduh" block.
  // Returning no matches keeps them out of the answer text so their placement is
  // consistent regardless of whether the answer happens to use the word "form".
  return [];
}

function appendTextWithFormChips(container, text, offset, formMatches) {
  const segmentStart = offset;
  const segmentEnd = offset + text.length;
  const matches = formMatches.filter(
    (match) => match.start >= segmentStart && match.end <= segmentEnd,
  );

  if (!matches.length) {
    container.append(document.createTextNode(text));
    return;
  }

  let cursor = 0;
  matches.forEach((match) => {
    const localStart = match.start - segmentStart;
    const localEnd = match.end - segmentStart;
    if (localStart > cursor) {
      container.append(document.createTextNode(text.slice(cursor, localStart)));
    }
    container.append(document.createTextNode(text.slice(localStart, localEnd)));
    const group = document.createElement("span");
    group.className = "form-download-inline-group";
    match.items.forEach((item) => {
      group.appendChild(createFormDownloadChip(item, true));
    });
    container.append(group);
    cursor = localEnd;
  });

  if (cursor < text.length) {
    container.append(document.createTextNode(text.slice(cursor)));
  }
}

function formatDuration(milliseconds) {
  if (milliseconds < 1000) return `${milliseconds} ms`;
  if (milliseconds < 60000) return `${(milliseconds / 1000).toFixed(1)}s`;

  const minutes = Math.floor(milliseconds / 60000);
  const seconds = Math.round((milliseconds % 60000) / 1000);
  return `${minutes}m ${seconds}s`;
}

function updateComposer() {
  const isMobile = window.matchMedia(MOBILE_QUERY).matches;
  elements.chatInput.disabled = false;
  elements.sendButton.disabled = false;
  elements.newChatButton.disabled = state.isSubmitting;
  elements.sendButton.textContent = state.isSubmitting ? "stop" : "send";
  elements.sendButton.setAttribute(
    "aria-label",
    state.isSubmitting ? "Stop response" : "Send message",
  );
  elements.sendButton.classList.toggle("is-stopping", state.isSubmitting);
  elements.chatInput.placeholder = state.isSubmitting
    ? "Type your next question..."
    : isMobile
      ? "Ask about HR docs..."
      : "Ask about HR SOPs, onboarding, travel, or internal documents...";
}

function renderFaqs() {
  elements.faqList.innerHTML = "";
  state.faqItems.forEach((item) => {
    const fragment = elements.faqTemplate.content.cloneNode(true);
    const container = fragment.querySelector(".faq-item");
    const trigger = fragment.querySelector(".faq-trigger");
    const source = fragment.querySelector(".faq-source");
    const askButton = fragment.querySelector(".faq-ask");
    const editButton = fragment.querySelector(".faq-edit");
    const deleteButton = fragment.querySelector(".faq-delete");
    const citationContainer = fragment.querySelector(".faq-citations");
    const citations = getFaqCitations(item);
    fragment.querySelector(".faq-question").textContent = item.question;
    fragment
      .querySelector(".faq-answer")
      .appendChild(formatMessage(stripCitationMarkers(item.answer)));
    if (item.image_url) {
      const image = document.createElement("img");
      image.className = "faq-answer-image";
      image.src = item.image_url;
      image.alt = item.question;
      image.loading = "lazy";
      fragment.querySelector(".faq-answer").after(image);
      askButton.hidden = true;
      if (isAdminSession()) {
        const actions = fragment.querySelector(".faq-actions");
        const fileInput = document.createElement("input");
        fileInput.type = "file";
        fileInput.accept = "image/webp,image/png,image/jpeg";
        fileInput.hidden = true;
        const changeButton = document.createElement("button");
        changeButton.type = "button";
        changeButton.className = "faq-ask";
        changeButton.textContent = "Ganti gambar";
        changeButton.addEventListener("click", () => fileInput.click());
        fileInput.addEventListener("change", () => {
          uploadPinnedFaqImage(fileInput.files && fileInput.files[0]);
        });
        actions.append(changeButton, fileInput);
      }
    }
    if (citations.length) {
      renderFaqCitations(citationContainer, citations);
      source.hidden = true;
    } else if (item.source) {
      source.textContent = item.source;
      if (item.source_url && isAdminSession()) {
        source.href = item.source_url;
        source.addEventListener("click", (event) => {
          event.preventDefault();
          downloadDocument(item.source_url, item.source);
        });
      } else {
        source.removeAttribute("href");
        source.removeAttribute("target");
        source.removeAttribute("rel");
      }
    } else {
      source.hidden = true;
      source.removeAttribute("href");
      source.removeAttribute("target");
      source.removeAttribute("rel");
    }
    trigger.addEventListener("click", () => {
      const isOpen = container.classList.toggle("is-open");
      trigger.setAttribute("aria-expanded", String(isOpen));
    });
    askButton.addEventListener("click", () => {
      if (!hasFaqEvidence(item)) {
        openDocumentErrorModal(
          "FAQ ini belum punya sumber dari dokumen terindeks, jadi belum bisa dipakai untuk bertanya di chat.",
          [],
          "FAQ tidak ada sumbernya",
        );
        return;
      }
      elements.chatInput.value = item.suggested_query || item.question;
      navigateTo("chat");
      window.setTimeout(() => elements.chatInput.focus(), 0);
    });
    if (item.id) {
      editButton.addEventListener("click", () => startFaqEdit(item));
      deleteButton.addEventListener("click", () => deleteFaq(item));
    } else {
      editButton.hidden = true;
      deleteButton.hidden = true;
    }
    elements.faqList.appendChild(fragment);
  });
  updateFaqControls();
}

async function uploadPinnedFaqImage(file) {
  if (!file || !isAdminSession()) return;
  showFaqStatus("Mengunggah gambar...");
  try {
    const response = await fetch("/api/admin/faq-image", {
      method: "POST",
      headers: adminAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        filename: file.name,
        content_base64: await fileToBase64(file),
      }),
    });
    const payload = await readJsonResponse(response);
    if (!response.ok)
      throw new Error(
        formatApiError(payload.detail, "Gagal mengunggah gambar."),
      );
    showFaqStatus("Gambar FAQ diperbarui.");
    await loadFaqs();
  } catch (error) {
    showFaqStatus(error.message || "Gagal mengunggah gambar.", true);
  }
}

function stripCitationMarkers(value) {
  return String(value)
    .replace(/\s*\[(\d+)\]/g, "")
    .replace(/\s+([.,;:!?])/g, "$1")
    .trim();
}

async function loadFaqs() {
  try {
    const response = await fetch("/api/faq");
    if (!response.ok) {
      state.faqItems = [];
      renderFaqs();
      return;
    }

    const items = await response.json();
    if (!Array.isArray(items) || items.length === 0) {
      state.faqItems = [];
      renderFaqs();
      return;
    }

    state.faqItems = items
      .filter((item) => item.question && item.answer)
      .map(normalizeFaq);
    renderFaqs();
  } catch (error) {
    state.faqItems = [];
    renderFaqs();
    console.warn("Unable to load FAQ", error);
  }
}

function normalizeFaq(item) {
  return {
    id: item.id || "",
    question: item.question,
    answer: item.answer,
    source: item.source || "",
    source_url: item.source_url || "",
    suggested_query: item.suggested_query || item.question,
    citations: Array.isArray(item.citations) ? item.citations : [],
    image_url: item.image_url || "",
  };
}

function getFaqCitations(item) {
  if (Array.isArray(item.citations) && item.citations.length) {
    return item.citations;
  }
  if (!item.source) return [];
  return [
    {
      id: 1,
      source: item.source,
      download_url: item.source_url || "",
    },
  ];
}

function hasFaqEvidence(item) {
  return getFaqCitations(item).length > 0;
}

function renderFaqCitations(container, citations) {
  const list = document.createElement("div");
  list.className = "faq-citation-list";
  citations.forEach((citation) => {
    const canOpenDocument = Boolean(citation.download_url) && isAdminSession();
    const source = canOpenDocument
      ? document.createElement("a")
      : document.createElement("span");
    source.className = "faq-citation-link";
    source.textContent = formatCitationText(citation);
    if (canOpenDocument) {
      source.href = citation.download_url;
      source.target = "_blank";
      source.rel = "noopener";
      source.addEventListener("click", (event) => {
        event.preventDefault();
        downloadDocument(citation.download_url, citation.source);
      });
    }
    list.appendChild(source);
  });
  container.appendChild(list);
  container.hidden = false;
}

function formatCitationText(citation) {
  return [
    citation.source || "Unknown source",
    citation.section || null,
    citation.page ? `PDF halaman ${citation.page}` : null,
  ]
    .filter(Boolean)
    .join(" - ");
}

function bindAdminFaqs() {
  elements.faqForm.addEventListener("submit", saveFaq);
  if (elements.faqStopButton) {
    elements.faqStopButton.addEventListener("click", cancelFaqGeneration);
  }
}

function showFaqStop() {
  if (!elements.faqStopButton) return;
  elements.faqStopButton.hidden = false;
  elements.faqStopButton.disabled = false;
}

function hideFaqStop() {
  if (elements.faqStopButton) elements.faqStopButton.hidden = true;
}

// Deletes a FAQ in the background without touching the UI. Used to roll back a
// generation the admin cancelled while the request was still in flight.
function discardFaqSilently(faqId) {
  if (!faqId) return;
  fetch(`/api/admin/faq/${encodeURIComponent(faqId)}`, {
    method: "DELETE",
    headers: adminAuthHeaders(),
  }).catch(() => {});
}

function cancelFaqGeneration() {
  const generation = state.activeFaqGeneration;
  if (!generation || !state.isMutatingFaq) return;
  // Mark this generation as cancelled; when its request resolves it will roll
  // back any FAQ the server already created instead of updating the UI.
  generation.cancelled = true;
  state.activeFaqGeneration = null;
  state.isMutatingFaq = false;
  hideFaqStop();
  resetFaqForm(false);
  showFaqStatus("Generate dibatalkan.");
  updateFaqControls();
}

async function saveFaq(event) {
  event.preventDefault();
  if (
    !isAdminSession() ||
    state.isMutatingFaq ||
    state.needsReindex ||
    state.isReindexing
  ) {
    if (state.needsReindex || state.isReindexing) {
      showFaqStatus("Rebuild embeddings dulu sebelum mengubah FAQ.", true);
    }
    return;
  }

  const faqId = elements.faqIdInput.value;
  const payload = {
    question: elements.faqQuestionInput.value.trim(),
  };
  if (!payload.question) {
    showFaqStatus("Pertanyaan wajib diisi.", true);
    return;
  }

  const generation = { cancelled: false };
  state.activeFaqGeneration = generation;
  state.isMutatingFaq = true;
  updateFaqControls();
  showFaqStop();
  showFaqStatus(
    faqId ? "Regenerating FAQ answer..." : "Generating FAQ answer...",
  );

  try {
    const response = await fetch(
      faqId ? `/api/admin/faq/${encodeURIComponent(faqId)}` : "/api/admin/faq",
      {
        method: faqId ? "PUT" : "POST",
        headers: adminAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      },
    );
    const responsePayload = await readJsonResponse(response);

    // Admin cancelled while this request was in flight: roll back any FAQ the
    // server created and leave the UI (already reset by cancel) untouched.
    if (generation.cancelled) {
      if (response.ok && !faqId && responsePayload.item?.id) {
        discardFaqSilently(responsePayload.item.id);
      }
      return;
    }

    if (!response.ok) {
      const failure = new Error(
        formatApiError(responsePayload.detail, "FAQ update failed."),
      );
      failure.status = response.status;
      throw failure;
    }
    if (
      responsePayload.item &&
      !hasFaqEvidence(normalizeFaq(responsePayload.item))
    ) {
      throw new Error(
        "FAQ tidak disimpan karena tidak ada sumber dari dokumen terindeks.",
      );
    }

    showFaqStatus(responsePayload.message || "FAQ saved.");
    resetFaqForm(false);
    await loadFaqs();
  } catch (error) {
    if (generation.cancelled) return;
    const message = formatFaqSaveError(error);
    showFaqStatus("FAQ tidak disimpan.", true);
    openDocumentErrorModal(
      message,
      [],
      faqId ? "FAQ tidak diupdate" : "FAQ tidak dibuat",
    );
  } finally {
    // Only clear state if this generation is still the active one; a cancel (or
    // a newer generation) has already reset it otherwise.
    if (state.activeFaqGeneration === generation) {
      state.activeFaqGeneration = null;
      state.isMutatingFaq = false;
      hideFaqStop();
      updateFaqControls();
    }
  }
}

function formatFaqSaveError(error) {
  const status = Number(error?.status) || 0;
  const rawMessage = String(error?.message || "").trim();

  // 422: backend sudah memvalidasi bahwa pertanyaan tidak punya sumber
  // relevan di dokumen terindeks (mis. pertanyaan di luar topik).
  if (status === 422) {
    return "FAQ tidak dibuat karena pertanyaan ini tidak punya sumber yang relevan di dokumen terindeks. Coba pertanyaan lain atau tambahkan dokumen terkait.";
  }

  // 5xx: layanan AI lokal (Ollama) mati atau gagal membuat jawaban.
  if (status >= 500) {
    console.warn("FAQ generation detail:", rawMessage);
    return "FAQ belum bisa dibuat karena layanan AI (Ollama) gagal merespons. Pastikan Ollama berjalan lalu coba lagi.";
  }

  // Error dari sisi klien (tanpa status HTTP) — fallback ke isi pesannya.
  if (!rawMessage) {
    return "FAQ belum bisa dibuat. Coba lagi sebentar lagi.";
  }
  const noSourcePatterns = [
    /tidak ada sumber/i,
    /belum punya sumber/i,
    /tidak tersedia dalam dokumen/i,
    /tidak ditemukan dalam dokumen/i,
    /citation/i,
    /evidence/i,
  ];
  if (noSourcePatterns.some((pattern) => pattern.test(rawMessage))) {
    return "FAQ tidak dibuat karena tidak ada sumber yang relevan di dokumen terindeks.";
  }

  return rawMessage;
}

function startFaqEdit(item) {
  if (
    !isAdminSession() ||
    state.isMutatingFaq ||
    state.needsReindex ||
    state.isReindexing
  )
    return;
  hideFaqStop();
  state.editingFaqId = item.id;
  elements.faqIdInput.value = item.id;
  elements.faqQuestionInput.value = item.question;
  elements.faqSubmitButton.textContent = "Regenerate FAQ";
  showFaqStatus("Editing FAQ item.");
  elements.faqQuestionInput.focus();
  elements.faqForm.scrollIntoView({ behavior: "smooth", block: "center" });
}

async function deleteFaq(item) {
  if (
    !isAdminSession() ||
    state.isMutatingFaq ||
    state.needsReindex ||
    state.isReindexing ||
    !item.id
  )
    return;
  const confirmed = window.confirm(`Delete FAQ "${item.question}"?`);
  if (!confirmed) return;

  state.isMutatingFaq = true;
  updateFaqControls();
  showFaqStatus("Deleting FAQ...");

  try {
    const response = await fetch(
      `/api/admin/faq/${encodeURIComponent(item.id)}`,
      {
        method: "DELETE",
        headers: adminAuthHeaders(),
      },
    );
    const payload = await readJsonResponse(response);
    if (!response.ok)
      throw new Error(formatApiError(payload.detail, "FAQ delete failed."));
    showFaqStatus(payload.message || "FAQ deleted.");
    if (state.editingFaqId === item.id) resetFaqForm(false);
    await loadFaqs();
  } catch (error) {
    showFaqStatus(error.message || "FAQ delete failed.", true);
  } finally {
    state.isMutatingFaq = false;
    updateFaqControls();
  }
}

function resetFaqForm(clearStatus = true) {
  state.editingFaqId = "";
  elements.faqForm.reset();
  elements.faqIdInput.value = "";
  elements.faqSubmitButton.textContent = "Generate FAQ";
  if (clearStatus) clearFaqStatus();
}

function updateFaqControls() {
  const isLocked =
    state.isMutatingFaq || state.needsReindex || state.isReindexing;
  elements.body.dataset.faqState = state.isMutatingFaq ? "running" : "idle";
  elements.faqSubmitButton.disabled = isLocked;
  // The stop button must stay clickable while a generation is running so the
  // admin can actually cancel it.
  if (elements.faqStopButton)
    elements.faqStopButton.disabled = !state.isMutatingFaq;
  elements.faqQuestionInput.disabled = isLocked;
  elements.faqList
    .querySelectorAll(".faq-edit, .faq-delete")
    .forEach((button) => {
      button.disabled = isLocked;
    });
}

function showFaqStatus(message, isError = false) {
  elements.faqStatus.textContent = message;
  elements.faqStatus.classList.toggle("is-error", isError);
}

function clearFaqStatus() {
  elements.faqStatus.textContent = "";
  elements.faqStatus.classList.remove("is-error");
}

function bindPolicyActions() {
  elements.filterButton.addEventListener("click", () => {
    elements.policySearchWrap.classList.toggle("is-visible");
    if (elements.policySearchWrap.classList.contains("is-visible"))
      elements.librarySearch.focus();
  });
  elements.librarySearch.addEventListener("input", () => {
    state.filter = elements.librarySearch.value.trim().toLowerCase();
    renderLibrary();
  });
  elements.chatLink.addEventListener("click", () => navigateTo("chat"));
}

function bindAuth() {
  elements.accountAvatar.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleAccountPopover();
  });
  elements.accountActionButton.addEventListener("click", (event) => {
    event.stopPropagation();
    closeAccountPopover();
    if (state.session.role === "admin") {
      openLogoutModal();
      return;
    }
    openAuthModal();
  });

  elements.authCloseButton.addEventListener("click", closeAuthModal);
  elements.authModal.addEventListener("click", (event) => {
    if (event.target === elements.authModal) closeAuthModal();
  });
  elements.logoutCancelButton.addEventListener("click", closeLogoutModal);
  elements.logoutConfirmButton.addEventListener("click", logoutAdmin);
  elements.logoutModal.addEventListener("click", (event) => {
    if (event.target === elements.logoutModal) closeLogoutModal();
  });
  elements.formFillCloseButton.addEventListener("click", closeFormFillModal);
  elements.formFillForm.addEventListener("submit", submitFormFill);
  elements.formFillModal.addEventListener("click", (event) => {
    if (event.target === elements.formFillModal) closeFormFillModal();
  });
  elements.documentErrorCloseButton.addEventListener(
    "click",
    closeDocumentErrorModal,
  );
  elements.documentErrorModal.addEventListener("click", (event) => {
    if (event.target === elements.documentErrorModal) closeDocumentErrorModal();
  });
  elements.authForm.addEventListener("submit", handleAdminLogin);
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    closeAccountPopover();
    if (elements.authModal.classList.contains("is-open")) closeAuthModal();
    if (elements.logoutModal.classList.contains("is-open")) closeLogoutModal();
    if (elements.documentErrorModal.classList.contains("is-open")) {
      closeDocumentErrorModal();
    }
    if (elements.formFillModal.classList.contains("is-open")) {
      closeFormFillModal();
    }
  });
  document.addEventListener("click", (event) => {
    if (elements.accountPanel.contains(event.target)) return;
    closeAccountPopover();
  });
}

function toggleAccountPopover() {
  if (elements.accountPopover.hidden) {
    openAccountPopover();
    return;
  }
  closeAccountPopover();
}

function openAccountPopover() {
  elements.accountPopover.hidden = false;
  elements.accountAvatar.setAttribute("aria-expanded", "true");
}

function closeAccountPopover() {
  elements.accountPopover.hidden = true;
  elements.accountAvatar.setAttribute("aria-expanded", "false");
}

function openAuthModal() {
  closeAccountPopover();
  clearAuthError();
  elements.authForm.reset();
  elements.authModal.classList.add("is-open");
  elements.authModal.setAttribute("aria-hidden", "false");
  elements.body.classList.add("auth-open");
  window.setTimeout(() => elements.adminEmail.focus(), 0);
}

function closeAuthModal() {
  elements.authModal.classList.remove("is-open");
  elements.authModal.setAttribute("aria-hidden", "true");
  elements.body.classList.remove("auth-open");
  clearAuthError();
}

function openLogoutModal() {
  closeAccountPopover();
  elements.logoutModal.classList.add("is-open");
  elements.logoutModal.setAttribute("aria-hidden", "false");
  elements.body.classList.add("logout-open");
  window.setTimeout(() => elements.logoutCancelButton.focus(), 0);
}

function closeLogoutModal() {
  elements.logoutModal.classList.remove("is-open");
  elements.logoutModal.setAttribute("aria-hidden", "true");
  elements.body.classList.remove("logout-open");
}

function openDocumentErrorModal(
  summary,
  failures = [],
  title = "Upload belum selesai",
) {
  elements.documentErrorTitle.textContent = title;
  elements.documentErrorSummary.textContent = summary;
  elements.documentErrorList.innerHTML = "";
  failures.forEach((failure) => {
    const item = document.createElement("li");
    const name = document.createElement("strong");
    name.textContent = failure.name || "Document";
    const reason = document.createElement("span");
    reason.textContent = failure.reason || "Upload failed.";
    item.append(name, reason);
    elements.documentErrorList.appendChild(item);
  });
  elements.documentErrorModal.classList.add("is-open");
  elements.documentErrorModal.setAttribute("aria-hidden", "false");
  elements.body.classList.add("document-error-open");
  window.setTimeout(() => elements.documentErrorCloseButton.focus(), 0);
}

function closeDocumentErrorModal() {
  elements.documentErrorModal.classList.remove("is-open");
  elements.documentErrorModal.setAttribute("aria-hidden", "true");
  elements.body.classList.remove("document-error-open");
}

async function handleAdminLogin(event) {
  event.preventDefault();
  const email = elements.adminEmail.value.trim().toLowerCase();
  const password = elements.adminPassword.value;

  try {
    const response = await fetch("/api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const payload = await readJsonResponse(response);
    if (!response.ok) {
      throw new Error(
        formatApiError(
          payload.detail,
          "Email atau password admin belum cocok.",
        ),
      );
    }

    state.session = {
      role: "admin",
      email: payload.email || email,
      name: payload.name || "Admin",
      token: payload.token || "",
      expires_at: payload.expires_at || "",
    };
    if (!isAdminSession()) {
      throw new Error("Sesi admin tidak valid. Coba login ulang.");
    }
  } catch (error) {
    showAuthError(error.message || "Email atau password admin belum cocok.");
    elements.adminPassword.select();
    return;
  }

  window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(state.session));
  syncAuth();
  closeAuthModal();
  closeMobileNav();
}

function logoutAdmin() {
  state.session = {
    role: "guest",
    email: "",
    name: "Guest",
    token: "",
    expires_at: "",
  };
  clearDocumentUndo();
  window.localStorage.removeItem(AUTH_STORAGE_KEY);
  closeLogoutModal();
  syncAuth();
}

function syncAuth() {
  const isAdmin = isAdminSession();
  if (!isAdmin && state.session.role === "admin") {
    state.session = {
      role: "guest",
      email: "",
      name: "Guest",
      token: "",
      expires_at: "",
    };
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
  }
  elements.body.dataset.role = isAdmin ? "admin" : "guest";
  elements.accountAvatar.textContent = isAdmin ? "A" : "G";
  elements.accountRoleLabel.textContent = isAdmin
    ? "Admin mode"
    : "Guest access";
  elements.accountName.textContent = isAdmin
    ? state.session.name || state.session.email
    : "Guest";
  elements.accountHint.textContent = isAdmin ? "Admin" : "Login admin";
  elements.accountPopoverRole.textContent = isAdmin
    ? "Admin mode"
    : "Guest access";
  elements.accountPopoverName.textContent = isAdmin
    ? state.session.email || state.session.name
    : "Guest";
  elements.accountPopoverHint.textContent = isAdmin
    ? "Klik ikon kanan untuk logout."
    : "Klik ikon kanan untuk login admin.";
  elements.accountActionIcon.textContent = isAdmin ? "logout" : "login";
  elements.accountActionText.textContent = isAdmin ? "Logout" : "Admin login";
  elements.accountActionButton.setAttribute(
    "aria-label",
    isAdmin ? "Logout admin" : "Login admin",
  );
  if (elements.policyNavLink) elements.policyNavLink.hidden = !isAdmin;
  if (!isAdmin && state.activeScreen === "policy") navigateTo("chat");
  if (!isAdmin) resetFaqForm();
  clearDocumentStatus();
  syncReindexState();
  updateFaqControls();
  if (isAdmin) {
    void loadLibrary();
  } else {
    state.documents = [];
    renderLibrary();
  }
}

function showAuthError(message) {
  elements.authError.textContent = message;
  elements.authError.hidden = false;
}

function clearAuthError() {
  elements.authError.textContent = "";
  elements.authError.hidden = true;
}

function bindAdminDocuments() {
  elements.documentFileInput.addEventListener("change", () => {
    const files = Array.from(elements.documentFileInput.files || []);
    elements.documentFileLabel.textContent = formatSelectedFiles(files);
    clearDocumentStatus();
  });

  elements.adminDocumentForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const files = Array.from(elements.documentFileInput.files || []);
    if (!files.length) {
      showDocumentStatus("Pilih dokumen dulu.", true);
      return;
    }
    await saveDocuments(files);
    elements.adminDocumentForm.reset();
    elements.documentFileLabel.textContent = "Choose files";
  });

  elements.documentReplaceInput.addEventListener("change", async () => {
    const file = elements.documentReplaceInput.files?.[0];
    if (!file || !state.pendingReplacePath) return;
    await saveDocument(file, state.pendingReplacePath);
    elements.documentReplaceInput.value = "";
    state.pendingReplacePath = "";
  });

  elements.documentReindexButton.addEventListener("click", rebuildEmbeddings);
  elements.documentUndoButton.addEventListener("click", undoDocumentChange);
}

async function saveDocuments(files) {
  if (!isAdminSession() || state.isMutatingDocument || state.isReindexing)
    return;
  state.isMutatingDocument = true;
  updateDocumentControls();

  let successCount = 0;
  let embeddableCount = 0;
  const failures = [];
  const insertedItems = [];
  for (const [index, file] of files.entries()) {
    showDocumentStatus(`Uploading ${index + 1}/${files.length}: ${file.name}`);
    try {
      const payload = await saveDocumentRequest(file);
      successCount += 1;
      if (payload.item) insertedItems.push(payload.item);
      if (payload.requires_reindex) embeddableCount += 1;
    } catch (error) {
      failures.push({
        name: file.name,
        reason: error.message || "Upload failed.",
      });
    }
  }

  state.isMutatingDocument = false;
  await loadLibrary();

  if (failures.length) {
    if (insertedItems.length) {
      pushDocumentChange({
        type: "insert",
        label: `Undo insert ${insertedItems.length} file${insertedItems.length === 1 ? "" : "s"}`,
        items: insertedItems,
        requires_reindex: embeddableCount > 0,
      });
    }
    const summary = `${successCount} uploaded, ${failures.length} failed.`;
    showDocumentStatus(summary, true);
    openDocumentErrorModal(summary, failures);
    if (embeddableCount > 0) markReindexRequired();
    updateDocumentControls();
    return;
  }
  if (embeddableCount > 0) {
    pushDocumentChange({
      type: "insert",
      label: `Undo insert ${successCount} file${successCount === 1 ? "" : "s"}`,
      items: insertedItems,
      requires_reindex: true,
    });
    markReindexRequired(
      `${embeddableCount} dokumen knowledge diperbarui. Rebuild embeddings sebelum lanjut.`,
    );
  } else if (successCount > 0) {
    pushDocumentChange({
      type: "insert",
      label: `Undo insert ${successCount} file${successCount === 1 ? "" : "s"}`,
      items: insertedItems,
      requires_reindex: false,
    });
    showDocumentStatus(
      `${successCount} file berhasil diunggah. Tidak perlu rebuild embeddings.`,
    );
  }
  updateDocumentControls();
}

async function saveDocument(file, replacePath = "") {
  if (!isAdminSession() || state.isMutatingDocument || state.isReindexing)
    return;
  state.isMutatingDocument = true;
  updateDocumentControls();
  showDocumentStatus(
    replacePath ? "Updating document..." : "Uploading document...",
  );

  try {
    const previousSnapshot = replacePath
      ? await createDocumentSnapshot(findDocumentByPath(replacePath))
      : null;
    const payload = await saveDocumentRequest(file, replacePath);
    await loadLibrary();
    if (payload.requires_reindex) {
      pushDocumentChange({
        type: replacePath ? "update" : "insert",
        label: replacePath ? "Undo update file" : "Undo insert file",
        item: payload.item,
        previous: previousSnapshot,
        requires_reindex: true,
      });
      markReindexRequired(
        `${payload.message || "Document saved."} Rebuild embeddings sebelum lanjut.`,
      );
    } else {
      pushDocumentChange({
        type: replacePath ? "update" : "insert",
        label: replacePath ? "Undo update file" : "Undo insert file",
        item: payload.item,
        previous: previousSnapshot,
        requires_reindex: false,
      });
      showDocumentStatus(
        `${payload.message || "File saved."} Tidak perlu rebuild embeddings.`,
      );
    }
  } catch (error) {
    showDocumentStatus(error.message || "Document update failed.", true);
  } finally {
    state.isMutatingDocument = false;
    updateDocumentControls();
  }
}

async function saveDocumentRequest(file, replacePath = "") {
  return saveDocumentPayload({
    filename: file.name,
    content_base64: await fileToBase64(file),
    replace_path: replacePath || null,
  });
}

async function saveDocumentPayload(body) {
  const response = await fetch("/api/admin/documents", {
    method: "POST",
    headers: adminAuthHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  const payload = await readJsonResponse(response);
  if (!response.ok) {
    throw new Error(payload.detail || "Document update failed.");
  }
  return payload;
}

async function deleteDocument(item) {
  if (!isAdminSession() || state.isMutatingDocument || state.isReindexing)
    return;

  state.isMutatingDocument = true;
  updateDocumentControls();
  showDocumentStatus("Deleting document...");

  try {
    const deletedSnapshot = await createDocumentSnapshot(item);
    const response = await fetch(
      `/api/admin/documents/${encodeURIComponent(item.relative_path)}`,
      {
        method: "DELETE",
        headers: adminAuthHeaders(),
      },
    );
    const payload = await readJsonResponse(response);
    if (!response.ok)
      throw new Error(payload.detail || "Document delete failed.");
    await loadLibrary();
    if (payload.requires_reindex) {
      pushDocumentChange({
        type: "delete",
        label: "Undo delete file",
        previous: deletedSnapshot,
        requires_reindex: true,
      });
      markReindexRequired(
        `${payload.message || "Document deleted."} Rebuild embeddings sebelum lanjut.`,
      );
    } else {
      pushDocumentChange({
        type: "delete",
        label: "Undo delete file",
        previous: deletedSnapshot,
        requires_reindex: false,
      });
      showDocumentStatus(
        `${payload.message || "File deleted."} Tidak perlu rebuild embeddings.`,
      );
    }
  } catch (error) {
    showDocumentStatus(error.message || "Document delete failed.", true);
  } finally {
    state.isMutatingDocument = false;
    updateDocumentControls();
  }
}

function startDocumentReplace(item) {
  if (!isAdminSession() || state.isMutatingDocument || state.isReindexing)
    return;
  state.pendingReplacePath = item.relative_path;
  elements.documentReplaceInput.value = "";
  elements.documentReplaceInput.click();
}

function updateDocumentControls() {
  const isLocked = state.isMutatingDocument || state.isReindexing;
  elements.documentUploadButton.disabled = isLocked;
  elements.documentFileInput.disabled = isLocked;
  elements.documentUndoButton.hidden = state.documentUndoStack.length === 0;
  elements.documentUndoButton.disabled =
    state.isMutatingDocument || state.isReindexing;
  if (state.documentUndoStack.length) {
    elements.documentUndoButton.title = `Undo ${state.documentUndoStack.length} pending document change${state.documentUndoStack.length === 1 ? "" : "s"}`;
  }
  elements.documentReindexButton.disabled =
    !isAdminSession() ||
    state.isMutatingDocument ||
    state.isReindexing ||
    !state.needsReindex;
  elements.libraryList
    .querySelectorAll(".document-update, .document-delete")
    .forEach((button) => {
      button.disabled = isLocked;
    });
}

function pushDocumentChange(undo) {
  const change = {
    id: `change-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    type: undo.type,
    label: formatDocumentChangeLabel(undo),
    requires_reindex: Boolean(undo.requires_reindex),
  };
  undo.change_id = change.id;
  state.documentUndoStack.push(undo);
  state.documentChanges.push(change);
  state.documentUndo = undo;
  updateDocumentControls();
}

function clearDocumentUndo() {
  state.documentUndoStack = [];
  state.documentChanges = [];
  state.documentUndo = null;
  updateDocumentControls();
}

function formatDocumentChangeLabel(undo) {
  const actionLabels = {
    insert: "Inserted",
    update: "Updated",
    delete: "Deleted",
  };
  const action = actionLabels[undo.type] || "Changed";
  const items = undo.items || [undo.item || undo.previous].filter(Boolean);
  if (items.length > 1) return `${action} ${items.length} files`;
  const item = items[0];
  return `${action} ${item?.display_name || item?.name || "file"}`;
}

function findDocumentByPath(relativePath) {
  return (
    state.documents.find((item) => item.relative_path === relativePath) || null
  );
}

async function createDocumentSnapshot(item) {
  if (!item?.download_url || !item.relative_path) {
    throw new Error("Snapshot dokumen gagal dibuat.");
  }
  return {
    name: item.name || item.relative_path.split("/").pop() || "document",
    relative_path: item.relative_path,
    display_name: item.display_name || item.name || "document",
    content_base64: await fetchDocumentBase64(item.download_url),
  };
}

async function fetchDocumentBase64(url) {
  const response = await fetch(url, {
    headers: adminAuthHeaders(),
  });
  if (!response.ok)
    throw new Error(`Snapshot dokumen gagal: HTTP ${response.status}`);
  return blobToBase64(await response.blob());
}

async function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      const value = String(reader.result || "");
      resolve(value.includes(",") ? value.split(",").pop() : value);
    });
    reader.addEventListener("error", () => reject(reader.error));
    reader.readAsDataURL(blob);
  });
}

async function deleteDocumentRequest(relativePath) {
  const response = await fetch(
    `/api/admin/documents/${encodeURIComponent(relativePath)}`,
    {
      method: "DELETE",
      headers: adminAuthHeaders(),
    },
  );
  const payload = await readJsonResponse(response);
  if (!response.ok && response.status !== 404) {
    throw new Error(payload.detail || "Undo delete failed.");
  }
  return payload;
}

async function restoreDocumentSnapshot(snapshot, replace = false) {
  return saveDocumentPayload({
    filename: snapshot.name,
    content_base64: snapshot.content_base64,
    replace_path: replace ? snapshot.relative_path : null,
  });
}

async function applyDocumentUndo(undo) {
  if (undo.type === "insert") {
    for (const item of [...(undo.items || [undo.item])].reverse()) {
      if (item?.relative_path) await deleteDocumentRequest(item.relative_path);
    }
    return;
  }
  if (undo.type === "delete") {
    await restoreDocumentSnapshot(undo.previous, false);
    return;
  }
  if (undo.type === "update") {
    await restoreDocumentSnapshot(undo.previous, true);
  }
}

async function undoDocumentChange() {
  const changes = [...state.documentUndoStack];
  if (
    !changes.length ||
    !isAdminSession() ||
    state.isMutatingDocument ||
    state.isReindexing
  )
    return;

  state.isMutatingDocument = true;
  updateDocumentControls();
  showDocumentStatus(
    `Undoing ${changes.length} document change${changes.length === 1 ? "" : "s"}...`,
  );

  try {
    for (const undo of changes.reverse()) {
      await applyDocumentUndo(undo);
    }

    await loadLibrary();
    const touchedEmbeddings = changes.some((undo) => undo.requires_reindex);
    state.documentUndoStack = [];
    state.documentChanges = [];
    state.documentUndo = null;
    if (touchedEmbeddings) {
      clearReindexRequired(
        "Semua perubahan dokumen dibatalkan. Embeddings kembali sesuai.",
      );
    } else {
      showDocumentStatus(
        "Semua perubahan dokumen dibatalkan. Tidak perlu rebuild embeddings.",
      );
    }
  } catch (error) {
    showDocumentStatus(error.message || "Undo dokumen gagal.", true);
  } finally {
    state.isMutatingDocument = false;
    updateDocumentControls();
  }
}

async function rebuildEmbeddings() {
  if (!isAdminSession() || state.isReindexing || !state.needsReindex) return;

  state.isReindexing = true;
  syncReindexState();
  updateDocumentControls();
  updateFaqControls();
  clearDocumentStatus();

  try {
    const response = await fetch("/api/admin/reindex", {
      method: "POST",
      headers: adminAuthHeaders(),
    });
    const payload = await readJsonResponse(response);
    if (!response.ok)
      throw new Error(payload.detail || "Rebuild embeddings failed.");
    clearReindexRequired(payload.message || "Embeddings rebuilt.");
  } catch (error) {
    showDocumentStatus(error.message || "Rebuild embeddings failed.", true);
  } finally {
    state.isReindexing = false;
    syncReindexState();
    updateDocumentControls();
    updateFaqControls();
  }
}

function markReindexRequired(
  message = "Document library changed. Rebuild embeddings before continuing.",
) {
  state.needsReindex = true;
  window.localStorage.setItem(REINDEX_STORAGE_KEY, "1");
  syncReindexState();
  showDocumentStatus(message, false);
}

function clearReindexRequired(message = "Embeddings rebuilt.") {
  state.needsReindex = false;
  clearDocumentUndo();
  window.localStorage.removeItem(REINDEX_STORAGE_KEY);
  syncReindexState();
  showDocumentStatus(message, false);
}

function syncReindexState() {
  elements.body.dataset.reindexState = state.isReindexing
    ? "running"
    : state.needsReindex
      ? "required"
      : "clean";
  if (!isAdminSession()) return;
  if (state.isReindexing) {
    clearDocumentStatus();
  } else if (state.needsReindex && !elements.adminDocumentStatus.textContent) {
    showDocumentStatus(
      "Document library changed. Rebuild embeddings before continuing.",
    );
  }
}

function showDocumentStatus(message, isError = false) {
  elements.adminDocumentStatus.textContent = message;
  elements.adminDocumentStatus.classList.toggle("is-error", isError);
}

function clearDocumentStatus() {
  elements.adminDocumentStatus.textContent = "";
  elements.adminDocumentStatus.classList.remove("is-error");
}

function isAdminSession() {
  return (
    state.session.role === "admin" &&
    Boolean(state.session.email) &&
    Boolean(state.session.token) &&
    !isSessionExpired(state.session)
  );
}

function isSessionExpired(session) {
  if (!session?.expires_at) return true;
  const expiresAt = new Date(session.expires_at);
  return Number.isNaN(expiresAt.getTime()) || expiresAt <= new Date();
}

function adminAuthHeaders(extraHeaders = {}) {
  if (!isAdminSession()) return { ...extraHeaders };
  return {
    ...extraHeaders,
    Authorization: `Bearer ${state.session.token}`,
  };
}

function formatSelectedFiles(files) {
  if (!files.length) return "Choose files";
  if (files.length === 1) return files[0].name;
  return `${files.length} files selected`;
}

async function loadLibrary() {
  if (!isAdminSession()) {
    state.documents = [];
    renderLibrary();
    return;
  }

  try {
    const response = await fetch("/api/library", {
      headers: adminAuthHeaders(),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const documents = await response.json();
    state.documents = Array.isArray(documents)
      ? documents.map(normalizeDocument)
      : [];
  } catch (error) {
    state.documents = [];
    console.error(error);
  }
  renderLibrary();
}

function normalizeDocument(item, index) {
  const documentKind = item.document_kind || "document";
  return {
    ...item,
    document_kind: documentKind,
    is_embeddable: Boolean(item.is_embeddable),
    display_name: formatDocumentTitle(
      item.display_name || `Document ${index + 1}`,
    ),
    description: "",
  };
}

function formatDocumentTitle(value) {
  return String(value)
    .replace(/\bsop\b/gi, "SOP")
    .replace(/\bics\b/gi, "ICS")
    .replace(/\bpp(\d+)\b/gi, (_, number) => `PP${number}`)
    .replace(/\bit\b/gi, "IT");
}

function getLibraryIcon(item) {
  const type = String(item.doc_type || "").toLowerCase();
  if (type === "pdf") return "picture_as_pdf";
  if (type === "doc" || type === "docx") return "article";
  if (type === "txt") return "text_snippet";
  return "description";
}

function renderLibrary() {
  const documents = state.documents.filter((item) => {
    const haystack =
      `${item.display_name} ${item.description || ""}`.toLowerCase();
    return !state.filter || haystack.includes(state.filter);
  });
  elements.libraryList.innerHTML = "";

  if (!documents.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Tidak ada dokumen yang cocok dengan filter ini.";
    elements.libraryList.appendChild(empty);
    return;
  }

  const documentItems = documents.filter(
    (item) => item.document_kind !== "form",
  );
  const formItems = documents.filter((item) => item.document_kind === "form");
  appendLibrarySection("Documents", documentItems);
  appendLibrarySection("Forms", formItems);
  updateDocumentControls();
}

function appendLibrarySection(title, items) {
  if (!items.length) return;

  const section = document.createElement("section");
  section.className = "library-section";

  const heading = document.createElement("div");
  heading.className = "library-section-heading";

  const headingTitle = document.createElement("h3");
  headingTitle.textContent = title;
  heading.appendChild(headingTitle);
  section.appendChild(heading);

  items.forEach((item) => {
    section.appendChild(createLibraryRow(item));
  });

  elements.libraryList.appendChild(section);
}

function createLibraryRow(item) {
  const fragment = elements.libraryItemTemplate.content.cloneNode(true);
  const row = fragment.querySelector(".document-row");
  row.dataset.kind = item.document_kind || "document";
  fragment.querySelector(".document-icon").textContent = getLibraryIcon(item);
  fragment.querySelector(".document-title").textContent = item.display_name;
  const meta = fragment.querySelector(".document-meta");
  meta.textContent = "";
  meta.hidden = true;
  const link = fragment.querySelector(".document-download");
  const updateButton = fragment.querySelector(".document-update");
  const deleteButton = fragment.querySelector(".document-delete");
  if (item.download_url) {
    link.href = item.download_url;
    link.addEventListener("click", (event) => {
      if (!isAdminSession()) return;
      event.preventDefault();
      downloadDocument(item.download_url, item.name || item.display_name);
    });
  } else {
    link.href = "#chat";
    link.addEventListener("click", (event) => {
      event.preventDefault();
      navigateTo("chat");
    });
  }
  if (item.relative_path) {
    updateButton.addEventListener("click", () => startDocumentReplace(item));
    deleteButton.addEventListener("click", () => deleteDocument(item));
  } else {
    updateButton.hidden = true;
    deleteButton.hidden = true;
  }
  return row;
}

async function downloadDocument(url, filename = "document") {
  try {
    const response = await fetch(url, {
      cache: "no-store",
      headers: adminAuthHeaders(),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename || "document";
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  } catch (error) {
    console.error(error);
    showDocumentStatus("Download dokumen gagal.", true);
  }
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

function formPathFromUrl(url) {
  // download_url looks like "/api/documents/<encoded relative path>"; the fill
  // endpoint unquotes it again, so pass the still-encoded path through.
  return String(url || "").replace(/^\/api\/documents\//, "");
}

async function openFormFillModal(item) {
  const path = formPathFromUrl(item.download_url);
  state.pendingFormFill = { path, label: item.label || item.name || "Form" };
  elements.formFillSubtitle.textContent = "";
  elements.formFillFields.innerHTML =
    '<p class="form-fill-note">Memuat kolom dari form…</p>';
  elements.formFillModal.classList.add("is-open");
  elements.formFillModal.setAttribute("aria-hidden", "false");

  try {
    const response = await fetch(
      `/api/forms/fields?path=${encodeURIComponent(path)}`,
    );
    const payload = await readJsonResponse(response);
    if (!response.ok)
      throw new Error(
        formatApiError(payload.detail, "Gagal memuat kolom form."),
      );
    // Ignore a stale response if the user already closed/switched forms.
    if (state.pendingFormFill?.path !== path) return;
    renderFormFillFields(Array.isArray(payload.fields) ? payload.fields : []);
  } catch (error) {
    elements.formFillFields.innerHTML = "";
    const note = document.createElement("p");
    note.className = "form-fill-note";
    note.textContent = error.message || "Gagal memuat kolom form.";
    elements.formFillFields.appendChild(note);
  }
}

function renderFormFillFields(fields) {
  elements.formFillFields.innerHTML = "";
  if (!fields.length) {
    const note = document.createElement("p");
    note.className = "form-fill-note";
    note.textContent = "Form ini tidak punya kolom isian yang terdeteksi.";
    elements.formFillFields.appendChild(note);
    return;
  }
  fields.forEach((field) => {
    const label = document.createElement("label");
    const span = document.createElement("span");
    span.textContent = field.label;
    const input = document.createElement("input");
    input.type = "text";
    input.dataset.key = field.key;
    label.append(span, input);
    elements.formFillFields.appendChild(label);
  });
  const firstInput = elements.formFillFields.querySelector("input");
  if (firstInput) window.setTimeout(() => firstInput.focus(), 0);
}

function closeFormFillModal() {
  state.pendingFormFill = null;
  elements.formFillModal.classList.remove("is-open");
  elements.formFillModal.setAttribute("aria-hidden", "true");
}

async function submitFormFill(event) {
  event.preventDefault();
  const pending = state.pendingFormFill;
  if (!pending) return;

  const values = {};
  elements.formFillFields
    .querySelectorAll("input[data-key]")
    .forEach((input) => {
      values[input.dataset.key] = input.value.trim();
    });

  try {
    const response = await fetch("/api/forms/fill", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: pending.path, values }),
    });
    if (!response.ok) {
      const payload = await readJsonResponse(response);
      throw new Error(formatApiError(payload.detail, "Gagal mengisi form."));
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = `${pending.label}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    closeFormFillModal();
  } catch (error) {
    openDocumentErrorModal(
      error.message || "Gagal mengisi form.",
      [],
      "Form gagal diisi",
    );
  }
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
