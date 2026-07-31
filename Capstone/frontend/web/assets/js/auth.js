function bindAuth() {
  elements.accountAvatar.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleAccountPopover();
  });
  elements.accountActionButton.addEventListener("click", (event) => {
    event.stopPropagation();
    closeAccountPopover();
    openLogoutModal();
  });
  elements.newAdminButton.addEventListener("click", (event) => {
    event.stopPropagation();
    closeAccountPopover();
    openNewAdminModal();
  });

  elements.newAdminCloseButton.addEventListener("click", closeNewAdminModal);
  elements.newAdminModal.addEventListener("click", (event) => {
    if (event.target === elements.newAdminModal) closeNewAdminModal();
  });
  elements.logoutCancelButton.addEventListener("click", closeLogoutModal);
  elements.logoutConfirmButton.addEventListener("click", logout);
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
  elements.newAdminForm.addEventListener("submit", handleNewAdminSubmit);
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    closeAccountPopover();
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

function isLoggedIn() {
  return (
    (state.session.role === "admin" || state.session.role === "user") &&
    Boolean(state.session.email) &&
    Boolean(state.session.token) &&
    !isSessionExpired(state.session)
  );
}

function sessionAuthHeaders(extraHeaders = {}) {
  if (!isLoggedIn()) return { ...extraHeaders };
  return {
    ...extraHeaders,
    Authorization: `Bearer ${state.session.token}`,
  };
}

function withSessionToken(url) {
  if (!url || !isLoggedIn()) return url;
  const [base, hash] = url.split("#");
  const separator = base.includes("?") ? "&" : "?";
  const withToken = `${base}${separator}token=${encodeURIComponent(state.session.token)}`;
  return hash ? `${withToken}#${hash}` : withToken;
}

function showSignInGate() {
  elements.signInGate.hidden = false;
  elements.signInGate.setAttribute("aria-hidden", "false");
}

function hideSignInGate() {
  elements.signInGate.hidden = true;
  elements.signInGate.setAttribute("aria-hidden", "true");
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

function openNewAdminModal() {
  if (!isAdminSession()) return;
  clearNewAdminStatus();
  elements.newAdminForm.reset();
  elements.newAdminModal.classList.add("is-open");
  elements.newAdminModal.setAttribute("aria-hidden", "false");
  elements.body.classList.add("new-admin-open");
  window.setTimeout(() => elements.newAdminEmail.focus(), 0);
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
  title = "Upload not finished",
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

async function handleNewAdminSubmit(event) {
  event.preventDefault();
  if (!isAdminSession()) {
    showNewAdminStatus("Your session is invalid. Log in again first.", true);
    return;
  }

  const email = elements.newAdminEmail.value.trim().toLowerCase();
  if (!email.endsWith("@icscompute.com")) {
    showNewAdminStatus("Email must be an @icscompute.com address.", true);
    elements.newAdminEmail.focus();
    return;
  }

  const payload = { email };

  try {
    const response = await fetch("/api/admin/admins", {
      method: "POST",
      headers: sessionAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload),
    });
    const data = await readJsonResponse(response);
    if (!response.ok) {
      throw new Error(formatApiError(data.detail, "New admin was not saved."));
    }

    elements.newAdminForm.reset();
    showNewAdminStatus(`Admin ${data.email || payload.email} saved.`, false);
  } catch (error) {
    showNewAdminStatus(error.message || "New admin was not saved.", true);
  }
}

function logout() {
  state.session = {
    role: "",
    email: "",
    name: "",
    token: "",
    expires_at: "",
  };
  clearDocumentUndo();
  window.localStorage.removeItem(AUTH_STORAGE_KEY);
  closeLogoutModal();
  syncAuth();
}

function syncAuth() {
  if (!isLoggedIn()) {
    showSignInGate();
    elements.body.dataset.role = "";
    state.conversations = [];
    renderSidebarConversations();
    return;
  }

  hideSignInGate();
  const isAdmin = isAdminSession();
  elements.body.dataset.role = isAdmin ? "admin" : "user";
  elements.accountAvatar.textContent = (state.session.name || state.session.email || "?")
    .trim()
    .charAt(0)
    .toUpperCase() || "?";
  elements.accountRoleLabel.textContent = isAdmin ? "Admin mode" : "Signed in";
  elements.accountName.textContent = state.session.name || state.session.email;
  elements.accountHint.textContent = isAdmin ? "Admin" : "User";
  elements.accountPopoverRole.textContent = isAdmin ? "Admin mode" : "Signed in";
  elements.accountPopoverName.textContent = state.session.email || state.session.name;
  elements.accountPopoverHint.textContent = "Click the icon on the right to log out.";
  elements.newAdminButton.hidden = !isAdmin;
  elements.accountActionIcon.textContent = "logout";
  elements.accountActionText.textContent = "Logout";
  elements.accountActionButton.setAttribute("aria-label", "Log out");
  if (elements.policyNavLink) elements.policyNavLink.hidden = false;
  if (elements.guardrailsNavLink) elements.guardrailsNavLink.hidden = !isAdmin;
  if (elements.logsNavLink) elements.logsNavLink.hidden = !isAdmin;
  if (elements.analyticsNavLink) elements.analyticsNavLink.hidden = !isAdmin;
  if (!isAdmin && (state.activeScreen === "logs" || state.activeScreen === "guardrails")) {
    navigateTo("chat");
  }
  if (!isAdmin) resetFaqForm();
  clearDocumentStatus();
  syncReindexState();
  updateFaqControls();
  void loadLibrary();
  void loadFaqs();
  void loadConversations();
  if (isAdmin) {
    void loadActivityLogs();
  } else {
    state.activityLogs = [];
    state.activityLogSummary = null;
    state.logError = "";
    renderActivityLogs();
  }
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
