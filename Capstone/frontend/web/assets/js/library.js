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

  elements.formFileInput?.addEventListener("change", async () => {
    const files = Array.from(elements.formFileInput.files || []);
    if (!files.length || !state.pendingFormSopPath) return;
    const linkedSopPath = state.pendingFormSopPath;
    try {
      await saveFormDocumentsForSop(files, linkedSopPath);
    } finally {
      elements.formFileInput.value = "";
      state.pendingFormSopPath = "";
    }
  });

  elements.documentReindexButton.addEventListener("click", rebuildEmbeddings);
  elements.documentUndoButton.addEventListener("click", undoDocumentChange);
  bindTemplateDownloadModal();
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
      `${embeddableCount} dokumen knowledge diperbarui. Finalize sebelum lanjut.`,
    );
  } else if (successCount > 0) {
    pushDocumentChange({
      type: "insert",
      label: `Undo insert ${successCount} file${successCount === 1 ? "" : "s"}`,
      items: insertedItems,
      requires_reindex: false,
    });
    showDocumentStatus(
      `${successCount} file berhasil diunggah. Tidak perlu finalize.`,
    );
  }
  updateDocumentControls();
}

async function saveDocument(file, replacePath = "", options = {}) {
  if (!isAdminSession() || state.isMutatingDocument || state.isReindexing)
    return;
  state.isMutatingDocument = true;
  updateDocumentControls();
  const isFormPdf = isFormPdfFile(file);
  showDocumentStatus(getDocumentSaveStatus(file, replacePath));

  try {
    const previousSnapshot = replacePath
      ? await createDocumentSnapshot(findDocumentByPath(replacePath))
      : null;
    const payload = await saveDocumentRequest(file, replacePath, options);
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
        `${payload.message || "Document saved."} Finalize sebelum lanjut.`,
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
        formatDocumentSaveMessage(payload, isFormPdf),
      );
    }
  } catch (error) {
    showDocumentStatus(error.message || "Document update failed.", true);
  } finally {
    state.isMutatingDocument = false;
    updateDocumentControls();
  }
}

async function saveFormDocumentsForSop(files, linkedSopPath) {
  if (!isAdminSession() || state.isMutatingDocument || state.isReindexing)
    return;
  state.isMutatingDocument = true;
  state.activeDocumentFormPath = linkedSopPath;
  updateDocumentControls();

  let successCount = 0;
  const failures = [];
  const insertedItems = [];
  for (const [index, file] of files.entries()) {
    showDocumentStatus(`Uploading form ${index + 1}/${files.length}: ${file.name}`);
    try {
      const payload = await saveDocumentRequest(file, "", {
        documentKind: "form",
        linkedSopPath,
      });
      successCount += 1;
      if (payload.item) insertedItems.push(payload.item);
    } catch (error) {
      failures.push({
        name: file.name,
        reason: error.message || "Upload failed.",
      });
    }
  }

  state.isMutatingDocument = false;
  await loadLibrary();
  state.activeDocumentFormPath = linkedSopPath;

  if (insertedItems.length) {
    pushDocumentChange({
      type: "insert",
      label: `Undo insert ${insertedItems.length} form${insertedItems.length === 1 ? "" : "s"}`,
      items: insertedItems,
      requires_reindex: false,
    });
  }

  if (failures.length) {
    const summary = `${successCount} form uploaded, ${failures.length} failed.`;
    showDocumentStatus(summary, true);
    openDocumentErrorModal(summary, failures);
  } else if (successCount > 0) {
    showDocumentStatus(
      `${successCount} form${successCount === 1 ? "" : "s"} berhasil diunggah. Tidak perlu finalize.`,
    );
  }
  updateDocumentControls();
}

function isFormPdfFile(file) {
  return (
    String(file?.name || "")
      .trim()
      .toLowerCase()
      .startsWith("form") &&
    String(file?.name || "")
      .trim()
      .toLowerCase()
      .endsWith(".pdf")
  );
}

function getDocumentSaveStatus(file, replacePath = "") {
  if (isFormPdfFile(file)) {
    return replacePath ? "Updating form..." : "Uploading form...";
  }
  return replacePath ? "Updating document..." : "Uploading document...";
}

