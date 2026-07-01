const CHAT_STORAGE_KEY = "ics-hr-ai-chat-v3";
const AUTH_STORAGE_KEY = "ics-hr-ai-auth-v1";
const CONVERSATION_STORAGE_KEY = "ics-hr-ai-conversation-v1";

const adminAccounts = [
  { email: "admin@gmail.com", password: "admin123", name: "admin" },
];

const faqItems = [
  {
    question: "Berapa hak cuti tahunan karyawan?",
    answer:
      "Karyawan yang telah bekerja 12 bulan terus-menerus berhak atas 12 hari kerja cuti tahunan. Maksimal 5 hari dapat dibawa ke tahun berikutnya dan akan hangus pada 31 Maret jika tidak digunakan.",
    source: "ICS_PP03_Kebijakan_Cuti.pdf - Pasal 1 - PDF halaman 2",
    source_url: "/api/documents/ICS_PP03_Kebijakan_Cuti.pdf",
    suggested_query:
      "Jelaskan hak, pengajuan, dan carry over cuti tahunan karyawan.",
  },
  {
    question: "Bagaimana mekanisme dan perhitungan upah lembur?",
    answer:
      "Lembur dilakukan atas permintaan tertulis Atasan Langsung dengan persetujuan Karyawan. Jam pertama dibayar 1,5 kali upah per jam, jam berikutnya 2 kali, dengan batas maksimal 4 jam per hari dan 18 jam per minggu.",
    source: "ICS_PP01_Peraturan_Perusahaan.pdf - Pasal 6 - PDF halaman 2-3",
    source_url: "/api/documents/ICS_PP01_Peraturan_Perusahaan.pdf",
    suggested_query: "Bagaimana mekanisme dan perhitungan upah lembur?",
  },
  {
    question: "Kapan gaji bulanan dibayarkan?",
    answer:
      "Gaji dibayarkan setiap tanggal 25 melalui transfer bank. Jika tanggal 25 jatuh pada hari libur atau akhir pekan, pembayaran dilakukan pada hari kerja sebelumnya.",
    source: "ICS_PP02_Kebijakan_Penggajian.pdf - Pasal 4 - PDF halaman 3",
    source_url: "/api/documents/ICS_PP02_Kebijakan_Penggajian.pdf",
    suggested_query: "Kapan dan bagaimana gaji bulanan dibayarkan?",
  },
  {
    question: "Apa ketentuan password akun perusahaan?",
    answer:
      "Password minimal terdiri dari 12 karakter dengan kombinasi huruf besar, huruf kecil, angka, dan simbol. Password sistem kritikal diganti minimal setiap 90 hari dan MFA wajib untuk layanan cloud serta email perusahaan.",
    source: "ICS_PP04_Kebijakan_IT.pdf - Pasal 4 - PDF halaman 3",
    source_url: "/api/documents/ICS_PP04_Kebijakan_IT.pdf",
    suggested_query:
      "Apa seluruh ketentuan keamanan password dan MFA perusahaan?",
  },
  {
    question: "Bagaimana melaporkan insiden keamanan IT?",
    answer:
      "Insiden atau dugaan insiden harus segera dilaporkan ke Departemen IT melalui security@icscompute.com atau hotline IT dalam 1x24 jam. Penanganan berikutnya meliputi isolasi, investigasi, pemulihan, dan dokumentasi oleh tim IT.",
    source: "ICS_PP04_Kebijakan_IT.pdf - Pasal 7 - PDF halaman 3",
    source_url: "/api/documents/ICS_PP04_Kebijakan_IT.pdf",
    suggested_query:
      "Jelaskan prosedur lengkap pelaporan dan penanganan insiden keamanan IT.",
  },
  {
    question: "Apa ketentuan pengajuan cuti sakit?",
    answer:
      "Cuti sakit diberikan selama sakit berlangsung dengan Surat Keterangan Dokter. Sakit satu hari tanpa surat dokter diperbolehkan maksimal dua kali dalam setahun; kejadian ketiga wajib menyertakan surat dokter.",
    source: "ICS_PP03_Kebijakan_Cuti.pdf - Pasal 3 - PDF halaman 2",
    source_url: "/api/documents/ICS_PP03_Kebijakan_Cuti.pdf",
    suggested_query:
      "Jelaskan hak, bukti, dan ketentuan lengkap cuti sakit karyawan.",
  },
  {
    question: "Siapa yang berhak menerima THR dan kapan dibayarkan?",
    answer:
      "THR diberikan kepada karyawan dengan masa kerja minimal satu bulan secara terus-menerus. Besarannya satu kali gaji untuk masa kerja minimal 12 bulan atau proporsional untuk masa kerja 1-12 bulan, dan dibayarkan paling lambat tujuh hari sebelum hari raya.",
    source: "ICS_PP02_Kebijakan_Penggajian.pdf - Pasal 7 - PDF halaman 3",
    source_url: "/api/documents/ICS_PP02_Kebijakan_Penggajian.pdf",
    suggested_query: "Jelaskan syarat, perhitungan, dan jadwal pembayaran THR.",
  },
  {
    question: "Apa ketentuan Work From Home?",
    answer:
      "Work From Home diperbolehkan sesuai kebijakan Departemen SDM dan harus mendapat persetujuan Atasan Langsung. Jam kerja normal tetap 40 jam per minggu dengan core hours pukul 10.00-16.00 WIB.",
    source: "ICS_PP01_Peraturan_Perusahaan.pdf - Pasal 5 - PDF halaman 2",
    source_url: "/api/documents/ICS_PP01_Peraturan_Perusahaan.pdf",
    suggested_query:
      "Jelaskan aturan Work From Home, jam kerja, dan persetujuan yang dibutuhkan.",
  },
  {
    question: "Apa aturan penggunaan AI generatif untuk pekerjaan?",
    answer:
      "AI generatif boleh digunakan untuk drafting, brainstorming, dan analisis non-sensitif. Data Konfidensial atau Rahasia dilarang dimasukkan ke layanan AI publik, dan seluruh output AI wajib diverifikasi sebelum digunakan untuk keputusan atau diserahkan kepada klien.",
    source: "ICS_PP04_Kebijakan_IT.pdf - Pasal 9 - PDF halaman 4",
    source_url: "/api/documents/ICS_PP04_Kebijakan_IT.pdf",
    suggested_query:
      "Jelaskan hal yang boleh dan dilarang dalam penggunaan AI generatif untuk pekerjaan.",
  },
];

