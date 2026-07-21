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
  elements.newAdminButton.addEventListener("click", (event) => {
    event.stopPropagation();
    closeAccountPopover();
    openNewAdminModal();
  });

  elements.authCloseButton.addEventListener("click", closeAuthModal);
  elements.authModal.addEventListener("click", (event) => {
    if (event.target === elements.authModal) closeAuthModal();
  });
  elements.newAdminCloseButton.addEventListener("click", closeNewAdminModal);
  elements.newAdminModal.addEventListener("click", (event) => {
    if (event.target === elements.newAdminModal) closeNewAdminModal();
  });
  elements.logoutCancelButton.addEventListener("click", closeLogoutModal);
  elements.logoutConfirmButton.addEventListener("click", logoutAdmin);
  elements.logoutModal.addEventListener("click", (event) => {
    if (event.target === elements.logoutModal) closeLogoutModal();
  });
  elements.documentErrorCloseButton.addEventListener(
    "click",
    closeDocumentErrorModal,
  );
  elements.documentErrorModal.addEventListener("click", (event) => {
    if (event.target === elements.documentErrorModal) closeDocumentErrorModal();
  });
  elements.authForm.addEventListener("submit", handleAdminLogin);
  elements.newAdminForm.addEventListener("submit", handleNewAdminSubmit);
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    closeAccountPopover();
    if (elements.authModal.classList.contains("is-open")) closeAuthModal();
    if (elements.newAdminModal.classList.contains("is-open")) {
      closeNewAdminModal();
    }
    if (elements.logoutModal.classList.contains("is-open")) closeLogoutModal();
    if (elements.documentErrorModal.classList.contains("is-open")) {
      closeDocumentErrorModal();
    }
    if (elements.templateDownloadModal?.classList.contains("is-open")) {
      window.closeTemplateDownloadModal?.();
    }
  });
  document.addEventListener("click", (event) => {
    if (elements.accountPanel.contains(event.target)) return;
    closeAccountPopover();
  });
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

function openNewAdminModal() {
  if (!isAdminSession()) {
    openAuthModal();
    return;
  }
  clearNewAdminStatus();
  elements.newAdminForm.reset();
  elements.newAdminModal.classList.add("is-open");
  elements.newAdminModal.setAttribute("aria-hidden", "false");
  elements.body.classList.add("new-admin-open");
  window.setTimeout(() => elements.newAdminName.focus(), 0);
}

function closeNewAdminModal() {
  elements.newAdminModal.classList.remove("is-open");
  elements.newAdminModal.setAttribute("aria-hidden", "true");
  elements.body.classList.remove("new-admin-open");
  clearNewAdminStatus();
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

async function handleNewAdminSubmit(event) {
  event.preventDefault();
  if (!isAdminSession()) {
    showNewAdminStatus("Sesi admin tidak valid. Login ulang dulu.", true);
    return;
  }

  const payload = {
    name: elements.newAdminName.value.trim() || "Admin",
    email: elements.newAdminEmail.value.trim().toLowerCase(),
    password: elements.newAdminPassword.value,
  };

  try {
    const response = await fetch("/api/admin/admins", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${state.session.token}`,
      },
      body: JSON.stringify(payload),
    });
    const data = await readJsonResponse(response);
    if (!response.ok) {
      throw new Error(formatApiError(data.detail, "Admin baru belum tersimpan."));
    }

    elements.newAdminForm.reset();
    showNewAdminStatus(`Admin ${data.email || payload.email} tersimpan.`, false);
  } catch (error) {
    showNewAdminStatus(error.message || "Admin baru belum tersimpan.", true);
    elements.newAdminPassword.select();
  }
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
  elements.newAdminButton.hidden = !isAdmin;
  elements.accountActionIcon.textContent = isAdmin ? "logout" : "login";
  elements.accountActionText.textContent = isAdmin ? "Logout" : "Admin login";
  elements.accountActionButton.setAttribute(
    "aria-label",
    isAdmin ? "Logout admin" : "Login admin",
  );
  if (elements.policyNavLink) elements.policyNavLink.hidden = false;
  if (elements.logsNavLink) elements.logsNavLink.hidden = !isAdmin;
  if (!isAdmin && state.activeScreen === "logs") {
    navigateTo("chat");
  }
  if (!isAdmin) resetFaqForm();
  clearDocumentStatus();
  syncReindexState();
  updateFaqControls();
  void loadLibrary();
  if (isAdmin) {
    void loadActivityLogs();
  } else {
    state.activityLogs = [];
    state.activityLogSummary = null;
    state.logError = "";
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

function showNewAdminStatus(message, isError) {
  elements.newAdminStatus.textContent = message;
  elements.newAdminStatus.hidden = false;
  elements.newAdminStatus.classList.toggle("is-success", !isError);
}

function clearNewAdminStatus() {
  elements.newAdminStatus.textContent = "";
  elements.newAdminStatus.hidden = true;
  elements.newAdminStatus.classList.remove("is-success");
}