function formatDocumentSaveMessage(payload, isFormPdf = false) {
  const baseMessage = payload.message || "File saved.";
  return `${baseMessage} Tidak perlu finalize.`;
}

async function saveDocumentRequest(file, replacePath = "", options = {}) {
  return saveDocumentPayload({
    filename: file.name,
    content_base64: await fileToBase64(file),
    replace_path: replacePath || null,
    document_kind: options.documentKind || null,
    linked_sop_path: options.linkedSopPath || null,
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
        `${payload.message || "Document deleted."} Finalize sebelum lanjut.`,
      );
    } else {
      pushDocumentChange({
        type: "delete",
        label: "Undo delete file",
        previous: deletedSnapshot,
        requires_reindex: false,
      });
      showDocumentStatus(
        `${payload.message || "File deleted."} Tidak perlu finalize.`,
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
    document_kind: item.document_kind || "document",
    linked_sop_path: item.linked_sop_path || "",
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
    document_kind: snapshot.document_kind || null,
    linked_sop_path: snapshot.linked_sop_path || null,
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
      clearReindexRequired("Semua perubahan dokumen dibatalkan.");
    } else {
      showDocumentStatus(
        "Semua perubahan dokumen dibatalkan. Tidak perlu finalize.",
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
      throw new Error(payload.detail || "Finalize failed.");
    clearReindexRequired(payload.message || "Changes finalized.");
  } catch (error) {
    showDocumentStatus(error.message || "Finalize failed.", true);
  } finally {
    state.isReindexing = false;
    syncReindexState();
    updateDocumentControls();
    updateFaqControls();
  }
}

function markReindexRequired(
  message = "Document library changed. Finalize before continuing.",
) {
  state.needsReindex = true;
  window.localStorage.setItem(REINDEX_STORAGE_KEY, "1");
  syncReindexState();
  showDocumentStatus(message, false);
}

function clearReindexRequired(message = "Changes finalized.") {
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
      "Document library changed. Finalize before continuing.",
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
    formats: Array.isArray(item.formats) ? item.formats : [],
    linked_sop_path: item.linked_sop_path || "",
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
  const type = getDocumentType(item);
  if (type === "pdf") return "picture_as_pdf";
  if (type === "doc" || type === "docx") return "article";
  if (type === "xls" || type === "xlsx") return "table_chart";
  if (type === "txt") return "text_snippet";
  return "description";
}

function getDocumentType(item) {
  const explicitType = String(item?.doc_type || "").trim().toLowerCase();
  if (explicitType) return explicitType;
  const name = String(item?.name || item?.display_name || "");
  const match = name.toLowerCase().match(/\.([a-z0-9]+)$/);
  return match ? match[1] : "";
}

function getDocumentTypeColorGroup(item) {
  const type = getDocumentType(item);
  if (type === "doc" || type === "docx") return "word";
  if (type === "xls" || type === "xlsx") return "excel";
  if (type === "pdf" || type === "txt") return type;
  return "default";
}

function applyDocumentIcon(icon, item) {
  icon.textContent = getLibraryIcon(item);
  icon.dataset.docType = getDocumentTypeColorGroup(item);
}

function renderLibrary() {
  const visibleItems = state.documents.filter((item) => {
    const haystack =
      `${item.display_name} ${item.description || ""}`.toLowerCase();
    return !state.filter || haystack.includes(state.filter);
  });
  elements.libraryList.innerHTML = "";

  if (!visibleItems.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Tidak ada dokumen yang cocok dengan filter ini.";
    elements.libraryList.appendChild(empty);
    return;
  }

  const documentItems = visibleItems.filter(
    (item) => item.document_kind !== "form",
  );
  if (!documentItems.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Tidak ada dokumen yang cocok dengan filter ini.";
    elements.libraryList.appendChild(empty);
    updateDocumentControls();
    return;
  }
  if (
    state.activeDocumentFormPath &&
    !documentItems.some(
      (item) => documentFormKey(item) === state.activeDocumentFormPath,
    )
  ) {
    state.activeDocumentFormPath = "";
  }
  const allFormItems = state.documents.filter((item) => item.document_kind === "form");
  appendLibrarySection("Documents", documentItems, allFormItems);
  updateDocumentControls();
}

function appendLibrarySection(title, items, forms = []) {
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
    section.appendChild(createDocumentLibraryGroup(item, formsForDocument(item, forms)));
  });

  elements.libraryList.appendChild(section);
}

