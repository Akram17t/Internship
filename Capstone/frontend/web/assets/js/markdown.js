/* Assistant answer renderer.
 *
 * Markdown is parsed by `marked` (standard CommonMark + GFM) rather than the
 * hand-written line parser this file used to carry, so tables, nested lists,
 * blockquotes, strikethrough and mixed emphasis all behave the way the model
 * expects when it writes markdown.
 *
 * SECURITY: `marked` returns an HTML *string*, and that string is built from
 * model output over admin-uploaded documents. It is therefore run through
 * DOMPurify with an explicit allow-list before it is ever assigned to
 * innerHTML. Nothing else in this file writes HTML. Do not add a code path that
 * assigns unsanitised markup.
 *
 * Both libraries are vendored under /assets/vendor and loaded before this file
 * (see index.html) -- the app has no bundler, so they are plain globals.
 */

// Tags markdown can legitimately produce. `img` is deliberately absent: an
// answer has no reason to embed a remote image, and allowing it would let
// document content trigger outbound requests.
const MARKDOWN_ALLOWED_TAGS = [
  "p", "br", "hr", "span",
  "strong", "em", "del", "s",
  "code", "pre", "blockquote",
  "h1", "h2", "h3", "h4", "h5", "h6",
  "ul", "ol", "li",
  "table", "thead", "tbody", "tr", "th", "td",
  "a",
];
const MARKDOWN_ALLOWED_ATTR = ["href", "title", "start", "colspan", "rowspan", "align"];

let markdownConfigured = false;

function configureMarkdown() {
  if (markdownConfigured) return;
  if (typeof marked === "undefined" || typeof DOMPurify === "undefined") return;

  marked.setOptions({
    gfm: true,
    // Answers arrive as chat prose where a single newline is meant as a line
    // break, not as paragraph continuation.
    breaks: true,
    headerIds: false,
    mangle: false,
  });

  // Any link that survives sanitising opens in a new tab and cannot reach back
  // into this window. DOMPurify already drops javascript:/data: URLs.
  DOMPurify.addHook("afterSanitizeAttributes", (node) => {
    if (node.tagName === "A" && node.hasAttribute("href")) {
      node.setAttribute("target", "_blank");
      node.setAttribute("rel", "noopener noreferrer nofollow");
    }
  });

  markdownConfigured = true;
}

function formatMessage(content, citations = [], formDownloads = []) {
  const wrapper = document.createElement("div");
  const source = normalizeStandaloneCitationLines(
    String(content ?? "").split(/\r?\n/),
  ).join("\n");
  const text = repairBrokenEmphasis(source);

  configureMarkdown();
  if (typeof marked === "undefined" || typeof DOMPurify === "undefined") {
    // Never render unparsed markup if the vendored libraries failed to load --
    // fall back to plain text, which is always safe.
    const paragraph = document.createElement("p");
    paragraph.textContent = text;
    wrapper.appendChild(paragraph);
    return wrapper;
  }

  wrapper.innerHTML = DOMPurify.sanitize(marked.parse(text), {
    ALLOWED_TAGS: MARKDOWN_ALLOWED_TAGS,
    ALLOWED_ATTR: MARKDOWN_ALLOWED_ATTR,
  });

  applyMessageClasses(wrapper);
  replaceCitationMarkers(wrapper, buildCitationMap(citations));
  return wrapper;
}

/* Re-tag and class the parsed output so it inherits the styles the rest of the
   app already defines (.message-list, .message-heading, .message-code,
   .message-table-wrap). Headings are flattened to h3/h4 because an answer is
   nested inside the page, not a document of its own. */
