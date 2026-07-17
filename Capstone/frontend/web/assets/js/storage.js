(function () {
  const FORM_DRAFT_PREFIX = "ics-hr-ai-form-draft-v1:";

  function draftKey(path) {
    return `${FORM_DRAFT_PREFIX}${encodeURIComponent(path || "")}`;
  }

  function getFormDraft(path) {
    const raw = window.localStorage.getItem(draftKey(path));
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw);
      if (!parsed || parsed.path !== path || typeof parsed.values !== "object") {
        return null;
      }
      return parsed;
    } catch {
      return null;
    }
  }

  function parseDraft(raw, expectedPath = "") {
    try {
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed.path !== "string" || typeof parsed.values !== "object") {
        return null;
      }
      if (expectedPath && parsed.path !== expectedPath) return null;
      return parsed;
    } catch {
      return null;
    }
  }

  function emitDraftChange() {
    window.dispatchEvent(new CustomEvent("formdraftschange"));
  }

  function saveFormDraft(path, label, values) {
    const payload = {
      path,
      label: label || "Form",
      updated_at: new Date().toISOString(),
      values: values || {},
    };
    window.localStorage.setItem(draftKey(path), JSON.stringify(payload));
    emitDraftChange();
    return payload;
  }

  function clearFormDraft(path) {
    window.localStorage.removeItem(draftKey(path));
    emitDraftChange();
  }

  function listFormDrafts() {
    const drafts = [];
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const key = window.localStorage.key(index);
      if (!key?.startsWith(FORM_DRAFT_PREFIX)) continue;
      const draft = parseDraft(window.localStorage.getItem(key));
      if (draft) drafts.push(draft);
    }
    return drafts.sort((left, right) =>
      String(right.updated_at || "").localeCompare(String(left.updated_at || "")),
    );
  }

  function serializeSchemaValues(schema, container) {
    const values = {};
    (schema?.fields || []).forEach((field) => {
      const fieldId = CSS.escape(field.id);
      const control = container.querySelector(
        `input[data-field-id="${fieldId}"], textarea[data-field-id="${fieldId}"], [data-field-id="${fieldId}"] input, [data-field-id="${fieldId}"] textarea`,
      );
      if (!control || field.type === "signature_image") return;
      values[field.id] =
        field.type === "checkbox" ? Boolean(control.checked) : control.value;
    });
    return values;
  }

  function serializeLegacyValues(container) {
    const values = {};
    container.querySelectorAll("input[data-key]").forEach((input) => {
      values[input.dataset.key] = input.value;
    });
    return values;
  }

  function serializeFormValues(schema, container) {
    return schema ? serializeSchemaValues(schema, container) : serializeLegacyValues(container);
  }

  function applyFormDraftValues(draft, schemaOrFields, container) {
    if (!draft?.values || !container) return false;
    const values = draft.values;
    if (schemaOrFields?.fields) {
      schemaOrFields.fields.forEach((field) => {
        if (field.type === "signature_image" || !(field.id in values)) return;
        const fieldId = CSS.escape(field.id);
        const control = container.querySelector(
          `input[data-field-id="${fieldId}"], textarea[data-field-id="${fieldId}"], [data-field-id="${fieldId}"] input, [data-field-id="${fieldId}"] textarea`,
        );
        if (!control) return;
        if (field.type === "checkbox") {
          control.checked = Boolean(values[field.id]);
        } else {
          control.value = String(values[field.id] ?? "");
        }
      });
      return true;
    }

    Object.entries(values).forEach(([key, value]) => {
      const input = container.querySelector(`input[data-key="${CSS.escape(key)}"]`);
      if (input) input.value = String(value ?? "");
    });
    return true;
  }

  window.AppStorage = {
    getFormDraft,
    listFormDrafts,
    saveFormDraft,
    clearFormDraft,
    serializeFormValues,
    applyFormDraftValues,
  };
})();
