let guardrailsLoaded = false;
let isSavingGuardrails = false;

function bindGuardrails() {
  elements.guardrailsForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await saveGuardrails();
  });
}

function loadGuardrailsIfVisible() {
  if (isAdminSession() && state.activeScreen === "guardrails") {
    void loadGuardrails();
  }
}

async function loadGuardrails() {
  if (!elements.guardrailsTextarea) return;
  setGuardrailsStatus(I18N.t("guardrails.loading"));
  try {
    const response = await fetch("/api/admin/guardrails", {
      cache: "no-store",
      headers: adminAuthHeaders(),
    });
    const payload = await readJsonResponse(response);
    if (!response.ok) {
      throw new Error(formatApiError(payload.detail, I18N.t("guardrails.loadFailed")));
    }
    elements.guardrailsTextarea.value = payload.rules || "";
    guardrailsLoaded = true;
    setGuardrailsStatus("");
  } catch (error) {
    setGuardrailsStatus(error.message || I18N.t("guardrails.loadFailed"), true);
  }
}

async function saveGuardrails() {
  if (!isAdminSession() || isSavingGuardrails) return;
  const rules = elements.guardrailsTextarea?.value.trim() || "";
  if (rules.length < 10) {
    setGuardrailsStatus(I18N.t("guardrails.rulesTooShort"), true);
    return;
  }

  isSavingGuardrails = true;
  if (elements.guardrailsSaveButton) elements.guardrailsSaveButton.disabled = true;
  setGuardrailsStatus(I18N.t("guardrails.saving"));
  try {
    const response = await fetch("/api/admin/guardrails", {
      method: "PUT",
      headers: adminAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ rules }),
    });
    const payload = await readJsonResponse(response);
    if (!response.ok) {
      throw new Error(formatApiError(payload.detail, I18N.t("guardrails.saveFailed")));
    }
    elements.guardrailsTextarea.value = payload.rules || rules;
    setGuardrailsStatus(I18N.t("guardrails.saved"), false, true);
  } catch (error) {
    setGuardrailsStatus(error.message || I18N.t("guardrails.saveFailed"), true);
  } finally {
    isSavingGuardrails = false;
    if (elements.guardrailsSaveButton) elements.guardrailsSaveButton.disabled = false;
  }
}

function setGuardrailsStatus(message, isError = false, isSuccess = false) {
  if (!elements.guardrailsStatus) return;
  elements.guardrailsStatus.textContent = message || "";
  elements.guardrailsStatus.classList.toggle("is-error", isError);
  elements.guardrailsStatus.classList.toggle("is-success", isSuccess);
}
