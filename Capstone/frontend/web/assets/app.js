const CHAT_STORAGE_KEY = "ics-hr-ai-chat-v3";

const faqItems = [
  {
    question: "Berapa hak cuti tahunan karyawan?",
    answer: "Karyawan yang telah bekerja 12 bulan terus-menerus berhak atas 12 hari kerja cuti tahunan. Maksimal 5 hari dapat dibawa ke tahun berikutnya dan akan hangus pada 31 Maret jika tidak digunakan.",
    source: "ICS_PP03_Kebijakan_Cuti.pdf - Pasal 1 - PDF halaman 2",
    source_url: "/api/documents/ICS_PP03_Kebijakan_Cuti.pdf",
    suggested_query: "Jelaskan hak, pengajuan, dan carry over cuti tahunan karyawan.",
  },
  {
    question: "Bagaimana mekanisme dan perhitungan upah lembur?",
    answer: "Lembur dilakukan atas permintaan tertulis Atasan Langsung dengan persetujuan Karyawan. Jam pertama dibayar 1,5 kali upah per jam, jam berikutnya 2 kali, dengan batas maksimal 4 jam per hari dan 18 jam per minggu.",
    source: "ICS_PP01_Peraturan_Perusahaan.pdf - Pasal 6 - PDF halaman 2-3",
    source_url: "/api/documents/ICS_PP01_Peraturan_Perusahaan.pdf",
    suggested_query: "Bagaimana mekanisme dan perhitungan upah lembur?",
  },
  {
    question: "Kapan gaji bulanan dibayarkan?",
    answer: "Gaji dibayarkan setiap tanggal 25 melalui transfer bank. Jika tanggal 25 jatuh pada hari libur atau akhir pekan, pembayaran dilakukan pada hari kerja sebelumnya.",
    source: "ICS_PP02_Kebijakan_Penggajian.pdf - Pasal 4 - PDF halaman 3",
    source_url: "/api/documents/ICS_PP02_Kebijakan_Penggajian.pdf",
    suggested_query: "Kapan dan bagaimana gaji bulanan dibayarkan?",
  },
  {
    question: "Apa ketentuan password akun perusahaan?",
    answer: "Password minimal terdiri dari 12 karakter dengan kombinasi huruf besar, huruf kecil, angka, dan simbol. Password sistem kritikal diganti minimal setiap 90 hari dan MFA wajib untuk layanan cloud serta email perusahaan.",
    source: "ICS_PP04_Kebijakan_IT.pdf - Pasal 4 - PDF halaman 3",
    source_url: "/api/documents/ICS_PP04_Kebijakan_IT.pdf",
    suggested_query: "Apa seluruh ketentuan keamanan password dan MFA perusahaan?",
  },
  {
    question: "Bagaimana melaporkan insiden keamanan IT?",
    answer: "Insiden atau dugaan insiden harus segera dilaporkan ke Departemen IT melalui security@icscompute.com atau hotline IT dalam 1x24 jam. Penanganan berikutnya meliputi isolasi, investigasi, pemulihan, dan dokumentasi oleh tim IT.",
    source: "ICS_PP04_Kebijakan_IT.pdf - Pasal 7 - PDF halaman 3",
    source_url: "/api/documents/ICS_PP04_Kebijakan_IT.pdf",
    suggested_query: "Jelaskan prosedur lengkap pelaporan dan penanganan insiden keamanan IT.",
  },
  {
    question: "Apa ketentuan pengajuan cuti sakit?",
    answer: "Cuti sakit diberikan selama sakit berlangsung dengan Surat Keterangan Dokter. Sakit satu hari tanpa surat dokter diperbolehkan maksimal dua kali dalam setahun; kejadian ketiga wajib menyertakan surat dokter.",
    source: "ICS_PP03_Kebijakan_Cuti.pdf - Pasal 3 - PDF halaman 2",
    source_url: "/api/documents/ICS_PP03_Kebijakan_Cuti.pdf",
    suggested_query: "Jelaskan hak, bukti, dan ketentuan lengkap cuti sakit karyawan.",
  },
  {
    question: "Siapa yang berhak menerima THR dan kapan dibayarkan?",
    answer: "THR diberikan kepada karyawan dengan masa kerja minimal satu bulan secara terus-menerus. Besarannya satu kali gaji untuk masa kerja minimal 12 bulan atau proporsional untuk masa kerja 1-12 bulan, dan dibayarkan paling lambat tujuh hari sebelum hari raya.",
    source: "ICS_PP02_Kebijakan_Penggajian.pdf - Pasal 7 - PDF halaman 3",
    source_url: "/api/documents/ICS_PP02_Kebijakan_Penggajian.pdf",
    suggested_query: "Jelaskan syarat, perhitungan, dan jadwal pembayaran THR.",
  },
  {
    question: "Apa ketentuan Work From Home?",
    answer: "Work From Home diperbolehkan sesuai kebijakan Departemen SDM dan harus mendapat persetujuan Atasan Langsung. Jam kerja normal tetap 40 jam per minggu dengan core hours pukul 10.00-16.00 WIB.",
    source: "ICS_PP01_Peraturan_Perusahaan.pdf - Pasal 5 - PDF halaman 2",
    source_url: "/api/documents/ICS_PP01_Peraturan_Perusahaan.pdf",
    suggested_query: "Jelaskan aturan Work From Home, jam kerja, dan persetujuan yang dibutuhkan.",
  },
  {
    question: "Apa aturan penggunaan AI generatif untuk pekerjaan?",
    answer: "AI generatif boleh digunakan untuk drafting, brainstorming, dan analisis non-sensitif. Data Konfidensial atau Rahasia dilarang dimasukkan ke layanan AI publik, dan seluruh output AI wajib diverifikasi sebelum digunakan untuk keputusan atau diserahkan kepada klien.",
    source: "ICS_PP04_Kebijakan_IT.pdf - Pasal 9 - PDF halaman 4",
    source_url: "/api/documents/ICS_PP04_Kebijakan_IT.pdf",
    suggested_query: "Jelaskan hal yang boleh dan dilarang dalam penggunaan AI generatif untuk pekerjaan.",
  },
];

