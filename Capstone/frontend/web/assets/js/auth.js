function bindAuth() {
  elements.accountAvatar.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleAccountPopover();
  });
  elements.accountActionButton.addEventListener("click", (event) => {
    event.stopPropagation();
    closeAccountPopover();
    if (state.session.role === "admin") {
      openLogoutModal();
      return;
    }
    openAuthModal();
  });

  elements.authCloseButton.addEventListener("click", closeAuthModal);
  elements.authModal.addEventListener("click", (event) => {
    if (event.target === elements.authModal) closeAuthModal();
  });
  elements.logoutCancelButton.addEventListener("click", closeLogoutModal);
  elements.logoutConfirmButton.addEventListener("click", logoutAdmin);
  elements.logoutModal.addEventListener("click", (event) => {
    if (event.target === elements.logoutModal) closeLogoutModal();
  });
  elements.formFillCloseButton.addEventListener("click", window.FormEditor.close);
  elements.formFillForm.addEventListener("submit", window.FormEditor.submit);
  elements.formFillClearDraftButton.addEventListener(
    "click",
    window.FormEditor.clearDraft,
  );
  elements.formFillModal.addEventListener("click", (event) => {
    if (event.target === elements.formFillModal) window.FormEditor.close();
  });
  elements.documentErrorCloseButton.addEventListener(
    "click",
    closeDocumentErrorModal,
  );
  elements.documentErrorModal.addEventListener("click", (event) => {
    if (event.target === elements.documentErrorModal) closeDocumentErrorModal();
  });
  elements.authForm.addEventListener("submit", handleAdminLogin);
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    closeAccountPopover();
    if (elements.authModal.classList.contains("is-open")) closeAuthModal();
    if (elements.logoutModal.classList.contains("is-open")) closeLogoutModal();
    if (elements.documentErrorModal.classList.contains("is-open")) {
      closeDocumentErrorModal();
    }
    if (elements.formFillModal.classList.contains("is-open")) {
      window.FormEditor.close();
    }
  });
  document.addEventListener("click", (event) => {
    if (elements.accountPanel.contains(event.target)) return;
    closeAccountPopover();
  });
  window.addEventListener("resize", window.FormEditor.handleResize);
}

function toggleAccountPopover() {
  if (elements.accountPopover.hidden) {
    openAccountPopover();
    return;
  }
  closeAccountPopover();
}

function openAccountPopover() {
  elements.accountPopover.hidden = false;
  elements.accountAvatar.setAttribute("aria-expanded", "true");
}

function closeAccountPopover() {
  elements.accountPopover.hidden = true;
  elements.accountAvatar.setAttribute("aria-expanded", "false");
}

function openAuthModal() {
  closeAccountPopover();
  clearAuthError();
  elements.authForm.reset();
  elements.authModal.classList.add("is-open");
  elements.authModal.setAttribute("aria-hidden", "false");
  elements.body.classList.add("auth-open");
  window.setTimeout(() => elements.adminEmail.focus(), 0);
}

function closeAuthModal() {
  elements.authModal.classList.remove("is-open");
  elements.authModal.setAttribute("aria-hidden", "true");
  elements.body.classList.remove("auth-open");
  clearAuthError();
}

function openLogoutModal() {
  closeAccountPopover();
  elements.logoutModal.classList.add("is-open");
  elements.logoutModal.setAttribute("aria-hidden", "false");
  elements.body.classList.add("logout-open");
  window.setTimeout(() => elements.logoutCancelButton.focus(), 0);
}

function closeLogoutModal() {
  elements.logoutModal.classList.remove("is-open");
  elements.logoutModal.setAttribute("aria-hidden", "true");
  elements.body.classList.remove("logout-open");
}

function openDocumentErrorModal(
  summary,
  failures = [],
  title = "Upload belum selesai",
) {
  elements.documentErrorTitle.textContent = title;
  elements.documentErrorSummary.textContent = summary;
  elements.documentErrorList.innerHTML = "";
  failures.forEach((failure) => {
    const item = document.createElement("li");
    const name = document.createElement("strong");
    name.textContent = failure.name || "Document";
    const reason = document.createElement("span");
    reason.textContent = failure.reason || "Upload failed.";
    item.append(name, reason);
    elements.documentErrorList.appendChild(item);
  });
  elements.documentErrorModal.classList.add("is-open");
  elements.documentErrorModal.setAttribute("aria-hidden", "false");
  elements.body.classList.add("document-error-open");
  window.setTimeout(() => elements.documentErrorCloseButton.focus(), 0);
}

