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
  setGuardrailsStatus("Loading...");
  try {
    const response = await fetch("/api/admin/guardrails", {
      cache: "no-store",
      headers: adminAuthHeaders(),
    });
    const payload = await readJsonResponse(response);
    if (!response.ok) {
      throw new Error(formatApiError(payload.detail, "Unable to load guardrails."));
    }
    elements.guardrailsTextarea.value = payload.rules || "";
    guardrailsLoaded = true;
    setGuardrailsStatus("");
  } catch (error) {
    setGuardrailsStatus(error.message || "Unable to load guardrails.", true);
  }
}

async function saveGuardrails() {
  if (!isAdminSession() || isSavingGuardrails) return;
  const rules = elements.guardrailsTextarea?.value.trim() || "";
  if (rules.length < 10) {
    setGuardrailsStatus("Rules minimal 10 karakter.", true);
    return;
  }

  isSavingGuardrails = true;
  if (elements.guardrailsSaveButton) elements.guardrailsSaveButton.disabled = true;
  setGuardrailsStatus("Saving...");
  try {
    const response = await fetch("/api/admin/guardrails", {
      method: "PUT",
      headers: adminAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ rules }),
    });
    const payload = await readJsonResponse(response);
    if (!response.ok) {
      throw new Error(formatApiError(payload.detail, "Unable to save guardrails."));
    }
    elements.guardrailsTextarea.value = payload.rules || rules;
    setGuardrailsStatus("Guardrails saved.", false, true);
  } catch (error) {
    setGuardrailsStatus(error.message || "Unable to save guardrails.", true);
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