const fallbackDocuments = [
  ["Global Employee Handbook", "Ref: POL-2024-001 • Comprehensive guide for workplace conduct and values."],
  ["ISO 27001 Security Policy", "Ref: SEC-2024-012 • Information security management and compliance protocols."],
  ["Travel & Reimbursement Policy", "Ref: FIN-2024-005 • Guidelines for business travel and expense filing."],
  ["Data Privacy Addendum (DPA)", "Ref: APP-2024-001 • Last Review: Dec 2023"],
  ["Remote Work Agreement Template", "Ref: APP-2024-005 • Last Review: Jan 2024"],
  ["Whistleblower Protection Policy", "Ref: APP-2024-009 • Last Review: Mar 2024"],
].map(([display_name, description]) => ({ display_name, description, download_url: "" }));

const initialMessages = [];

const screens = {
  chat: "Active Session",
  faq: "Frequently Asked Questions",
  policy: "Policy Library",
};

const state = {
  activeScreen: "chat",
  isSubmitting: false,
  messages: loadMessages(),
  documents: [],
  filter: "",
};

const elements = {
  body: document.body,
  screenTitle: document.getElementById("screenTitle"),
  navLinks: Array.from(document.querySelectorAll(".nav-link")),
  screens: Array.from(document.querySelectorAll(".screen")),
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
  messageTemplate: document.getElementById("messageTemplate"),
  faqTemplate: document.getElementById("faqTemplate"),
  libraryItemTemplate: document.getElementById("libraryItemTemplate"),
};

init();

function init() {
  bindNavigation();
  bindChat();
  bindPolicyActions();
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
  elements.menuToggle.addEventListener("click", () => elements.body.classList.add("nav-open"));
  elements.pageBackdrop.addEventListener("click", closeMobileNav);
}

function syncScreenFromHash() {
  const hash = window.location.hash.slice(1);
  const target = screens[hash] ? hash : "chat";
  state.activeScreen = target;
  elements.body.dataset.activeScreen = target;
  elements.screenTitle.textContent = screens[target];

  elements.navLinks.forEach((button) => button.classList.toggle("is-active", button.dataset.screen === target));
  elements.screens.forEach((screen) => screen.classList.toggle("is-active", screen.dataset.screenPanel === target));
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
    await submitQuestion(elements.chatInput.value);
  });

  elements.chatInput.addEventListener("keydown", async (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      await submitQuestion(elements.chatInput.value);
    }
  });
}

function resetChat() {
  if (state.isSubmitting) return;
  state.messages = [];
  window.localStorage.removeItem(CHAT_STORAGE_KEY);
  elements.chatInput.value = "";
  renderMessages();
  navigateTo("chat");
  window.setTimeout(() => elements.chatInput.focus(), 0);
}

async function submitQuestion(rawQuestion) {
  const question = rawQuestion.trim();
  if (!question || state.isSubmitting) return;
  const startedAt = performance.now();

  state.isSubmitting = true;
  updateComposer();
  state.messages.push(
    { role: "user", content: question, timestamp: "Just now" },
    { role: "assistant", loading: true, timestamp: "thinking" },
  );
  elements.chatInput.value = "";
  renderMessages();

  try {
    const response = await fetch("/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    replaceLoading({
      role: "assistant",
      content: payload.answer || "No answer was returned.",
      citations: Array.isArray(payload.citations) ? payload.citations : [],
      duration_ms: Math.round(performance.now() - startedAt),
      timestamp: "Just now",
    });
  } catch (error) {
    replaceLoading({
      role: "assistant",
      content: "I couldn't reach the knowledge service. Please make sure the FastAPI server and vector database are running.",
      citations: [],
      duration_ms: Math.round(performance.now() - startedAt),
      timestamp: "Just now",
    });
    console.error(error);
  } finally {
    state.isSubmitting = false;
    updateComposer();
    persistMessages();
    renderMessages();
  }
}