function applyMessageClasses(wrapper) {
  wrapper.querySelectorAll("ul, ol").forEach((list) => {
    list.classList.add("message-list");
  });

  wrapper.querySelectorAll("h1, h2, h3, h4, h5, h6").forEach((heading) => {
    const level = Number(heading.tagName.slice(1));
    const replacement = document.createElement(level <= 2 ? "h3" : "h4");
    replacement.className = "message-heading";
    while (heading.firstChild) replacement.appendChild(heading.firstChild);
    heading.replaceWith(replacement);
  });

  wrapper.querySelectorAll("pre").forEach((pre) => {
    pre.classList.add("message-code");
  });

  // Tables get an overflow wrapper so a wide table scrolls inside the bubble
  // instead of stretching it.
  wrapper.querySelectorAll("table").forEach((table) => {
    table.classList.add("message-table");
    if (table.parentElement?.classList.contains("message-table-wrap")) return;
    const scroller = document.createElement("div");
    scroller.className = "message-table-wrap";
    table.replaceWith(scroller);
    scroller.appendChild(table);
  });
}

/* Swap inline [n] markers for citation chips.
 *
 * Walks text nodes only, so a marker is never rewritten inside a code block or
 * inside an existing chip. A marker with no matching citation is left as plain
 * text rather than dropped, so nothing silently disappears from the answer. */
function replaceCitationMarkers(wrapper, citationMap) {
  if (!citationMap.size || typeof createCitationChip !== "function") return;

  const walker = document.createTreeWalker(wrapper, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (node.parentElement?.closest("pre, code, .citation-chip")) {
        return NodeFilter.FILTER_REJECT;
      }
      return /\[\d+\]/.test(node.nodeValue)
        ? NodeFilter.FILTER_ACCEPT
        : NodeFilter.FILTER_REJECT;
    },
  });

  const targets = [];
  while (walker.nextNode()) targets.push(walker.currentNode);

  targets.forEach((node) => {
    const pattern = /\[(\d+)\]/g;
    const fragment = document.createDocumentFragment();
    const value = node.nodeValue;
    let cursor = 0;
    let match = pattern.exec(value);
    let replaced = false;

    while (match) {
      const entry = citationMap.get(match[1]);
      if (entry) {
        if (match.index > cursor) {
          fragment.appendChild(
            document.createTextNode(value.slice(cursor, match.index)),
          );
        }
        fragment.appendChild(createCitationChip(entry.citation, entry.index, true));
        cursor = pattern.lastIndex;
        replaced = true;
      }
      match = pattern.exec(value);
    }

    if (!replaced) return;
    if (cursor < value.length) {
      fragment.appendChild(document.createTextNode(value.slice(cursor)));
    }
    node.replaceWith(fragment);
  });
}

/* A model often puts its citation markers on their own line under the sentence
   they belong to. Left alone those become empty-looking paragraphs, so they are
   folded back onto the end of the preceding line before parsing. */
function normalizeStandaloneCitationLines(lines) {
  const normalized = [];
  lines.forEach((line) => {
    const marker = standaloneCitationMarker(line);
    if (!marker || !normalized.length) {
      normalized.push(line);
      return;
    }

    let targetIndex = normalized.length - 1;
    while (targetIndex >= 0 && !String(normalized[targetIndex]).trim()) {
      targetIndex -= 1;
    }
    if (targetIndex < 0) {
      normalized.push(line);
      return;
    }
    if (!normalized[targetIndex].includes(marker)) {
      normalized[targetIndex] = `${String(normalized[targetIndex]).trimEnd()} ${marker}`;
    }
  });
  return normalized;
}

function standaloneCitationMarker(line) {
  const match = String(line || "").match(/^\s*(?:[-*•]\s*)?((?:\[\d+\]\s*)+)\s*$/);
  return match ? match[1].trim().replace(/\s+/g, " ") : "";
}

/* Only repairs genuinely unbalanced emphasis (`*x***`, `***x*`), which a model
   produces often enough to matter and which no parser can read sensibly.
   Well-formed `***x***` is left for marked to render as bold+italic. */
function repairBrokenEmphasis(text) {
  return String(text)
    .replace(/(^|[\s(])\*([^*\n]+?)\*\*\*(?=$|[\s.,;:!?)])/g, "$1**$2**")
    .replace(/(^|[\s(])\*\*\*([^*\n]+?)\*(?=$|[\s.,;:!?)])/g, "$1**$2**");
}

function buildCitationMap(citations) {
  const entries = Array.isArray(citations) ? citations : [];
  return new Map(
    entries.map((citation, index) => [
      String(citation.id || index + 1),
      { citation, index },
    ]),
  );
}