const fallbackDocuments = [
  [
    "Global Employee Handbook",
    "Ref: POL-2024-001 • Comprehensive guide for workplace conduct and values.",
  ],
  [
    "ISO 27001 Security Policy",
    "Ref: SEC-2024-012 • Information security management and compliance protocols.",
  ],
  [
    "Travel & Reimbursement Policy",
    "Ref: FIN-2024-005 • Guidelines for business travel and expense filing.",
  ],
  ["Data Privacy Addendum (DPA)", "Ref: APP-2024-001 • Last Review: Dec 2023"],
  [
    "Remote Work Agreement Template",
    "Ref: APP-2024-005 • Last Review: Jan 2024",
  ],
  [
    "Whistleblower Protection Policy",
    "Ref: APP-2024-009 • Last Review: Mar 2024",
  ],
].map(([display_name, description]) => ({
  display_name,
  description,
  download_url: "",
}));

const initialMessages = [];

const screens = {
  chat: "Active Session",
  faq: "Frequently Asked Questions",
  policy: "Policy Library",
};

const state = {
  activeScreen: "chat",
  isSubmitting: false,
  activeRequestController: null,
  activeRequestStartedAt: null,
  conversationId: loadConversationId(),
  messages: loadMessages(),
  documents: [],
  filter: "",
  session: loadSession(),
  pendingReplacePath: "",
  isMutatingDocument: false,
};

