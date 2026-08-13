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
  title = I18N.t("documentErrorModal.title"),
) {
  elements.documentErrorTitle.textContent = title;
  elements.documentErrorSummary.textContent = summary;
  elements.documentErrorList.innerHTML = "";
  failures.forEach((failure) => {
    const item = document.createElement("li");
    const name = document.createElement("strong");
    name.textContent = failure.name || I18N.t("documentErrorModal.defaultDocument");
    const reason = document.createElement("span");
    reason.textContent = failure.reason || I18N.t("docs.uploadFailed");
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
    showNewAdminStatus(I18N.t("newAdminModal.sessionInvalid"), true);
    return;
  }

  const email = elements.newAdminEmail.value.trim().toLowerCase();
  if (!email.endsWith("@icscompute.com")) {
    showNewAdminStatus(I18N.t("newAdminModal.emailMustMatch"), true);
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
      throw new Error(formatApiError(data.detail, I18N.t("newAdminModal.notSaved")));
    }

    elements.newAdminForm.reset();
    showNewAdminStatus(I18N.t("newAdminModal.saved", { email: data.email || payload.email }), false);
  } catch (error) {
    showNewAdminStatus(error.message || I18N.t("newAdminModal.notSaved"), true);
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
  // Prevent Google Identity Services from immediately selecting the previous
  // account again; the next session must start from the sign-in gate.
  window.google?.accounts?.id?.disableAutoSelect?.();
  // CHAT_STORAGE_KEY is one global key, not scoped per user -- without this,
  // the next person to sign in on this browser (a real risk on shared/kiosk
  // machines) would see this account's chat transcript rendered immediately,
  // including any sensitive HR answers, before sending a message of their own.
  resetChat();
  closeLogoutModal();
  syncAuth();
}

function syncAuth() {
  if (!isLoggedIn()) {
    showSignInGate();
    elements.accountActionButton.hidden = true;
    elements.body.dataset.role = "";
    state.conversations = [];
    renderSidebarConversations();
    return;
  }

  hideSignInGate();
  elements.accountActionButton.hidden = false;
  const isAdmin = isAdminSession();
  elements.body.dataset.role = isAdmin ? "admin" : "user";
  refreshAccountLabels();
  elements.newAdminButton.hidden = !isAdmin;
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

// Split out of syncAuth() so refreshDynamicUI() (app.js, on language change)
// can re-derive these labels from state.session without re-running the
// nav-visibility/navigation/network side effects that live in syncAuth().
function refreshAccountLabels() {
  if (!isLoggedIn()) return;
  const isAdmin = isAdminSession();
  elements.accountAvatar.textContent = (state.session.name || state.session.email || "?")
    .trim()
    .charAt(0)
    .toUpperCase() || "?";
  // The only identity cue left when the sidebar is collapsed to its icon rail.
  elements.accountAvatar.title = state.session.email || state.session.name || "";
  elements.accountRoleLabel.textContent = I18N.t(isAdmin ? "account.adminMode" : "account.signedIn");
  elements.accountName.textContent = state.session.name || state.session.email;
  elements.accountHint.textContent = I18N.t(isAdmin ? "account.admin" : "account.user");
  elements.accountPopoverRole.textContent = I18N.t(isAdmin ? "account.adminMode" : "account.signedIn");
  elements.accountPopoverName.textContent = state.session.email || state.session.name;
  // Not "the icon on the right": collapsed to the icon rail, the logout button
  // sits under the avatar rather than beside it.
  elements.accountPopoverHint.textContent = I18N.t("account.logoutHint");
  elements.accountActionIcon.textContent = "logout";
  elements.accountActionText.textContent = I18N.t("account.logout");
  elements.accountActionButton.setAttribute("aria-label", I18N.t("account.logOutAria"));
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
