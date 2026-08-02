let googleSignInInitAttempts = 0;

function initGoogleSignIn() {
  if (isLoggedIn()) return;

  if (!state.googleClientId) {
    showSignInError(I18N.t("signin.notConfigured"), "signin.notConfigured");
    return;
  }

  if (!window.google?.accounts?.id) {
    // Identity Services script loads with async/defer; retry briefly until ready.
    googleSignInInitAttempts += 1;
    if (googleSignInInitAttempts > 50) {
      showSignInError(I18N.t("signin.loadFailed"), "signin.loadFailed");
      return;
    }
    window.setTimeout(initGoogleSignIn, 100);
    return;
  }

  clearSignInError();
  window.google.accounts.id.initialize({
    client_id: state.googleClientId,
    callback: handleGoogleCredentialResponse,
    hosted_domain: "icscompute.com",
    auto_select: true,
    // Chrome is phasing out third-party-cookie-based One Tap in favor of
    // FedCM; without this flag the auto-prompt can silently fail to show
    // on newer browsers even with an active Google session.
    use_fedcm_for_prompt: true,
  });
  elements.googleSignInButton.innerHTML = "";
  window.google.accounts.id.renderButton(elements.googleSignInButton, {
    type: "standard",
    theme: "outline",
    size: "large",
    text: "signin_with",
    shape: "pill",
  });
  // Auto-prompt the Google One Tap account picker so most people never have
  // to click the button below -- it's kept only as a fallback for when the
  // browser suppresses the prompt (e.g. recently dismissed, no active
  // Google session, third-party-cookie/FedCM restrictions, or a browser
  // that doesn't support One Tap at all).
  window.google.accounts.id.prompt((notification) => {
    if (notification.isNotDisplayed()) {
      console.info(
        "[googleAuth] One Tap not displayed:",
        notification.getNotDisplayedReason(),
      );
    } else if (notification.isSkippedMoment()) {
      console.info("[googleAuth] One Tap skipped:", notification.getSkippedReason());
    } else if (notification.isDismissedMoment()) {
      console.info("[googleAuth] One Tap dismissed:", notification.getDismissedReason());
    }
  });
}

async function handleGoogleCredentialResponse(response) {
  clearSignInError();
  try {
    const apiResponse = await fetch("/api/auth/google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: response.credential }),
    });
    const payload = await readJsonResponse(apiResponse);
    if (!apiResponse.ok) {
      throw new Error(formatApiError(payload.detail, I18N.t("signin.failed")));
    }

    state.session = {
      role: payload.role === "admin" ? "admin" : "user",
      email: payload.email || "",
      name: payload.name || "",
      token: payload.token || "",
      expires_at: payload.expires_at || "",
    };
    if (!isLoggedIn()) {
      throw new Error(I18N.t("signin.sessionInvalid"));
    }
    // Unconditional, not just for a different account: CHAT_STORAGE_KEY is
    // one global key, so even a same-browser session that expired silently
    // (no explicit logout) leaves the previous transcript rendered as soon
    // as *anyone* next authenticates, before logout()'s own reset ever runs.
    // Nothing is lost -- each account's real history still lists correctly
    // in the sidebar via loadConversations(), scoped server-side per user.
    resetChat();
    window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(state.session));
    syncAuth();
  } catch (error) {
    showSignInError(error.message || I18N.t("signin.failed"));
  }
}

// Remembers which i18n key is on screen (if any) so refreshSignInError() can
// re-translate it on a language switch -- this message is set once, before
// the guest ever gets a chance to touch the sign-in card's language toggle,
// so unlike the rest of the UI it has no render function to simply re-run.
let lastSignInErrorKey = "";

function showSignInError(message, key = "") {
  lastSignInErrorKey = key;
  elements.signInError.textContent = message;
  elements.signInError.hidden = false;
}

function clearSignInError() {
  lastSignInErrorKey = "";
  elements.signInError.textContent = "";
  elements.signInError.hidden = true;
}

function refreshSignInError() {
  if (!lastSignInErrorKey || elements.signInError.hidden) return;
  elements.signInError.textContent = I18N.t(lastSignInErrorKey);
}