function replaceLoading(message) {
  const index = state.messages.findIndex((item) => item.loading);
  if (index === -1) state.messages.push(message);
  else state.messages.splice(index, 1, message);
}

function renderMessages() {
  elements.chatThread.innerHTML = "";
  state.messages.forEach((message) => {
    const fragment = elements.messageTemplate.content.cloneNode(true);
    const article = fragment.querySelector(".message");
    const bubble = fragment.querySelector(".message-bubble");
    const citations = fragment.querySelector(".message-citations");
    const meta = fragment.querySelector(".message-meta");
    const isAssistant = message.role === "assistant";

    article.classList.add(isAssistant ? "is-assistant" : "is-user");
    if (message.loading) {
      article.classList.add("message--loading");
      bubble.innerHTML = '<span class="loading-dots"><span></span><span></span><span></span></span>Searching policies...';
    } else {
      bubble.appendChild(formatMessage(message.content));
      renderMessageCitations(citations, message.citations);
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
  elements.chatThread.scrollTop = elements.chatThread.scrollHeight;
}

function renderMessageCitations(container, citations) {
  if (!Array.isArray(citations) || !citations.length) return;

  const heading = document.createElement("strong");
  heading.textContent = "Sumber";
  const list = document.createElement("ol");

  citations.forEach((citation) => {
    const item = document.createElement("li");
    const source = citation.download_url ? document.createElement("a") : document.createElement("span");
    source.textContent = citation.source || "Unknown source";
    if (citation.download_url) {
      source.href = citation.download_url;
      source.target = "_blank";
      source.rel = "noopener";
    }

    const location = document.createElement("span");
    location.className = "citation-location";
    location.textContent = [
      citation.section || null,
      citation.page ? `PDF halaman ${citation.page}` : null,
    ].filter(Boolean).join(" · ") || "Lokasi tidak tersedia";

    item.append(source, location);
    list.appendChild(item);
  });

  container.append(heading, list);
  container.hidden = false;
}

function formatMessage(content) {
  const wrapper = document.createElement("div");
  const lines = String(content).split(/\r?\n/);
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
      item.textContent = value.slice(2);
      list.appendChild(item);
      return;
    }
    list = null;
    const paragraph = document.createElement("p");
    paragraph.textContent = value;
    wrapper.appendChild(paragraph);
  });
  return wrapper;
}

function formatDuration(milliseconds) {
  if (milliseconds < 1000) return `${milliseconds} ms`;
  if (milliseconds < 60000) return `${(milliseconds / 1000).toFixed(1)}s`;

  const minutes = Math.floor(milliseconds / 60000);
  const seconds = Math.round((milliseconds % 60000) / 1000);
  return `${minutes}m ${seconds}s`;
}

function updateComposer() {
  elements.chatInput.disabled = state.isSubmitting;
  elements.sendButton.disabled = state.isSubmitting;
  elements.newChatButton.disabled = state.isSubmitting;
  elements.chatInput.placeholder = state.isSubmitting ? "Searching policies..." : "Type your message here...";
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
    if (elements.policySearchWrap.classList.contains("is-visible")) elements.librarySearch.focus();
  });
  elements.librarySearch.addEventListener("input", () => {
    state.filter = elements.librarySearch.value.trim().toLowerCase();
    renderLibrary();
  });
  elements.downloadAllButton.addEventListener("click", () => {
    state.documents.filter((item) => item.download_url).forEach((item, index) => {
      window.setTimeout(() => window.open(item.download_url, "_blank", "noopener"), index * 150);
    });
  });
  elements.chatLink.addEventListener("click", () => navigateTo("chat"));
}

async function loadLibrary() {
  try {
    const response = await fetch("/api/library");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const documents = await response.json();
    state.documents = documents.length ? documents.map(normalizeDocument) : fallbackDocuments;
  } catch (error) {
    state.documents = fallbackDocuments;
    console.error(error);
  }
  renderLibrary();
}

function normalizeDocument(item, index) {
  return {
    ...item,
    display_name: item.display_name || `Policy Document ${index + 1}`,
    description: `Ref: ${item.doc_type || "DOC"}-${String(index + 1).padStart(3, "0")} • ${item.relative_path || "Internal policy document"}`,
  };
}

function renderLibrary() {
  const documents = state.documents.filter((item) => {
    const haystack = `${item.display_name} ${item.description || ""}`.toLowerCase();
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
    fragment.querySelector(".document-meta").textContent = item.description || item.relative_path || "Internal policy document";
    const link = fragment.querySelector(".document-download");
    if (item.download_url) link.href = item.download_url;
    else {
      link.href = "#chat";
      link.addEventListener("click", (event) => {
        event.preventDefault();
        navigateTo("chat");
      });
    }
    elements.libraryList.appendChild(fragment);
  });
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
  window.localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(state.messages.filter((message) => !message.loading)));
}
