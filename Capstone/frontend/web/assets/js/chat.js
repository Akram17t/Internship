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
      answer_source: normalizeAnswerSource(payload.answer_source),
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
      content: `Aku belum bisa menyelesaikan jawaban ini. ${error.message || "Pastikan FastAPI, layanan AI, dan database embedding sedang berjalan."}`,
      citations: [],
      flowcharts: [],
      answer_source: "fallback",
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
    const avatar = fragment.querySelector(".message-avatar");
    const bubble = fragment.querySelector(".message-bubble");
    const meta = fragment.querySelector(".message-meta");
    const isAssistant = message.role === "assistant";

    article.classList.add(isAssistant ? "is-assistant" : "is-user");
    if (isAssistant) {
      avatar.alt = "AI Assistant";
    } else {
      avatar.remove();
    }
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
    if (isAssistant && message.answer_source) {
      const source = document.createElement("span");
      source.className = `message-source message-source--${message.answer_source}`;
      source.textContent = formatAnswerSource(message.answer_source);
      meta.append(" • ", source);
    }
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

function normalizeAnswerSource(value) {
  const source = String(value || "").toLowerCase();
  if (source === "cache" || source === "model" || source === "fallback") {
    return source;
  }
  return "model";
}

function formatAnswerSource(source) {
  if (source === "cache") return "Hit cache";
  if (source === "fallback") return "Fallback";
  return "Model";
}

function createCitationChip(citation, index, isInline = false) {
  const fileType = getCitationFileType(citation);
  const canOpenDocument = Boolean(citation.download_url);
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
    if (item.download_url) window.FormEditor.open(item, { state, elements });
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