const elements = {
  body: document.body,
  screenTitle: document.getElementById("screenTitle"),
  navLinks: Array.from(document.querySelectorAll(".nav-link")),
  screens: Array.from(document.querySelectorAll(".screen")),
  chatScreen: document.querySelector('[data-screen-panel="chat"]'),
  chatThread: document.getElementById("chatThread"),
  chatForm: document.getElementById("chatForm"),
  chatInput: document.getElementById("chatInput"),
  sendButton: document.getElementById("sendButton"),
  newChatButton: document.getElementById("newChatButton"),
  faqList: document.getElementById("faqList"),
  libraryList: document.getElementById("libraryList"),
  librarySearch: document.getElementById("librarySearch"),
  policySearchWrap: document.getElementById("policySearchWrap"),
  filterButton: document.getElementById("filterButton"),
  downloadAllButton: document.getElementById("downloadAllButton"),
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
  adminDocumentPanel: document.getElementById("adminDocumentPanel"),
  adminDocumentForm: document.getElementById("adminDocumentForm"),
  documentFileInput: document.getElementById("documentFileInput"),
  documentFileLabel: document.getElementById("documentFileLabel"),
  documentUploadButton: document.getElementById("documentUploadButton"),
  documentReplaceInput: document.getElementById("documentReplaceInput"),
  adminDocumentStatus: document.getElementById("adminDocumentStatus"),
  messageTemplate: document.getElementById("messageTemplate"),
  faqTemplate: document.getElementById("faqTemplate"),
  libraryItemTemplate: document.getElementById("libraryItemTemplate"),
};

init();

function init() {
  bindNavigation();
  bindChat();
  bindPolicyActions();
  bindAuth();
  bindAdminDocuments();
  syncAuth();
  updateComposer();
  renderMessages();
  renderFaqs();
  syncScreenFromHash();
  void loadLibrary();
}

function bindNavigation() {
  window.addEventListener("hashchange", syncScreenFromHash);
  elements.navLinks.forEach((button) => {
    button.addEventListener("click", () => navigateTo(button.dataset.screen));
  });
  elements.menuToggle.addEventListener("click", () =>
    elements.body.classList.add("nav-open"),
  );
  elements.pageBackdrop.addEventListener("click", closeMobileNav);
}