function createDocumentLibraryGroup(item, forms) {
  const group = document.createElement("div");
  group.className = "document-library-group";
  const key = documentFormKey(item);
  // Guests can't insert a form, so an SOP with zero linked forms has nothing
  // to show them; only render the panel when there are forms or an admin
  // could add one.
  const canManageForms = forms.length > 0 || isAdminSession();
  const isOpen = canManageForms && Boolean(key) && state.activeDocumentFormPath === key;
  const relatedId = `related-forms-${stableDomId(key || item.display_name)}`;
  group.classList.toggle("is-forms-open", Boolean(isOpen));
  group.appendChild(createLibraryRow(item, { isOpen, relatedId, canManageForms }));

  if (canManageForms) {
    const related = document.createElement("div");
    related.className = "related-forms";
    related.id = relatedId;
    const header = document.createElement("div");
    header.className = "related-forms-heading";
    const title = document.createElement("span");
    title.textContent = "Forms";
    header.appendChild(title);
    related.appendChild(header);

    forms.forEach((form) => related.appendChild(createRelatedFormRow(form)));
    related.appendChild(createInsertFormRow(item, forms.length > 0));
    group.appendChild(related);
  }
  return group;
}

function documentFormKey(item) {
  return String(item?.relative_path || item?.name || item?.display_name || "");
}

function stableDomId(value) {
  const safeValue = String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return safeValue || "document";
}

function toggleDocumentForms(item) {
  const key = documentFormKey(item);
  if (!key) return;
  state.activeDocumentFormPath =
    state.activeDocumentFormPath === key ? "" : key;
  renderLibrary();
}

function formsForDocument(documentItem, forms) {
  if (!documentItem?.relative_path) return [];
  const documentPath = String(documentItem.relative_path).toLowerCase();
  const documentName = String(documentItem.name || "").toLowerCase();
  return forms.filter((form) => {
    const linked = String(form.linked_sop_path || "").toLowerCase();
    return (
      linked === documentPath ||
      linked.endsWith(`/${documentName}`) ||
      linked === documentName
    );
  });
}