window.openDocumentErrorModal = openDocumentErrorModal;

function closeDocumentErrorModal() {
  elements.documentErrorModal.classList.remove("is-open");
  elements.documentErrorModal.setAttribute("aria-hidden", "true");
  elements.body.classList.remove("document-error-open");
}

async function handleAdminLogin(event) {
  event.preventDefault();
  const email = elements.adminEmail.value.trim().toLowerCase();
  const password = elements.adminPassword.value;

  try {
    const response = await fetch("/api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const payload = await readJsonResponse(response);
    if (!response.ok) {
      throw new Error(
        formatApiError(
          payload.detail,
          "Email atau password admin belum cocok.",
        ),
      );
    }

    state.session = {
      role: "admin",
      email: payload.email || email,
      name: payload.name || "Admin",
      token: payload.token || "",
      expires_at: payload.expires_at || "",
    };
    if (!isAdminSession()) {
      throw new Error("Sesi admin tidak valid. Coba login ulang.");
    }
  } catch (error) {
    showAuthError(error.message || "Email atau password admin belum cocok.");
    elements.adminPassword.select();
    return;
  }

  window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(state.session));
  syncAuth();
  closeAuthModal();
  closeMobileNav();
}

function logoutAdmin() {
  state.session = {
    role: "guest",
    email: "",
    name: "Guest",
    token: "",
    expires_at: "",
  };
  clearDocumentUndo();
  window.localStorage.removeItem(AUTH_STORAGE_KEY);
  closeLogoutModal();
  syncAuth();
}

function syncAuth() {
  const isAdmin = isAdminSession();
  if (!isAdmin && state.session.role === "admin") {
    state.session = {
      role: "guest",
      email: "",
      name: "Guest",
      token: "",
      expires_at: "",
    };
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
  }
  elements.body.dataset.role = isAdmin ? "admin" : "guest";
  elements.accountAvatar.textContent = isAdmin ? "A" : "G";
  elements.accountRoleLabel.textContent = isAdmin
    ? "Admin mode"
    : "Guest access";
  elements.accountName.textContent = isAdmin
    ? state.session.name || state.session.email
    : "Guest";
  elements.accountHint.textContent = isAdmin ? "Admin" : "Login admin";
  elements.accountPopoverRole.textContent = isAdmin
    ? "Admin mode"
    : "Guest access";
  elements.accountPopoverName.textContent = isAdmin
    ? state.session.email || state.session.name
    : "Guest";
  elements.accountPopoverHint.textContent = isAdmin
    ? "Klik ikon kanan untuk logout."
    : "Klik ikon kanan untuk login admin.";
  elements.accountActionIcon.textContent = isAdmin ? "logout" : "login";
  elements.accountActionText.textContent = isAdmin ? "Logout" : "Admin login";
  elements.accountActionButton.setAttribute(
    "aria-label",
    isAdmin ? "Logout admin" : "Login admin",
  );
  if (elements.policyNavLink) elements.policyNavLink.hidden = !isAdmin;
  if (elements.logsNavLink) elements.logsNavLink.hidden = !isAdmin;
  if (!isAdmin && (state.activeScreen === "policy" || state.activeScreen === "logs")) {
    navigateTo("chat");
  }
  if (!isAdmin) resetFaqForm();
  clearDocumentStatus();
  syncReindexState();
  updateFaqControls();
  if (isAdmin) {
    void loadLibrary();
    void loadActivityLogs();
  } else {
    state.documents = [];
    state.activityLogs = [];
    state.activityLogSummary = null;
    state.logError = "";
    renderLibrary();
    renderActivityLogs();
  }
}

function showAuthError(message) {
  elements.authError.textContent = message;
  elements.authError.hidden = false;
}

function clearAuthError() {
  elements.authError.textContent = "";
  elements.authError.hidden = true;
}
