(function () {
  let state = null;
  let elements = null;

  function storage() {
    return window.AppStorage;
  }

  function formatUpdatedAt(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "baru saja";
    return date.toLocaleString("id-ID", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function getDraftProgress(draft) {
    const values = Object.values(draft.values || {});
    const filled = values.filter((value) =>
      typeof value === "boolean" ? value : String(value || "").trim(),
    ).length;
    if (!values.length) return "Belum ada isian";
    return `${filled}/${values.length} field terisi`;
  }

  function openDraft(draft) {
    closePopover();
    window.FormEditor.open(
      {
        label: draft.label || "Draft form",
        name: draft.label || "Draft form",
        download_url: `/api/documents/${draft.path}`,
      },
      { state, elements },
    );
  }

  function renderDraftItem(draft) {
    const button = document.createElement("button");
    button.className = "form-draft-item";
    button.type = "button";

    const icon = document.createElement("span");
    icon.className = "material-symbols-outlined";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "description";

    const copy = document.createElement("span");
    copy.className = "form-draft-item-copy";

    const title = document.createElement("strong");
    title.textContent = draft.label || "Draft form";

    const meta = document.createElement("small");
    meta.textContent = `${getDraftProgress(draft)} - ${formatUpdatedAt(draft.updated_at)}`;

    copy.append(title, meta);
    button.append(icon, copy);
    button.addEventListener("click", () => openDraft(draft));
    return button;
  }

  function render() {
    const drafts = storage().listFormDrafts();
    const hasDrafts = drafts.length > 0;
    elements.formDraftButton.hidden = !hasDrafts;
    elements.formDraftCount.textContent = String(drafts.length);

    if (!hasDrafts) {
      closePopover();
      elements.formDraftList.innerHTML = "";
      return;
    }

    elements.formDraftList.innerHTML = "";
    drafts.forEach((draft) => {
      elements.formDraftList.appendChild(renderDraftItem(draft));
    });
  }

  function openPopover() {
    render();
    if (elements.formDraftButton.hidden) return;
    elements.formDraftPopover.hidden = false;
    elements.formDraftButton.setAttribute("aria-expanded", "true");
  }

  function closePopover() {
    elements.formDraftPopover.hidden = true;
    elements.formDraftButton.setAttribute("aria-expanded", "false");
  }

  function togglePopover() {
    if (elements.formDraftPopover.hidden) openPopover();
    else closePopover();
  }

  function init(context = {}) {
    state = context.state;
    elements = context.elements;
    if (!elements?.formDraftButton || !elements?.formDraftPopover) return;

    elements.formDraftButton.addEventListener("click", (event) => {
      event.stopPropagation();
      togglePopover();
    });
    document.addEventListener("click", (event) => {
      if (elements.formDraftMenu?.contains(event.target)) return;
      closePopover();
    });
    window.addEventListener("formdraftschange", render);
    window.addEventListener("storage", (event) => {
      if (event.key?.startsWith("ics-hr-ai-form-draft-v1:")) render();
    });
    render();
  }

  window.FormDraftLauncher = {
    init,
    render,
    closePopover,
  };
})();