function syncScreenFromHash() {
  const hash = window.location.hash.slice(1);
  const target = screens[hash] ? hash : "chat";
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
  window.location.hash = screen || "chat";
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
    { role: "assistant", loading: true, timestamp: "thinking" },
  );
  elements.chatInput.value = "";
  renderMessages("smooth");

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
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    if (payload.conversation_id) {
      state.conversationId = payload.conversation_id;
      window.localStorage.setItem(CONVERSATION_STORAGE_KEY, state.conversationId);
    }
    replaceLoading({
      role: "assistant",
      content: payload.answer || "No answer was returned.",
      citations: Array.isArray(payload.citations) ? payload.citations : [],
      duration_ms: Math.round(performance.now() - startedAt),
      timestamp: "Just now",
    });
  } catch (error) {
    if (error.name === "AbortError") return;
    replaceLoading({
      role: "assistant",
      content:
        "I couldn't reach the knowledge service. Please make sure the FastAPI server and vector database are running.",
      citations: [],
      duration_ms: Math.round(performance.now() - startedAt),
      timestamp: "Just now",
    });
    console.error(error);
  } finally {
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

  const durationMs = state.activeRequestStartedAt
    ? Math.round(performance.now() - state.activeRequestStartedAt)
    : undefined;

  state.activeRequestController?.abort();
  replaceLoading({
    role: "assistant",
    content: "Respons dihentikan.",
    citations: [],
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
  const index = state.messages.findIndex((item) => item.loading);
  if (index === -1) state.messages.push(message);
  else state.messages.splice(index, 1, message);
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
      bubble.innerHTML =
        '<span class="loading-dots"><span></span><span></span><span></span></span>Searching policies...';
    } else {
      bubble.appendChild(formatMessage(message.content, message.citations));
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

function scrollChatToBottom(behavior = "auto") {
  window.requestAnimationFrame(() => {
    elements.chatThread.scrollTo({
      top: elements.chatThread.scrollHeight,
      behavior,
    });

    window.requestAnimationFrame(() => {
      elements.chatThread.scrollTo({
        top: elements.chatThread.scrollHeight,
        behavior,
      });
    });
  });
}

function renderMessageCitationsLegacy(container, citations) {
  if (!Array.isArray(citations) || !citations.length) return;

  const heading = document.createElement("strong");
  heading.textContent = "Sumber";
  const list = document.createElement("ol");

  citations.forEach((citation) => {
    const item = document.createElement("li");
    const source = citation.download_url
      ? document.createElement("a")
      : document.createElement("span");
    source.textContent = citation.source || "Unknown source";
    if (citation.download_url) {
      source.href = citation.download_url;
      source.target = "_blank";
      source.rel = "noopener";
    }

    const location = document.createElement("span");
    location.className = "citation-location";
    location.textContent =
      [
        citation.section || null,
        citation.page ? `PDF halaman ${citation.page}` : null,
      ]
        .filter(Boolean)
        .join(" · ") || "Lokasi tidak tersedia";

    item.append(source, location);
    list.appendChild(item);
  });

  container.append(heading, list);
  container.hidden = false;
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
  const chip = citation.download_url
    ? document.createElement("a")
    : document.createElement("button");
  const fileType = getCitationFileType(citation);
  chip.className = `citation-chip citation-chip--${fileType}`;
  if (isInline) chip.classList.add("is-inline");
  chip.setAttribute("aria-label", formatCitationLabel(citation, index));

  if (citation.download_url) {
    chip.href = citation.download_url;
    chip.target = "_blank";
    chip.rel = "noopener";
  } else {
    chip.type = "button";
  }

  const icon = document.createElement("span");
  icon.className = "material-symbols-outlined citation-chip-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = getCitationIcon(fileType);

  const number = document.createElement("span");
  number.className = "citation-chip-number";
  number.textContent = String(citation.id || index + 1);

  const tooltip = document.createElement("span");
  tooltip.className = "citation-tooltip";
  tooltip.setAttribute("role", "tooltip");

  const title = document.createElement("strong");
  title.textContent = citation.source || "Unknown source";

  const meta = document.createElement("span");
  meta.textContent = formatCitationLocation(citation);

  tooltip.append(title, meta);
  chip.append(icon, number, tooltip);
  return chip;
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

function formatMessage(content, citations = []) {
  const wrapper = document.createElement("div");
  const lines = String(content).split(/\r?\n/);
  const citationMap = buildCitationMap(citations);
  let list = null;
  lines.forEach((line) => {
    const value = line.trim();
    if (!value) return;
    if (value.startsWith("- ")) {
      if (!list) {
        list = document.createElement("ul");
        wrapper.appendChild(list);
      }
      const item = document.createElement("li");
      appendFormattedText(item, value.slice(2), citationMap);
      list.appendChild(item);
      return;
    }
    list = null;
    const paragraph = document.createElement("p");
    appendFormattedText(paragraph, value, citationMap);
    wrapper.appendChild(paragraph);
  });
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

function appendFormattedText(container, text, citationMap) {
  const pattern = /\[(\d+)\]/g;
  let cursor = 0;
  let match = pattern.exec(text);

  while (match) {
    if (match.index > cursor) {
      container.append(document.createTextNode(text.slice(cursor, match.index)));
    }

    const citationEntry = citationMap.get(match[1]);
    if (citationEntry) {
      container.append(
        createCitationChip(citationEntry.citation, citationEntry.index, true),
      );
    } else {
      container.append(document.createTextNode(match[0]));
    }

    cursor = pattern.lastIndex;
    match = pattern.exec(text);
  }

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
    ? "Ketik pertanyaan berikutnya..."
    : "Tanya soal cuti, THR, lembur, WFH, atau policy lainnya...";
}

function renderFaqs() {
  elements.faqList.innerHTML = "";
  faqItems.forEach((item) => {
    const fragment = elements.faqTemplate.content.cloneNode(true);
    const container = fragment.querySelector(".faq-item");
    const trigger = fragment.querySelector(".faq-trigger");
    const source = fragment.querySelector(".faq-source");
    const askButton = fragment.querySelector(".faq-ask");
    fragment.querySelector(".faq-question").textContent = item.question;
    fragment.querySelector(".faq-answer").textContent = item.answer;
    source.textContent = item.source;
    source.href = item.source_url;
    trigger.addEventListener("click", () => {
      const isOpen = container.classList.toggle("is-open");
      trigger.setAttribute("aria-expanded", String(isOpen));
    });
    askButton.addEventListener("click", () => {
      elements.chatInput.value = item.suggested_query || item.question;
      navigateTo("chat");
      window.setTimeout(() => elements.chatInput.focus(), 0);
    });
    elements.faqList.appendChild(fragment);
  });
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
  elements.downloadAllButton.addEventListener("click", () => {
    state.documents
      .filter((item) => item.download_url)
      .forEach((item, index) => {
        window.setTimeout(
          () => window.open(item.download_url, "_blank", "noopener"),
          index * 150,
        );
      });
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
  elements.authForm.addEventListener("submit", handleAdminLogin);
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    closeAccountPopover();
    if (elements.authModal.classList.contains("is-open")) closeAuthModal();
    if (elements.logoutModal.classList.contains("is-open")) closeLogoutModal();
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

function handleAdminLogin(event) {
  event.preventDefault();
  const email = elements.adminEmail.value.trim().toLowerCase();
  const password = elements.adminPassword.value;
  const account = adminAccounts.find(
    (item) => item.email === email && item.password === password,
  );

  if (!account) {
    showAuthError("Email atau password admin belum cocok.");
    elements.adminPassword.select();
    return;
  }

  state.session = {
    role: "admin",
    email: account.email,
    name: account.name,
  };
  window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(state.session));
  syncAuth();
  closeAuthModal();
  closeMobileNav();
}

function logoutAdmin() {
  state.session = { role: "guest", email: "", name: "Guest" };
  window.localStorage.removeItem(AUTH_STORAGE_KEY);
  closeLogoutModal();
  syncAuth();
}

function syncAuth() {
  const isAdmin = state.session.role === "admin";
  elements.body.dataset.role = isAdmin ? "admin" : "guest";
  elements.accountAvatar.textContent = isAdmin ? "A" : "G";
  elements.accountRoleLabel.textContent = isAdmin
    ? "Admin mode"
    : "Guest access";
  elements.accountName.textContent = isAdmin
    ? state.session.name || state.session.email
    : "Guest";
  elements.accountHint.textContent = isAdmin
    ? "Admin"
    : "Login admin";
  elements.accountPopoverRole.textContent = isAdmin ? "Admin mode" : "Guest access";
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
  clearDocumentStatus();
  renderLibrary();
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
}

async function saveDocuments(files) {
  if (!isAdminSession() || state.isMutatingDocument) return;
  state.isMutatingDocument = true;
  updateDocumentControls();

  let successCount = 0;
  const failures = [];
  for (const [index, file] of files.entries()) {
    showDocumentStatus(`Uploading ${index + 1}/${files.length}: ${file.name}`);
    try {
      await saveDocumentRequest(file);
      successCount += 1;
    } catch (error) {
      failures.push(`${file.name}: ${error.message || "failed"}`);
    }
  }

  state.isMutatingDocument = false;
  updateDocumentControls();
  await loadLibrary();

  if (failures.length) {
    showDocumentStatus(
      `${successCount} uploaded, ${failures.length} failed. ${failures.join("; ")}`,
      true,
    );
    return;
  }
  showDocumentStatus(`${successCount} document${successCount === 1 ? "" : "s"} uploaded.`);
}

async function saveDocument(file, replacePath = "") {
  if (!isAdminSession() || state.isMutatingDocument) return;
  state.isMutatingDocument = true;
  updateDocumentControls();
  showDocumentStatus(replacePath ? "Updating document..." : "Uploading document...");

  try {
    const payload = await saveDocumentRequest(file, replacePath);
    showDocumentStatus(payload.message || "Document saved.");
    await loadLibrary();
  } catch (error) {
    showDocumentStatus(error.message || "Document update failed.", true);
  } finally {
    state.isMutatingDocument = false;
    updateDocumentControls();
  }
}

async function saveDocumentRequest(file, replacePath = "") {
  const response = await fetch("/api/admin/documents", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Admin-Email": state.session.email,
    },
    body: JSON.stringify({
      filename: file.name,
      content_base64: await fileToBase64(file),
      replace_path: replacePath || null,
    }),
  });
  const payload = await readJsonResponse(response);
  if (!response.ok) {
    throw new Error(payload.detail || "Document update failed.");
  }
  return payload;
}

async function deleteDocument(item) {
  if (!isAdminSession() || state.isMutatingDocument) return;
  const confirmed = window.confirm(`Delete "${item.display_name}"?`);
  if (!confirmed) return;

  state.isMutatingDocument = true;
  updateDocumentControls();
  showDocumentStatus("Deleting document...");

  try {
    const response = await fetch(`/api/admin/documents/${encodeURIComponent(item.relative_path)}`, {
      method: "DELETE",
      headers: { "X-Admin-Email": state.session.email },
    });
    const payload = await readJsonResponse(response);
    if (!response.ok) throw new Error(payload.detail || "Document delete failed.");
    showDocumentStatus(payload.message || "Document deleted.");
    await loadLibrary();
  } catch (error) {
    showDocumentStatus(error.message || "Document delete failed.", true);
  } finally {
    state.isMutatingDocument = false;
    updateDocumentControls();
  }
}

function startDocumentReplace(item) {
  if (!isAdminSession() || state.isMutatingDocument) return;
  state.pendingReplacePath = item.relative_path;
  elements.documentReplaceInput.value = "";
  elements.documentReplaceInput.click();
}

function updateDocumentControls() {
  elements.documentUploadButton.disabled = state.isMutatingDocument;
  elements.libraryList
    .querySelectorAll(".document-update, .document-delete")
    .forEach((button) => {
      button.disabled = state.isMutatingDocument;
    });
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
  return state.session.role === "admin" && Boolean(state.session.email);
}

function formatSelectedFiles(files) {
  if (!files.length) return "Choose files";
  if (files.length === 1) return files[0].name;
  return `${files.length} files selected`;
}

async function loadLibrary() {
  try {
    const response = await fetch("/api/library");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const documents = await response.json();
    state.documents = documents.length
      ? documents.map(normalizeDocument)
      : fallbackDocuments;
  } catch (error) {
    state.documents = fallbackDocuments;
    console.error(error);
  }
  renderLibrary();
}

function normalizeDocument(item, index) {
  return {
    ...item,
    display_name: formatDocumentTitle(
      item.display_name || `Policy Document ${index + 1}`,
    ),
    description: `Ref: ${item.doc_type || "DOC"}-${String(index + 1).padStart(3, "0")} • ${item.relative_path || "Internal policy document"}`,
  };
}

function formatDocumentTitle(value) {
  return String(value)
    .replace(/\bics\b/gi, "ICS")
    .replace(/\bpp(\d+)\b/gi, (_, number) => `PP${number}`)
    .replace(/\bit\b/gi, "IT");
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
    empty.textContent = "No policy documents match this filter.";
    elements.libraryList.appendChild(empty);
    return;
  }

  documents.forEach((item) => {
    const fragment = elements.libraryItemTemplate.content.cloneNode(true);
    fragment.querySelector(".document-title").textContent = item.display_name;
    fragment.querySelector(".document-meta").textContent =
      item.description || item.relative_path || "Internal policy document";
    const link = fragment.querySelector(".document-download");
    const updateButton = fragment.querySelector(".document-update");
    const deleteButton = fragment.querySelector(".document-delete");
    if (item.download_url) link.href = item.download_url;
    else {
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
    elements.libraryList.appendChild(fragment);
  });
  updateDocumentControls();
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

function loadSession() {
  const guest = { role: "guest", email: "", name: "Guest" };
  const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
  if (!raw) return guest;

  try {
    const parsed = JSON.parse(raw);
    const account = adminAccounts.find(
      (item) => item.email === String(parsed.email || "").toLowerCase(),
    );
    if (!account || parsed.role !== "admin") return guest;
    return { role: "admin", email: account.email, name: account.name };
  } catch {
    return guest;
  }
}

function getInitials(value) {
  return (
    String(value)
      .split(/[\s@._-]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part.charAt(0))
      .join("")
      .toUpperCase() || "A"
  );
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
