(function () {
  let state = null;
  let elements = null;
  let resizeTimeout = null;

  function api() {
    return window.AppApi;
  }

  function storage() {
    return window.AppStorage;
  }

  function setContext(context = {}) {
    state = context.state;
    elements = context.elements;
  }

  function authHeaders(extraHeaders = {}) {
    return api().authHeaders(state?.session, extraHeaders);
  }

  function setStatus(message = "", isError = false) {
    elements.formFillStatus.hidden = !message;
    elements.formFillStatus.textContent = message;
    elements.formFillStatus.classList.toggle("is-error", Boolean(message) && isError);
  }

  function renderNote(container, message) {
    container.innerHTML = "";
    const note = document.createElement("p");
    note.className = "form-fill-note";
    note.textContent = message;
    container.appendChild(note);
  }

  function scheduleDraftSave(pending, delay = 400) {
    if (!pending || !pending.path) return;
    window.clearTimeout(pending.draftTimer);
    pending.draftTimer = window.setTimeout(() => {
      pending.draftTimer = null;
      saveDraft(pending);
    }, delay);
  }

  function saveDraft(pending) {
    if (!pending || !elements?.formFillFields) return;
    const container =
      pending.mode === "schema" && elements.formFillForm
        ? elements.formFillForm
        : elements.formFillFields;
    const values = storage().serializeFormValues(
      pending.mode === "schema" ? pending.schema : null,
      container,
    );
    storage().saveFormDraft(pending.path, pending.label, values);
  }

  function restoreDraft(pending, schemaOrFields) {
    const draft = storage().getFormDraft(pending.path);
    if (!draft) return;
    const restored = storage().applyFormDraftValues(
      draft,
      schemaOrFields,
      pending.mode === "schema" && elements.formFillForm
        ? elements.formFillForm
        : elements.formFillFields,
    );
    return restored;
  }

  function clearDraft() {
    const pending = state?.pendingFormFill;
    if (!pending) return;
    window.clearTimeout(pending.draftTimer);
    pending.draftTimer = null;
    storage().clearFormDraft(pending.path);
    const container =
      pending.mode === "schema" && elements.formFillForm
        ? elements.formFillForm
        : elements.formFillFields;
    container
      .querySelectorAll("input:not([type='file']), textarea")
      .forEach((control) => {
        if (control.type === "checkbox") control.checked = false;
        else control.value = "";
      });
    syncAllPreviewValues(pending);
  }

  async function fetchSchema(path) {
    const response = await fetch(`/api/forms/schema?path=${encodeURIComponent(path)}`, {
      cache: "no-store",
      headers: authHeaders(),
    });
    if (response.status === 404) return null;

    const payload = await api().readJsonResponse(response);
    if (!response.ok) {
      throw new Error(api().formatApiError(payload.detail, "Gagal memuat schema form."));
    }
    return payload;
  }

  async function open(item, context = {}) {
    setContext(context);
    const path = api().formPathFromUrl(item.download_url);
    const pending = {
      path,
      label: item.label || item.name || "Form",
      downloadUrl: item.download_url || "",
      mode: "legacy",
      schema: null,
      fieldById: new Map(),
      activeFieldId: "",
      fieldElements: new Map(),
      overlayElements: new Map(),
      previewControlElements: new Map(),
      previewValueElements: new Map(),
      previewSignatureUrls: new Map(),
      renderVersion: 0,
      draftTimer: null,
    };

    state.pendingFormFill = pending;
    elements.formFillTitle.textContent = "Editor form PDF";
    elements.formFillSubtitle.textContent = "";
    setStatus("");
    resetOutputFormat();
    renderNote(elements.formFillPreview, "Memuat preview form...");
    renderNote(elements.formFillFields, "Memuat kolom form...");
    elements.formFillModal.classList.add("is-open");
    elements.formFillModal.setAttribute("aria-hidden", "false");

    try {
      const schema = await fetchSchema(path);
      if (state.pendingFormFill !== pending) return;

      if (schema) {
        pending.mode = "schema";
        pending.schema = schema;
        elements.formFillTitle.textContent = schema.title || "Editor form PDF";
        elements.formFillSubtitle.textContent = "";
        renderSchemaFormFields(pending);
        restoreDraft(pending, schema);
        await renderSchemaPreview(pending);
        const firstControl = elements.formFillPreview.querySelector(
          "input:not([type='file']), textarea",
        );
        if (firstControl) window.setTimeout(() => firstControl.focus(), 0);
        return;
      }

      const response = await fetch(`/api/forms/fields?path=${encodeURIComponent(path)}`, {
        cache: "no-store",
        headers: authHeaders(),
      });
      const payload = await api().readJsonResponse(response);
      if (!response.ok) {
        throw new Error(api().formatApiError(payload.detail, "Gagal memuat kolom form."));
      }
      if (state.pendingFormFill !== pending) return;
      const legacyFields = Array.isArray(payload.fields) ? payload.fields : [];
      elements.formFillSubtitle.textContent = "";
      renderLegacyFields(legacyFields, pending);
      restoreDraft(pending, legacyFields);
      renderNote(
        elements.formFillPreview,
        "Preview editor belum tersedia untuk template ini.",
      );
    } catch (error) {
      if (state.pendingFormFill !== pending) return;
      renderNote(elements.formFillFields, error.message || "Gagal memuat editor form.");
      renderNote(elements.formFillPreview, "Preview form belum bisa dimuat.");
      setStatus(error.message || "Gagal memuat editor form.", true);
    }
  }

  function groupSchemaFields(fields) {
    const sections = new Map();
    fields.forEach((field) => {
      const section = field.section || "Field";
      if (!sections.has(section)) {
        sections.set(section, { regular: [], groups: new Map() });
      }
      const layout = field.layout || {};
      if (layout.group_id) {
        const groups = sections.get(section).groups;
        if (!groups.has(layout.group_id)) {
          groups.set(layout.group_id, {
            id: layout.group_id,
            label: layout.group_label || section,
            kind: layout.kind || "table_cell",
            fields: [],
          });
        }
        groups.get(layout.group_id).fields.push(field);
      } else {
        sections.get(section).regular.push(field);
      }
    });
    return sections;
  }

  function findFieldControl(container, fieldId) {
    if (!container || !fieldId) return null;
    const escapedId = CSS.escape(fieldId);
    return container.querySelector(
      `input[data-field-id="${escapedId}"], textarea[data-field-id="${escapedId}"], [data-field-id="${escapedId}"] input, [data-field-id="${escapedId}"] textarea`,
    );
  }

  function getHiddenControl(fieldId) {
    return findFieldControl(elements.formFillFields, fieldId);
  }

  function getControl(fieldId) {
    return (
      state?.pendingFormFill?.previewControlElements?.get(fieldId) ||
      findFieldControl(elements.formFillForm, fieldId) ||
      getHiddenControl(fieldId)
    );
  }

  function hasFieldRect(field) {
    return (
      field &&
      field.rect &&
      Number.isFinite(Number(field.rect.x)) &&
      Number.isFinite(Number(field.rect.y)) &&
      Number.isFinite(Number(field.rect.width)) &&
      Number.isFinite(Number(field.rect.height)) &&
      field.page !== null &&
      field.page !== undefined
    );
  }

  function getOutputFormat() {
    return "docx";
  }

  function filenameFromFillResponse(response, fallback) {
    if (typeof api().filenameFromResponse === "function") {
      return api().filenameFromResponse(response, fallback);
    }

    const disposition = response?.headers?.get("content-disposition") || "";
    const encodedMatch = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (encodedMatch?.[1]) {
      try {
        return decodeURIComponent(encodedMatch[1]);
      } catch {
        return encodedMatch[1];
      }
    }

    const plainMatch = disposition.match(/filename="?([^";]+)"?/i);
    return plainMatch?.[1] || fallback;
  }

  function resetOutputFormat() {
    return "docx";
  }

  function revokeSignatureUrl(pending, fieldId) {
    const url = pending.previewSignatureUrls.get(fieldId);
    if (url) {
      URL.revokeObjectURL(url);
      pending.previewSignatureUrls.delete(fieldId);
    }
  }

  function syncPreviewValue(fieldId) {
    const pending = state.pendingFormFill;
    if (!pending) return;
    const field = pending.fieldById.get(fieldId);
    const previewElement = pending.previewValueElements.get(fieldId);
    if (!field || !previewElement) return;

    if (field.type === "signature_image") {
      const image = previewElement.querySelector("img");
      const file = getControl(fieldId)?.files?.[0];
      revokeSignatureUrl(pending, fieldId);
      if (file && image) {
        const url = URL.createObjectURL(file);
        pending.previewSignatureUrls.set(fieldId, url);
        image.src = url;
        image.alt = field.label;
        previewElement.hidden = false;
        previewElement.classList.add("has-value");
        pending.overlayElements.get(fieldId)?.classList.add("has-value");
      } else if (image) {
        image.removeAttribute("src");
        image.alt = "";
        previewElement.hidden = true;
        previewElement.classList.remove("has-value");
        pending.overlayElements.get(fieldId)?.classList.remove("has-value");
      }
      return;
    }

    const control = getControl(fieldId);
    if (!control) return;
    const value = field.type === "checkbox" ? (control.checked ? "X" : "") : control.value || "";
    const hasPreviewControl = state.pendingFormFill?.previewControlElements?.has(fieldId);
    previewElement.textContent = hasPreviewControl ? "" : value;
    previewElement.hidden = !value;
    previewElement.classList.toggle("has-value", Boolean(value));
    state.pendingFormFill?.overlayElements
      ?.get(fieldId)
      ?.classList.toggle("has-value", Boolean(value));
  }

  function syncAllPreviewValues(pending) {
    pending.fieldById.forEach((_field, fieldId) => {
      syncPreviewValue(fieldId);
    });
  }

  function syncChoiceGroup(field) {
    const choiceGroup = field?.layout?.choice_group;
    if (!choiceGroup) return;
    state.pendingFormFill?.fieldById.forEach((candidate) => {
      if (candidate?.layout?.choice_group === choiceGroup) {
        syncPreviewValue(candidate.id);
      }
    });
  }

  function syncHiddenControl(field, control) {
    const hiddenControl = getHiddenControl(field.id);
    if (!hiddenControl || hiddenControl === control || field.type === "signature_image") {
      return;
    }
    if (field.type === "checkbox") {
      hiddenControl.checked = Boolean(control.checked);
      return;
    }
    hiddenControl.value = control.value || "";
  }

  function getFieldIdFromEventTarget(target) {
    if (!target || !(target instanceof HTMLElement)) return "";
    return target.dataset.fieldId || target.closest("[data-field-id]")?.dataset.fieldId || "";
  }

  function getNavigableSchemaFields(pending) {
    const fields = Array.isArray(pending?.schema?.fields) ? pending.schema.fields : [];
    return fields
      .filter((field) => {
        const control = pending.previewControlElements.get(field.id);
        return control && field.type !== "signature_image" && !control.disabled;
      })
      .sort((left, right) => {
        const leftHasRect = hasFieldRect(left);
        const rightHasRect = hasFieldRect(right);
        if (leftHasRect !== rightHasRect) return leftHasRect ? -1 : 1;
        const pageDelta = Number(left.page || 0) - Number(right.page || 0);
        if (pageDelta) return pageDelta;
        const yDelta = Number(left.rect?.y || 0) - Number(right.rect?.y || 0);
        if (Math.abs(yDelta) > 1) return yDelta;
        const xDelta = Number(left.rect?.x || 0) - Number(right.rect?.x || 0);
        if (xDelta) return xDelta;
        return String(left.label || "").localeCompare(String(right.label || ""));
      });
  }

  function focusSchemaFieldByOffset(currentFieldId, offset) {
    const pending = state?.pendingFormFill;
    if (!pending || pending.mode !== "schema") return false;
    const fields = getNavigableSchemaFields(pending);
    if (!fields.length) return false;
    const currentIndex = fields.findIndex((field) => field.id === currentFieldId);
    if (currentIndex < 0) return false;

    const nextIndex = currentIndex + offset;
    if (nextIndex < 0 || nextIndex >= fields.length) {
      return true;
    }
    setActiveField(fields[nextIndex].id, { focus: true });
    return true;
  }

  function focusLegacyFieldByOffset(target, offset) {
    const controls = Array.from(
      elements.formFillFields.querySelectorAll("input[data-key]"),
    ).filter((control) => !control.disabled);
    const currentIndex = controls.indexOf(target);
    if (currentIndex < 0) return false;
    const nextControl = controls[currentIndex + offset];
    if (nextControl) nextControl.focus();
    return true;
  }

  function handleKeydown(event) {
    if (event.key !== "Enter" || event.isComposing) return;
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (!target.matches("input, textarea")) return;
    if (target.type === "file" || target.type === "submit" || target.type === "button") {
      return;
    }

    const pending = state?.pendingFormFill;
    if (!pending) return;
    const offset = event.shiftKey ? -1 : 1;
    const handled =
      pending.mode === "schema"
        ? focusSchemaFieldByOffset(getFieldIdFromEventTarget(target), offset)
        : focusLegacyFieldByOffset(target, offset);

    if (handled) {
      event.preventDefault();
      event.stopPropagation();
    }
  }

  function scrollFieldIntoView(fieldElement, { smooth = true } = {}) {
    if (fieldElement?.closest?.("#formFillPreview")) {
      fieldElement.scrollIntoView({
        block: "center",
        inline: "nearest",
        behavior: smooth ? "smooth" : "auto",
      });
      return;
    }

    const container = elements.formFillFields;
    if (!container || !fieldElement) return;

    const containerRect = container.getBoundingClientRect();
    const fieldRect = fieldElement.getBoundingClientRect();
    const centeredTop =
      container.scrollTop +
      fieldRect.top -
      containerRect.top -
      Math.max((container.clientHeight - fieldRect.height) / 2, 28);

    container.scrollTo({
      top: Math.max(0, centeredTop),
      behavior: smooth ? "smooth" : "auto",
    });
  }

  function setActiveField(fieldId, { focus = false, smooth = true } = {}) {
    const pending = state.pendingFormFill;
    if (!pending || !fieldId) return;
    pending.activeFieldId = fieldId;

    pending.fieldElements.forEach((element, id) => {
      element.classList.toggle("is-active", id === fieldId);
    });
    pending.overlayElements.forEach((element, id) => {
      element.classList.toggle("is-active", id === fieldId);
    });

    const fieldElement = pending.fieldElements.get(fieldId);
    scrollFieldIntoView(fieldElement, { smooth });
    const previewControl = pending.previewControlElements.get(fieldId);
    if (focus && previewControl) {
      previewControl.focus({ preventScroll: true });
    } else if (focus && fieldElement) {
      fieldElement.querySelector("input, textarea")?.focus({ preventScroll: true });
    }

    pending.overlayElements.get(fieldId)?.scrollIntoView({
      block: "center",
      inline: "center",
      behavior: smooth ? "smooth" : "auto",
    });
  }

  function handleControlChange(field) {
    syncPreviewValue(field.id);
    syncChoiceGroup(field);
    scheduleDraftSave(state.pendingFormFill);
  }

  function createSchemaFieldElement(field, pending) {
    const wrapper = document.createElement("div");
    wrapper.className = "form-editor-field";
    wrapper.dataset.fieldId = field.id;
    wrapper.dataset.fieldType = field.type;

    const heading = document.createElement("div");
    heading.className = "form-editor-field-label";
    const labelText = document.createElement("span");
    labelText.textContent = field.label;
    heading.appendChild(labelText);
    wrapper.appendChild(heading);

    if (field.placeholder) {
      const hint = document.createElement("p");
      hint.className = "form-editor-field-hint";
      hint.textContent = field.placeholder;
      wrapper.appendChild(hint);
    }

    let control;
    if (field.type === "textarea") {
      control = document.createElement("textarea");
      control.rows = 4;
      wrapper.appendChild(control);
    } else if (field.type === "date") {
      control = document.createElement("input");
      control.type = "text";
      wrapper.appendChild(control);
    } else if (field.type === "checkbox") {
      const row = document.createElement("label");
      row.className = "form-editor-checkbox";
      control = document.createElement("input");
      control.type = field.layout?.choice_group ? "radio" : "checkbox";
      if (field.layout?.choice_group) {
        control.name = field.layout.choice_group;
        control.value = field.id;
      }
      const description = document.createElement("span");
      description.textContent = field.layout?.column_label || "Centang untuk menandai field ini.";
      row.append(control, description);
      wrapper.appendChild(row);
    } else if (field.type === "signature_image") {
      control = document.createElement("input");
      control.type = "file";
      control.accept = "image/png,image/jpeg";
      const meta = document.createElement("div");
      meta.className = "form-editor-file-meta";
      meta.textContent = "Upload file PNG atau JPEG.";
      wrapper.append(control, meta);
      control.addEventListener("change", () => {
        const file = control.files?.[0];
        meta.textContent = file
          ? `${file.name} - ${Math.max(1, Math.round(file.size / 1024))} KB`
          : "Upload file PNG atau JPEG.";
        setActiveField(field.id, { smooth: false });
        syncPreviewValue(field.id);
      });
    } else {
      control = document.createElement("input");
      control.type = "text";
      wrapper.appendChild(control);
    }

    if (control && field.type !== "checkbox" && field.type !== "signature_image") {
      control.placeholder = field.placeholder || "";
    }

    if (control) {
      control.name = field.id;
      control.dataset.fieldId = field.id;
      const hiddenControl = getHiddenControl(field.id);
      if (hiddenControl && hiddenControl !== control && field.type !== "signature_image") {
        if (field.type === "checkbox") {
          control.checked = Boolean(hiddenControl.checked);
        } else {
          control.value = hiddenControl.value || "";
        }
      }
      control.addEventListener("focus", () => setActiveField(field.id, { smooth: false }));
      control.addEventListener("click", () => setActiveField(field.id, { smooth: false }));
      if (field.type === "checkbox") {
        control.addEventListener("change", () => {
          setActiveField(field.id, { smooth: false });
          syncHiddenControl(field, control);
          handleControlChange(field);
        });
      } else if (field.type !== "signature_image") {
        control.addEventListener("input", () => {
          syncHiddenControl(field, control);
          handleControlChange(field);
        });
        control.addEventListener("change", () => {
          syncHiddenControl(field, control);
          handleControlChange(field);
        });
      }
    }

    wrapper.addEventListener("click", () => setActiveField(field.id, { focus: false }));
    pending.fieldElements.set(field.id, wrapper);
    return wrapper;
  }

  function createChoiceMatrixElement(group, pending) {
    const wrapper = document.createElement("div");
    wrapper.className = "form-layout-group is-choice-matrix";

    const title = document.createElement("h4");
    title.className = "form-layout-group-title";
    title.textContent = group.label || "Pilihan";
    wrapper.appendChild(title);

    const rows = new Map();
    const columns = [];
    group.fields.forEach((field) => {
      const layout = field.layout || {};
      const rowLabel = layout.row_label || field.label;
      const columnLabel = layout.column_label || field.label;
      if (!rows.has(rowLabel)) rows.set(rowLabel, []);
      rows.get(rowLabel).push(field);
      if (!columns.includes(columnLabel)) columns.push(columnLabel);
    });

    const table = document.createElement("div");
    table.className = "form-choice-matrix";
    table.style.gridTemplateColumns = `minmax(170px, 1.8fr) repeat(${columns.length}, minmax(96px, 1fr))`;

    const empty = document.createElement("div");
    empty.className = "form-choice-matrix-header";
    table.appendChild(empty);
    columns.forEach((column) => {
      const header = document.createElement("div");
      header.className = "form-choice-matrix-header";
      header.textContent = column;
      table.appendChild(header);
    });

    rows.forEach((rowFields, rowLabel) => {
      const rowHeading = document.createElement("div");
      rowHeading.className = "form-choice-matrix-row-label";
      rowHeading.textContent = rowLabel;
      table.appendChild(rowHeading);
      columns.forEach((column) => {
        const field = rowFields.find((candidate) => candidate.layout?.column_label === column);
        const cell = document.createElement("label");
        cell.className = "form-choice-matrix-cell";
        if (field) {
          cell.dataset.fieldId = field.id;
          cell.dataset.fieldType = field.type;
          const control = document.createElement("input");
          control.type = "radio";
          control.name = field.layout.choice_group || `${group.id}-${rowLabel}`;
          control.value = field.id;
          control.dataset.fieldId = field.id;
          control.addEventListener("focus", () => setActiveField(field.id, { smooth: false }));
          control.addEventListener("click", () => setActiveField(field.id, { smooth: false }));
          control.addEventListener("change", () => {
            setActiveField(field.id, { smooth: false });
            handleControlChange(field);
          });
          const mark = document.createElement("span");
          mark.className = "form-choice-matrix-mark";
          mark.textContent = column;
          cell.append(control, mark);
          cell.addEventListener("click", () => setActiveField(field.id, { focus: false }));
          pending.fieldElements.set(field.id, cell);
        }
        table.appendChild(cell);
      });
    });

    wrapper.appendChild(table);
    return wrapper;
  }

  function createTableGroupElement(group, pending) {
    const wrapper = document.createElement("div");
    wrapper.className = "form-layout-group is-table";

    const title = document.createElement("h4");
    title.className = "form-layout-group-title";
    title.textContent = group.label || "Tabel";
    wrapper.appendChild(title);

    const rows = new Map();
    const columns = [];
    group.fields.forEach((field) => {
      const layout = field.layout || {};
      const rowLabel = layout.row_label || field.label;
      const columnLabel = layout.column_label || field.label;
      if (!rows.has(rowLabel)) rows.set(rowLabel, []);
      rows.get(rowLabel).push(field);
      if (!columns.includes(columnLabel)) columns.push(columnLabel);
    });

    const table = document.createElement("div");
    table.className = "form-table-group";
    table.style.gridTemplateColumns = `minmax(160px, 1.6fr) repeat(${columns.length}, minmax(120px, 1fr))`;

    table.appendChild(document.createElement("div"));
    columns.forEach((column) => {
      const header = document.createElement("div");
      header.className = "form-table-group-header";
      header.textContent = column;
      table.appendChild(header);
    });

    rows.forEach((rowFields, rowLabel) => {
      const rowHeading = document.createElement("div");
      rowHeading.className = "form-table-group-row-label";
      rowHeading.textContent = rowLabel;
      table.appendChild(rowHeading);
      columns.forEach((column) => {
        const cell = document.createElement("div");
        cell.className = "form-table-group-cell";
        const field = rowFields.find((candidate) => candidate.layout?.column_label === column);
        if (field) {
          cell.appendChild(createSchemaFieldElement(field, pending));
        }
        table.appendChild(cell);
      });
    });

    wrapper.appendChild(table);
    return wrapper;
  }

  function createLayoutGroupElement(group, pending) {
    if (group.kind === "choice_matrix") {
      return createChoiceMatrixElement(group, pending);
    }
    return createTableGroupElement(group, pending);
  }

  function renderSchemaFormFields(pending) {
    pending.fieldElements = new Map();
    pending.fieldById = new Map();
    elements.formFillFields.innerHTML = "";
    const fields = Array.isArray(pending.schema?.fields) ? pending.schema.fields : [];
    if (!fields.length) {
      renderNote(elements.formFillFields, "Schema form tidak punya field.");
      return;
    }

    fields.forEach((field) => pending.fieldById.set(field.id, field));

    groupSchemaFields(fields).forEach((sectionFields, sectionName) => {
      const section = document.createElement("section");
      section.className = "form-fields-section";

      const title = document.createElement("h3");
      title.className = "form-fields-section-title";
      title.textContent = sectionName;
      section.appendChild(title);

      if (sectionFields.regular.length) {
        const grid = document.createElement("div");
        grid.className = "form-field-grid";
        sectionFields.regular.forEach((field) => {
          grid.appendChild(createSchemaFieldElement(field, pending));
        });
        section.appendChild(grid);
      }
      sectionFields.groups.forEach((group) => {
        section.appendChild(createLayoutGroupElement(group, pending));
      });
      elements.formFillFields.appendChild(section);
    });
  }

  function renderLegacyFields(fields, pending) {
    elements.formFillFields.innerHTML = "";
    if (!fields.length) {
      renderNote(elements.formFillFields, "Form ini tidak punya kolom isian yang terdeteksi.");
      return;
    }
    fields.forEach((field) => {
      const label = document.createElement("label");
      const span = document.createElement("span");
      span.textContent = field.label;
      const input = document.createElement("input");
      input.type = "text";
      input.dataset.key = field.key;
      input.addEventListener("input", () => scheduleDraftSave(pending));
      input.addEventListener("change", () => scheduleDraftSave(pending));
      label.append(span, input);
      elements.formFillFields.appendChild(label);
    });
    const firstInput = elements.formFillFields.querySelector("input");
    if (firstInput) window.setTimeout(() => firstInput.focus(), 0);
  }

  function togglePreviewCheckbox(field) {
    const control = getControl(field.id);
    if (!control) return;
    if (field.layout?.choice_group) {
      control.checked = true;
    } else {
      control.checked = !control.checked;
    }
    setActiveField(field.id, { focus: false });
    syncPreviewValue(field.id);
    syncChoiceGroup(field);
    scheduleDraftSave(state.pendingFormFill);
  }

  function positionPreviewElement(element, field, scale) {
    element.style.left = `${Number(field.rect.x) * scale}px`;
    element.style.top = `${Number(field.rect.y) * scale}px`;
    element.style.width = `${Number(field.rect.width) * scale}px`;
    element.style.height = `${Number(field.rect.height) * scale}px`;
  }

  function createPreviewFieldElement(field, pending, scale) {
    const wrapper = document.createElement(field.type === "signature_image" ? "label" : "div");
    wrapper.className = "form-preview-field";
    wrapper.dataset.fieldId = field.id;
    wrapper.dataset.fieldType = field.type;
    wrapper.title = field.label;
    positionPreviewElement(wrapper, field, scale);
    wrapper.style.fontSize = `${Math.max(8, Number(field.font_size || 10) * scale)}px`;
    wrapper.style.lineHeight = `${field.line_height || 1.08}`;

    let control;
    if (field.type === "textarea") {
      control = document.createElement("textarea");
      control.rows = 1;
    } else {
      control = document.createElement("input");
      if (field.type === "checkbox") {
        control.type = field.layout?.choice_group ? "radio" : "checkbox";
      } else if (field.type === "signature_image") {
        control.type = "file";
        control.accept = "image/png,image/jpeg";
      } else {
        control.type = "text";
      }
    }

    control.name = field.layout?.choice_group || field.id;
    control.dataset.fieldId = field.id;
    control.title = field.label;
    if (field.type !== "checkbox" && field.type !== "signature_image") {
      control.placeholder = field.placeholder || field.label || "";
    }
    if (field.layout?.choice_group) {
      control.value = field.id;
    }

    const hiddenControl = getHiddenControl(field.id);
    if (hiddenControl && field.type !== "signature_image") {
      if (field.type === "checkbox") control.checked = Boolean(hiddenControl.checked);
      else control.value = hiddenControl.value || "";
    }

    control.addEventListener("focus", () => setActiveField(field.id, { smooth: false }));
    control.addEventListener("click", () => setActiveField(field.id, { smooth: false }));

    if (field.type === "checkbox") {
      control.addEventListener("change", () => {
        syncHiddenControl(field, control);
        handleControlChange(field);
      });
    } else if (field.type === "signature_image") {
      control.addEventListener("change", () => {
        setActiveField(field.id, { smooth: false });
        syncPreviewValue(field.id);
      });
    } else {
      control.addEventListener("input", () => {
        syncHiddenControl(field, control);
        handleControlChange(field);
      });
      control.addEventListener("change", () => {
        syncHiddenControl(field, control);
        handleControlChange(field);
      });
    }

    if (field.type === "signature_image") {
      const label = document.createElement("span");
      label.className = "form-preview-field-file-label";
      label.textContent = "Upload";
      wrapper.append(label, control);
    } else {
      wrapper.appendChild(control);
    }

    pending.previewControlElements.set(field.id, control);
    return wrapper;
  }

  async function renderSchemaPreview(pending) {
    if (!window.pdfjsLib?.getDocument) {
      renderNote(elements.formFillPreview, "Library preview PDF tidak tersedia di browser ini.");
      return;
    }

    const renderVersion = pending.renderVersion + 1;
    pending.renderVersion = renderVersion;
    pending.overlayElements = new Map();
    pending.previewControlElements = new Map();
    pending.previewValueElements = new Map();
    renderNote(elements.formFillPreview, "Memuat preview PDF...");

    try {
      const response = await fetch(pending.downloadUrl, {
        cache: "no-store",
        headers: authHeaders(),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const pdfBytes = new Uint8Array(await response.arrayBuffer());
      const pdf = await window.pdfjsLib.getDocument({ data: pdfBytes }).promise;
      if (state.pendingFormFill !== pending || pending.renderVersion !== renderVersion) {
        return;
      }

      elements.formFillPreview.innerHTML = "";
      const pages = Array.isArray(pending.schema?.pages) ? pending.schema.pages : [];
      const widestPage = Math.max(
        ...(pages.length ? pages.map((page) => Number(page.width) || 612) : [612]),
      );
      const containerWidth = Math.max(elements.formFillPreview.clientWidth - 28, 280);
      const scale = Math.min(1.5, containerWidth / widestPage);
      const outputScale = window.devicePixelRatio || 1;

      for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
        const page = await pdf.getPage(pageNumber);
        const viewport = page.getViewport({ scale });

        const pageElement = document.createElement("div");
        pageElement.className = "form-preview-page";
        pageElement.style.width = `${viewport.width}px`;

        const canvas = document.createElement("canvas");
        canvas.width = Math.floor(viewport.width * outputScale);
        canvas.height = Math.floor(viewport.height * outputScale);
        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;
        pageElement.appendChild(canvas);

        const overlay = document.createElement("div");
        overlay.className = "form-preview-overlay";
        pageElement.appendChild(overlay);
        elements.formFillPreview.appendChild(pageElement);

        await page.render({
          canvasContext: canvas.getContext("2d"),
          viewport,
          transform:
            outputScale === 1 ? null : [outputScale, 0, 0, outputScale, 0, 0],
        }).promise;

        const pageFields = (pending.schema?.fields || []).filter(
          (field) => hasFieldRect(field) && Number(field.page) === pageNumber - 1,
        );
        pageFields.forEach((field) => {
          const valueElement = document.createElement("div");
          valueElement.className = "form-preview-field-value";
          valueElement.classList.add(`is-${field.type.replace("_", "-")}`);
          valueElement.classList.add(`is-${field.align || "left"}`);
          if (field.clear !== false) valueElement.classList.add("is-clearing");
          positionPreviewElement(valueElement, field, scale);
          valueElement.style.setProperty(
            "--form-clear-padding",
            `${Math.max(0, Number(field.clear_padding ?? 1)) * scale}px`,
          );
          valueElement.style.fontSize = `${Math.max(
            8,
            Number(field.font_size || 10) * scale,
          )}px`;
          valueElement.style.lineHeight = `${field.line_height || 1.08}`;
          valueElement.hidden = true;
          if (field.type === "signature_image") {
            valueElement.appendChild(document.createElement("img"));
          }
          overlay.appendChild(valueElement);
          pending.previewValueElements.set(field.id, valueElement);

          const previewField = createPreviewFieldElement(field, pending, scale);
          overlay.appendChild(previewField);
          pending.overlayElements.set(field.id, previewField);
        });
      }
      if ((pending.schema?.fields || []).length) {
        syncAllPreviewValues(pending);
        setActiveField(pending.activeFieldId || pending.schema.fields[0].id, {
          smooth: false,
        });
      }
    } catch (error) {
      if (state.pendingFormFill !== pending || pending.renderVersion !== renderVersion) {
        return;
      }
      renderNote(
        elements.formFillPreview,
        "Preview PDF belum bisa dimuat, tapi field form tetap bisa diisi.",
      );
      setStatus(error.message || "Preview PDF belum bisa dimuat.", true);
    }
  }

  function close({ flushDraft = true } = {}) {
    if (!state || !elements) return;
    const pending = state.pendingFormFill;
    if (pending) {
      const hasPendingDraftSave = Boolean(pending.draftTimer);
      window.clearTimeout(pending.draftTimer);
      pending.draftTimer = null;
      if (flushDraft && hasPendingDraftSave) saveDraft(pending);
      pending.previewSignatureUrls.forEach((url) => URL.revokeObjectURL(url));
    }
    state.pendingFormFill = null;
    elements.formFillModal.classList.remove("is-open");
    elements.formFillModal.setAttribute("aria-hidden", "true");
    elements.formFillTitle.textContent = "Editor form PDF";
    elements.formFillSubtitle.textContent = "";
    setStatus("");
    elements.formFillPreview.innerHTML = "";
    elements.formFillFields.innerHTML = "";
  }

  function handleResize() {
    const pending = state?.pendingFormFill;
    if (!pending || pending.mode !== "schema" || !pending.schema) return;
    window.clearTimeout(resizeTimeout);
    resizeTimeout = window.setTimeout(() => {
      if (state.pendingFormFill === pending) {
        renderSchemaPreview(pending);
      }
    }, 120);
  }

  async function submit(event) {
    event.preventDefault();
    const pending = state.pendingFormFill;
    if (!pending) return;
    const outputFormat = getOutputFormat();

    try {
      let response;
      if (pending.mode === "schema" && pending.schema) {
        const formData = new FormData();
        const values = {};
        (pending.schema.fields || []).forEach((field) => {
          const control = getControl(field.id);
          if (!control) return;
          if (field.type === "signature_image") {
            const file = control.files?.[0];
            if (file) formData.append(field.id, file);
            return;
          }
          values[field.id] = field.type === "checkbox" ? Boolean(control.checked) : control.value.trim();
        });
        formData.append(
          "payload",
          JSON.stringify({ path: pending.path, values, output_format: outputFormat }),
        );
        response = await fetch("/api/forms/fill", {
          method: "POST",
          headers: authHeaders(),
          body: formData,
        });
      } else {
        const values = {};
        elements.formFillFields.querySelectorAll("input[data-key]").forEach((input) => {
          values[input.dataset.key] = input.value.trim();
        });
        response = await fetch("/api/forms/fill", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            path: pending.path,
            values,
            output_format: outputFormat,
          }),
        });
      }

      if (!response.ok) {
        const payload = await api().readJsonResponse(response);
        throw new Error(api().formatApiError(payload.detail, "Gagal mengisi form."));
      }
      const blob = await response.blob();
      const filename = filenameFromFillResponse(
        response,
        `${pending.label}.docx`,
      );
      api().downloadBlob(blob, filename);
      storage().clearFormDraft(pending.path);
      close({ flushDraft: false });
    } catch (error) {
      window.openDocumentErrorModal?.(
        error.message || "Gagal mengisi form.",
        [],
        "Form gagal diisi",
      );
    }
  }

  window.FormEditor = {
    open,
    close,
    submit,
    handleKeydown,
    handleResize,
    clearDraft,
  };
})();