function createLibraryRow(item, options = {}) {
  const fragment = elements.libraryItemTemplate.content.cloneNode(true);
  const row = fragment.querySelector(".document-row");
  row.dataset.kind = item.document_kind || "document";
  applyDocumentIcon(fragment.querySelector(".document-icon"), item);
  fragment.querySelector(".document-title").textContent = item.display_name;
  const meta = fragment.querySelector(".document-meta");
  meta.textContent = "";
  meta.hidden = true;
  const link = fragment.querySelector(".document-download");
  const expandButton = fragment.querySelector(".document-expand");
  const updateButton = fragment.querySelector(".document-update");
  const deleteButton = fragment.querySelector(".document-delete");
  if (options.canManageForms) {
    row.classList.add("is-toggleable");
    row.tabIndex = 0;
    if (options.relatedId) row.setAttribute("aria-controls", options.relatedId);
    row.setAttribute("aria-expanded", options.isOpen ? "true" : "false");
    expandButton.setAttribute(
      "aria-label",
      options.isOpen
        ? `Hide forms for ${item.display_name}`
        : `Show forms for ${item.display_name}`,
    );
    expandButton.setAttribute("aria-expanded", options.isOpen ? "true" : "false");
    expandButton.addEventListener("click", () => toggleDocumentForms(item));
    row.addEventListener("click", (event) => {
      if (event.target.closest("a, button, input, label")) return;
      toggleDocumentForms(item);
    });
    row.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      if (event.target.closest("a, button, input, label")) return;
      event.preventDefault();
      toggleDocumentForms(item);
    });
  } else {
    expandButton.hidden = true;
  }
  if (item.download_url) {
    link.href = item.download_url;
    link.addEventListener("click", (event) => {
      event.preventDefault();
      openTemplateDownloadModal(item.download_url, item.name || item.display_name, {
        formats: downloadFormatsForDocument(item),
      });
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

function createRelatedFormRow(item) {
  const row = document.createElement("article");
  row.className = "related-form-row";
  row.dataset.kind = "form";

  const info = document.createElement("div");
  info.className = "related-form-info";
  const icon = document.createElement("span");
  icon.className = "material-symbols-outlined related-form-icon";
  icon.setAttribute("aria-hidden", "true");
  applyDocumentIcon(icon, item);
  const title = document.createElement("span");
  title.className = "related-form-title";
  title.textContent = item.display_name || item.name || "Form";
  info.append(icon, title);

  const actions = document.createElement("div");
  actions.className = "related-form-actions";

  const downloadButton = document.createElement("button");
  downloadButton.className = "related-form-button";
  downloadButton.type = "button";
  downloadButton.title = "Download form";
  downloadButton.setAttribute("aria-label", `Download ${item.display_name || item.name || "form"}`);
  downloadButton.innerHTML = '<span class="material-symbols-outlined">download</span>';
  downloadButton.addEventListener("click", () => {
    openTemplateDownloadModal(item.download_url, item.name || item.display_name, {
      formats: downloadFormatsForDocument(item),
    });
  });
  actions.appendChild(downloadButton);

  const deleteButton = document.createElement("button");
  deleteButton.className = "related-form-button admin-only is-danger";
  deleteButton.type = "button";
  deleteButton.title = "Delete form";
  deleteButton.setAttribute("aria-label", `Delete ${item.display_name || item.name || "form"}`);
  deleteButton.innerHTML = '<span class="material-symbols-outlined">delete</span>';
  deleteButton.addEventListener("click", () => deleteDocument(item));
  actions.appendChild(deleteButton);

  row.append(info, actions);
  return row;
}

function createInsertFormRow(sop, hasForms) {
  const row = document.createElement("button");
  row.className = "related-form-insert admin-only";
  row.type = "button";
  row.setAttribute(
    "aria-label",
    hasForms ? "Insert another form" : "Insert form for this SOP",
  );
  const icon = document.createElement("span");
  icon.className = "material-symbols-outlined";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = "upload_file";
  const label = document.createElement("span");
  label.textContent = hasForms ? "Insert another form" : "Insert form";
  row.append(icon, label);
  row.addEventListener("click", () => startFormUploadForSop(sop));
  return row;
}

function startFormUploadForSop(item) {
  if (!isAdminSession() || state.isMutatingDocument || state.isReindexing) return;
  if (!item?.relative_path || !elements.formFileInput) return;
  state.pendingFormSopPath = item.relative_path;
  elements.formFileInput.value = "";
  elements.formFileInput.click();
}

let templateDownloadModalBound = false;

function bindTemplateDownloadModal() {
  if (!elements.templateDownloadModal) return;
  if (templateDownloadModalBound) return;
  templateDownloadModalBound = true;
  elements.templateDownloadPdfButton?.addEventListener("click", () => {
    downloadPendingTemplateFormat("pdf");
  });
  elements.templateDownloadWordButton?.addEventListener("click", () => {
    downloadPendingTemplateFormat("docx");
  });
  elements.templateDownloadCancelButton?.addEventListener(
    "click",
    closeTemplateDownloadModal,
  );
  elements.templateDownloadModal.addEventListener("click", (event) => {
    if (event.target === elements.templateDownloadModal) closeTemplateDownloadModal();
  });
}

function openTemplateDownloadModal(url, filename = "form.pdf", options = {}) {
  if (!url) return;
  bindTemplateDownloadModal();
  const formats =
    options.formats ||
    templateDownloadFormats(url, filename, ["pdf", "docx"]);
  if (!elements.templateDownloadModal) {
    const fallbackFormat = firstAvailableDownloadFormat(formats);
    if (fallbackFormat) downloadDocument(fallbackFormat.url, fallbackFormat.filename);
    return;
  }
  state.pendingTemplateDownload = { url, filename, formats };
  syncTemplateDownloadFormatButton(elements.templateDownloadPdfButton, formats.pdf);
  syncTemplateDownloadFormatButton(elements.templateDownloadWordButton, formats.docx);
  elements.templateDownloadName.textContent = filename || "Form template";
  elements.templateDownloadModal.classList.add("is-open");
  elements.templateDownloadModal.setAttribute("aria-hidden", "false");
  window.setTimeout(() => {
    const firstButton =
      elements.templateDownloadModal?.querySelector(".template-format-button:not([hidden])");
    firstButton?.focus();
  }, 0);
}

function closeTemplateDownloadModal() {
  state.pendingTemplateDownload = null;
  elements.templateDownloadModal?.classList.remove("is-open");
  elements.templateDownloadModal?.setAttribute("aria-hidden", "true");
}

function withDownloadFormat(url, format) {
  const nextUrl = new URL(url, window.location.origin);
  nextUrl.searchParams.set("format", format);
  return nextUrl.pathname + nextUrl.search;
}

function withFileExtension(filename, extension) {
  const safeName = String(filename || "form").replace(/\.(pdf|docx|txt|xlsx|xls)$/i, "");
  return `${safeName}.${extension}`;
}

function templateDownloadFormats(url, filename, availableFormats) {
  const formats = {};
  if (availableFormats.includes("pdf")) {
    formats.pdf = {
      label: "PDF",
      url,
      filename: withFileExtension(filename, "pdf"),
    };
  }
  if (availableFormats.includes("docx")) {
    formats.docx = {
      label: "Word",
      url: withDownloadFormat(url, "docx"),
      filename: withFileExtension(filename, "docx"),
    };
  }
  if (availableFormats.includes("txt")) {
    formats.pdf = {
      label: "TXT",
      url,
      filename: withFileExtension(filename, "txt"),
    };
  }
  if (availableFormats.includes("xlsx")) {
    formats.pdf = {
      label: "Excel",
      url,
      filename: withFileExtension(filename, "xlsx"),
    };
  } else if (availableFormats.includes("xls")) {
    formats.pdf = {
      label: "Excel",
      url,
      filename: withFileExtension(filename, "xls"),
    };
  }
  return formats;
}

function downloadFormatsForDocument(item) {
  const type = String(item.doc_type || "").toLowerCase();
  const filename = item.name || item.display_name || "document";
  if (Array.isArray(item.formats) && item.formats.length) {
    return templateDownloadFormats(item.download_url, filename, item.formats);
  }
  if (item.document_kind === "form") {
    if (type === "pdf") return templateDownloadFormats(item.download_url, filename, ["pdf", "docx"]);
    if (type === "docx") return templateDownloadFormats(item.download_url, filename, ["docx"]);
    if (type === "xlsx" || type === "xls") {
      return templateDownloadFormats(item.download_url, filename, [type]);
    }
  }
  if (type === "pdf") return templateDownloadFormats(item.download_url, filename, ["pdf"]);
  if (type === "doc" || type === "docx") {
    return {
      docx: {
        label: "Word",
        url: item.download_url,
        filename: withFileExtension(filename, "docx"),
      },
    };
  }
  if (type === "txt") return templateDownloadFormats(item.download_url, filename, ["txt"]);
  return {
    pdf: {
      label: "Download",
      url: item.download_url,
      filename,
    },
  };
}

function syncTemplateDownloadFormatButton(button, format) {
  if (!button) return;
  button.hidden = !format;
  if (!format) return;
  button.textContent = format.label;
}

function firstAvailableDownloadFormat(formats) {
  return formats.docx || formats.pdf || null;
}

function downloadPendingTemplateFormat(format) {
  const pending = state.pendingTemplateDownload;
  const selectedFormat = pending?.formats?.[format];
  closeTemplateDownloadModal();
  if (selectedFormat) downloadDocument(selectedFormat.url, selectedFormat.filename);
}

async function downloadDocument(url, filename = "document") {
  try {
    const response = await fetch(url, {
      cache: "no-store",
      headers: adminAuthHeaders(),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const blob = await response.blob();
    const responseFilename =
      typeof window.AppApi?.filenameFromResponse === "function"
        ? window.AppApi.filenameFromResponse(response, filename)
        : filename;
    window.AppApi.downloadBlob(blob, responseFilename);
  } catch (error) {
    console.error(error);
    showDocumentStatus("Download dokumen gagal.", true);
  }
}

window.openTemplateDownloadModal = openTemplateDownloadModal;
window.closeTemplateDownloadModal = closeTemplateDownloadModal;
window.downloadDocument = downloadDocument;
