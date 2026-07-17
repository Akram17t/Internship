(function () {
  const AppApi = {
    isSessionExpired(session) {
      if (!session?.expires_at) return true;
      const expiresAt = new Date(session.expires_at);
      return Number.isNaN(expiresAt.getTime()) || expiresAt <= new Date();
    },

    authHeaders(session, extraHeaders = {}) {
      if (
        session?.role !== "admin" ||
        !session.email ||
        !session.token ||
        AppApi.isSessionExpired(session)
      ) {
        return { ...extraHeaders };
      }
      return {
        ...extraHeaders,
        Authorization: `Bearer ${session.token}`,
      };
    },

    async readJsonResponse(response) {
      try {
        return await response.json();
      } catch {
        return {};
      }
    },

    formatApiError(detail, fallback = "Request failed.") {
      if (!detail) return fallback;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) {
        const messages = detail
          .map((item) => AppApi.formatApiError(item, ""))
          .filter(Boolean);
        return messages.join("; ") || fallback;
      }
      if (typeof detail === "object") {
        if (typeof detail.message === "string") return detail.message;
        if (typeof detail.msg === "string") return detail.msg;
        if (typeof detail.detail === "string") return detail.detail;
        return JSON.stringify(detail);
      }
      return String(detail);
    },

    formPathFromUrl(url) {
      return String(url || "").replace(/^\/api\/documents\//, "");
    },

    filenameFromResponse(response, fallback = "document") {
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
      if (plainMatch?.[1]) return plainMatch[1];
      return fallback;
    },

    downloadBlob(blob, filename) {
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filename || "document";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    },
  };

  window.AppApi = AppApi;
})();
