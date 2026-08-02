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
    I18N.applyI18n(fragment);
    fragment.querySelector(".faq-question").textContent = item.question;
    fragment
      .querySelector(".faq-answer")
      .appendChild(formatMessage(stripCitationMarkers(item.answer)));
    if (citations.length) {
      renderFaqCitations(citationContainer, citations);
      source.hidden = true;
    } else if (item.source) {
      source.textContent = item.source;
      const browserUrl = citationBrowserUrl(item);
      if (browserUrl) {
        source.href = withSessionToken(browserUrl);
        source.target = "_blank";
        source.rel = "noopener noreferrer";
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
          I18N.t("faq.noEvidence"),
          [],
          I18N.t("faq.noSourceTitle"),
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

function stripCitationMarkers(value) {
  return String(value)
    .replace(/\s*\[(\d+)\]/g, "")
    .replace(/\s+([.,;:!?])/g, "$1")
    .trim();
}

async function loadFaqs() {
  if (!isLoggedIn()) {
    state.faqItems = [];
    renderFaqs();
    return;
  }
  try {
    const response = await fetch("/api/faq", { headers: sessionAuthHeaders() });
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
    page: item.page,
    page_end: item.page_end,
    suggested_query: item.suggested_query || item.question,
    citations: Array.isArray(item.citations) ? item.citations : [],
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
      page: item.page,
      page_end: item.page_end,
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
    const canOpenDocument = Boolean(citation.download_url);
    const source = canOpenDocument
      ? document.createElement("a")
      : document.createElement("span");
    source.className = "faq-citation-link";
    source.textContent = formatCitationText(citation);
    if (canOpenDocument) {
      source.href = withSessionToken(citationBrowserUrl(citation));
      source.target = "_blank";
      source.rel = "noopener noreferrer";
    }
    list.appendChild(source);
  });
  container.appendChild(list);
  container.hidden = false;
}

function formatCitationText(citation) {
  return [
    citation.source || I18N.t("chat.citation.unknownSource"),
    citation.section || null,
    formatCitationPageRange(citation),
  ]
    .filter(Boolean)
    .join(" - ");
}

function formatCitationPageRange(citation) {
  const page = Number(citation?.page);
  const pageEnd = Number(citation?.page_end);
  if (!Number.isInteger(page) || page < 1) return null;
  if (Number.isInteger(pageEnd) && pageEnd > page) {
    return I18N.t("chat.citation.pdfPageRange", { start: page, end: pageEnd });
  }
  return I18N.t("chat.citation.pdfPage", { page });
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
  showFaqStatus(I18N.t("faq.cancelled"));
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
      showFaqStatus(I18N.t("faq.finalizeFirst"), true);
    }
    return;
  }

  const faqId = elements.faqIdInput.value;
  const payload = {
    question: elements.faqQuestionInput.value.trim(),
  };
  if (!payload.question) {
    showFaqStatus(I18N.t("faq.questionRequired"), true);
    return;
  }

  const generation = { cancelled: false };
  state.activeFaqGeneration = generation;
  state.isMutatingFaq = true;
  updateFaqControls();
  showFaqStop();
  showFaqStatus(
    faqId ? I18N.t("faq.regenerating") : I18N.t("faq.generating"),
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
        formatApiError(responsePayload.detail, I18N.t("faq.updateFailed")),
      );
      failure.status = response.status;
      throw failure;
    }
    if (
      responsePayload.item &&
      !hasFaqEvidence(normalizeFaq(responsePayload.item))
    ) {
      throw new Error(I18N.t("faq.noEvidenceOnSave"));
    }

    showFaqStatus(responsePayload.message || I18N.t("faq.saved"));
    resetFaqForm(false);
    await loadFaqs();
  } catch (error) {
    if (generation.cancelled) return;
    const message = formatFaqSaveError(error);
    showFaqStatus(I18N.t("faq.notSaved"), true);
    openDocumentErrorModal(
      message,
      [],
      faqId ? I18N.t("faq.notUpdatedTitle") : I18N.t("faq.notCreatedTitle"),
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

  // 422: the backend already validated that the question has no relevant
  // source in the indexed documents (e.g. an off-topic question).
  if (status === 422) {
    return I18N.t("faq.error422");
  }

  // 5xx: the AI service is down or failed to produce an answer.
  if (status >= 500) {
    console.warn("FAQ generation detail:", rawMessage);
    return I18N.t("faq.error5xx");
  }

  // Client-side error (no HTTP status) — fall back to the message content.
  if (!rawMessage) {
    return I18N.t("faq.errorGeneric");
  }
  const noSourcePatterns = [
    /no source/i,
    /no relevant source/i,
    /not available in the document/i,
    /not found in the document/i,
    /citation/i,
    /evidence/i,
  ];
  if (noSourcePatterns.some((pattern) => pattern.test(rawMessage))) {
    return I18N.t("faq.errorNoSource");
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
  elements.faqSubmitButton.textContent = I18N.t("faq.regenerate");
  showFaqStatus(I18N.t("faq.editing"));
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
  const confirmed = window.confirm(I18N.t("faq.deleteConfirm", { question: item.question }));
  if (!confirmed) return;

  state.isMutatingFaq = true;
  updateFaqControls();
  showFaqStatus(I18N.t("faq.deleting"));

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
      throw new Error(formatApiError(payload.detail, I18N.t("faq.deleteFailed")));
    showFaqStatus(payload.message || I18N.t("faq.deleted"));
    if (state.editingFaqId === item.id) resetFaqForm(false);
    await loadFaqs();
  } catch (error) {
    showFaqStatus(error.message || I18N.t("faq.deleteFailed"), true);
  } finally {
    state.isMutatingFaq = false;
    updateFaqControls();
  }
}

function resetFaqForm(clearStatus = true) {
  state.editingFaqId = "";
  elements.faqForm.reset();
  elements.faqIdInput.value = "";
  elements.faqSubmitButton.textContent = I18N.t("faq.generate");
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
