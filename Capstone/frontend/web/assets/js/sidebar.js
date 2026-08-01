function bindSidebarConversations() {
  // Nothing to bind here directly; rows are (re)bound on every render because
  // the list itself is rebuilt from scratch each time, same pattern as
  // renderFaqs()/renderLibrary().
}

async function loadConversations() {
  if (!isLoggedIn()) {
    state.conversations = [];
    renderSidebarConversations();
    return;
  }
  if (state.isLoadingConversations) return;
  state.isLoadingConversations = true;
  try {
    const response = await fetch("/api/conversations", {
      headers: sessionAuthHeaders(),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const items = await response.json();
    state.conversations = Array.isArray(items) ? items : [];
  } catch (error) {
    console.warn("Failed to load chat history.", error);
  } finally {
    state.isLoadingConversations = false;
    renderSidebarConversations();
  }
}

function renderSidebarConversations() {
  if (!elements.conversationList) return;
  elements.conversationList.innerHTML = "";

  if (!isLoggedIn() || !state.conversations.length) {
    return;
  }

  state.conversations.forEach((item) => {
    const fragment = elements.conversationItemTemplate.content.cloneNode(true);
    const row = fragment.querySelector(".conversation-row");
    const openButton = fragment.querySelector(".conversation-open");
    const titleEl = fragment.querySelector(".conversation-title");
    const titleInput = fragment.querySelector(".conversation-title-input");
    const renameButton = fragment.querySelector(".conversation-rename");
    const deleteButton = fragment.querySelector(".conversation-delete");

    titleEl.textContent = item.title || "New chat";
    row.classList.toggle("is-active", item.id === state.conversationId);
    openButton.addEventListener("click", () => void openConversation(item.id));
    renameButton.addEventListener("click", (event) => {
      event.stopPropagation();
      beginInlineRename(item, titleEl, titleInput);
    });
    deleteButton.addEventListener("click", (event) => {
      event.stopPropagation();
      void deleteConversationConfirm(item);
    });

    elements.conversationList.appendChild(fragment);
  });
}

async function openConversation(conversationId) {
  if (state.isSubmitting || conversationId === state.conversationId) {
    navigateTo("chat");
    return;
  }
  try {
    const response = await fetch(
      `/api/conversations/${encodeURIComponent(conversationId)}/messages`,
      { headers: sessionAuthHeaders() },
    );
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    const messages = Array.isArray(payload.messages) ? payload.messages : [];

    state.conversationId = conversationId;
    window.localStorage.setItem(CONVERSATION_STORAGE_KEY, conversationId);
    // Carry the answer provenance through, not just role/content -- otherwise a
    // reopened conversation loses its "Model"/"Hit cache" badge and its feedback
    // buttons, which is what made restored answers look different from live ones.
    state.messages = messages.map((message) => ({
      role: message.role,
      content: message.content,
      answer_source: message.answer_source || "",
      feedback_id: message.feedback_id ?? null,
      feedback_token: message.feedback_token || "",
      feedback: message.feedback ?? null,
      duration_ms: Number.isFinite(message.duration_ms) ? message.duration_ms : undefined,
      citations: Array.isArray(message.citations) ? message.citations : [],
      form_downloads: Array.isArray(message.form_downloads) ? message.form_downloads : [],
    }));
    persistMessages();
    navigateTo("chat");
    renderMessages("auto", { forceScroll: true });
    renderSidebarConversations();
  } catch (error) {
    console.warn("Failed to open conversation.", error);
  }
}

function beginInlineRename(item, titleEl, inputEl) {
  inputEl.value = item.title || "";
  titleEl.hidden = true;
  inputEl.hidden = false;
  inputEl.focus();
  inputEl.select();

  let settled = false;
  const finish = (commit) => {
    if (settled) return;
    settled = true;
    inputEl.removeEventListener("keydown", onKeydown);
    inputEl.removeEventListener("blur", onBlur);
    titleEl.hidden = false;
    inputEl.hidden = true;
    const cleanTitle = inputEl.value.trim();
    if (commit && cleanTitle && cleanTitle !== item.title) {
      void submitRename(item, cleanTitle);
    }
  };
  const onKeydown = (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      finish(true);
    } else if (event.key === "Escape") {
      event.preventDefault();
      finish(false);
    }
  };
  const onBlur = () => finish(true);

  inputEl.addEventListener("keydown", onKeydown);
  inputEl.addEventListener("blur", onBlur);
}

async function submitRename(item, cleanTitle) {
  try {
    const response = await fetch(
      `/api/conversations/${encodeURIComponent(item.id)}`,
      {
        method: "PATCH",
        headers: sessionAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ title: cleanTitle }),
      },
    );
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    item.title = cleanTitle;
    renderSidebarConversations();
  } catch (error) {
    console.warn("Failed to rename conversation.", error);
  }
}

async function deleteConversationConfirm(item) {
  try {
    const response = await fetch(
      `/api/conversations/${encodeURIComponent(item.id)}`,
      { method: "DELETE", headers: sessionAuthHeaders() },
    );
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.conversations = state.conversations.filter((entry) => entry.id !== item.id);
    if (state.conversationId === item.id) {
      resetChat();
    }
    renderSidebarConversations();
  } catch (error) {
    console.warn("Failed to delete conversation.", error);
  }
}
