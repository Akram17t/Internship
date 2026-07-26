function citationSourceLooksLikePdf(citation) {
  const source = String(citation?.source || citation?.name || "").trim();
  let candidate = source;
  if (!candidate) {
    candidate = String(
      citation?.download_url || citation?.source_url || "",
    ).split("#", 1)[0];
    try {
      candidate = decodeURIComponent(candidate);
    } catch (_) {
      // Keep the original URL when it contains malformed escape sequences.
    }
  }
  return candidate.split(/[?#]/, 1)[0].toLowerCase().endsWith(".pdf");
}

function citationBrowserUrl(citation) {
  const rawUrl = String(
    citation?.download_url || citation?.source_url || "",
  ).trim();
  if (!rawUrl) return "";

  const baseUrl = rawUrl.split("#", 1)[0];
  const rawPage = citation?.page;
  const page =
    typeof rawPage === "number"
      ? rawPage
      : typeof rawPage === "string" && rawPage.trim()
        ? Number(rawPage)
        : Number.NaN;
  if (
    !citationSourceLooksLikePdf(citation) ||
    !Number.isInteger(page) ||
    page < 1
  ) {
    return baseUrl;
  }
  return `${baseUrl}#page=${page}`;
}
