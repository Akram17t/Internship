function formatMessage(content, citations = [], formDownloads = []) {
  const wrapper = document.createElement("div");
  const lines = normalizeStandaloneCitationLines(String(content).split(/\r?\n/));
  const citationMap = buildCitationMap(citations);
  let list = null;
  let listType = null;

  const appendListItem = (tag, text, startNumber) => {
    if (!list || listType !== tag) {
      list = document.createElement(tag);
      list.className = "message-list";
      if (tag === "ol" && startNumber > 1) list.start = startNumber;
      wrapper.appendChild(list);
      listType = tag;
    }
    const item = document.createElement("li");
    appendFormattedText(item, text, citationMap, formDownloads);
    list.appendChild(item);
  };

  for (let index = 0; index < lines.length; index += 1) {
    const tableRange = getMarkdownTableRange(lines, index);
    if (tableRange) {
      list = null;
      listType = null;
      wrapper.appendChild(
        createMarkdownTable(
          lines.slice(tableRange.start, tableRange.end),
          citationMap,
          formDownloads,
        ),
      );
      index = tableRange.end - 1;
      continue;
    }

    const value = lines[index].trim();
    if (!value) {
      list = null;
      listType = null;
      continue;
    }

    const heading = value.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      list = null;
      listType = null;
      const element = document.createElement(
        heading[1].length <= 2 ? "h3" : "h4",
      );
      element.className = "message-heading";
      appendFormattedText(
        element,
        heading[2].trim(),
        citationMap,
        formDownloads,
      );
      wrapper.appendChild(element);
      continue;
    }

    const ordered = value.match(/^(\d+)[.)]\s+(.*)$/);
    if (ordered) {
      if (isCitationOnlyText(ordered[2])) {
        appendCitationToPreviousBlock(wrapper, ordered[2], citationMap);
        continue;
      }
      appendListItem("ol", ordered[2].trim(), Number(ordered[1]) || 1);
      continue;
    }

    const bullet = value.match(/^[-*•]\s+(.*)$/);
    if (bullet) {
      appendListItem("ul", bullet[1].trim());
      continue;
    }

    list = null;
    listType = null;
    const paragraph = document.createElement("p");
    appendFormattedText(paragraph, value, citationMap, formDownloads);
    wrapper.appendChild(paragraph);
  }
  return wrapper;
}

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
  const match = String(line || "").match(/^\s*(?:[-*â€¢]\s*)?((?:\[\d+\]\s*)+)\s*$/);
  return match ? match[1].trim().replace(/\s+/g, " ") : "";
}

function isCitationOnlyText(text) {
  return Boolean(standaloneCitationMarker(text));
}

function appendCitationToPreviousBlock(wrapper, text, citationMap) {
  const marker = standaloneCitationMarker(text);
  const target = wrapper.querySelector(
    "p:last-child, li:last-child, td:last-child, th:last-child",
  );
  if (!marker || !target || target.textContent.includes(marker)) return;
  target.append(document.createTextNode(" "));
  appendFormattedText(target, marker, citationMap);
}

function getMarkdownTableRange(lines, start) {
  if (!isMarkdownTableRow(lines[start])) return null;
  if (!isMarkdownTableSeparator(lines[start + 1] || "")) return null;

  let end = start + 2;
  while (end < lines.length && isMarkdownTableRow(lines[end])) {
    end += 1;
  }

  return end > start + 2 ? { start, end } : null;
}

function isMarkdownTableRow(line) {
  const value = stripMarkdownTableCitationSuffix(line);
  return (
    value.startsWith("|") &&
    (value.endsWith("|") || value.split("|").length > 3) &&
    value.split("|").length > 3
  );
}

function isMarkdownTableSeparator(line) {
  const cells = splitMarkdownTableRow(line);
  return (
    cells.length > 1 &&
    cells.every((cell) => /^:?-{3,}:?$/.test(cell.replace(/\s/g, "")))
  );
}

function splitMarkdownTableRow(line) {
  const suffix = markdownTableCitationSuffix(line);
  const cells = stripMarkdownTableCitationSuffix(line)
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
  if (suffix && cells.length) {
    cells[cells.length - 1] = `${cells[cells.length - 1]} ${suffix}`.trim();
  }
  return cells;
}

function markdownTableCitationSuffix(line) {
  const match = String(line || "").match(/\|\s*((?:\[\d+\]\s*)+)$/);
  return match ? match[1].trim().replace(/\s+/g, " ") : "";
}

function stripMarkdownTableCitationSuffix(line) {
  return String(line || "")
    .trim()
    .replace(/\s+(?:\[\d+\]\s*)+$/, "")
    .trim();
}

function createMarkdownTable(lines, citationMap, formDownloads = []) {
  const wrapper = document.createElement("div");
  wrapper.className = "message-table-wrap";
  const table = document.createElement("table");
  table.className = "message-table";
  const headerCells = splitMarkdownTableRow(lines[0]);
  const bodyRows = lines.slice(2).map(splitMarkdownTableRow);
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  headerCells.forEach((cell) => {
    const th = document.createElement("th");
    appendFormattedText(th, cell, citationMap, formDownloads);
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  bodyRows.forEach((row) => {
    const tr = document.createElement("tr");
    headerCells.forEach((_, cellIndex) => {
      const td = document.createElement("td");
      appendFormattedText(td, row[cellIndex] || "", citationMap, formDownloads);
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  wrapper.appendChild(table);
  return wrapper;
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

function sanitizeMarkdownEmphasis(text) {
  const preservedNestedSegments = [];
  const value = String(text).replace(
    /\*\*[^*\n]*\*[^*\n]+\*[^*\n]*\*\*/g,
    (match) => {
      const token = `__MD_NESTED_${preservedNestedSegments.length}__`;
      preservedNestedSegments.push(match);
      return token;
    },
  );

  return value
    .replace(/(^|[\s(])\*\*\*([^*\n]+?)\*\*\*(?=$|[\s.,;:!?)]|$)/g, "$1**$2**")
    .replace(/(^|[\s(])\*([^*\n]+?)\*\*\*(?=$|[\s.,;:!?)]|$)/g, "$1**$2**")
    .replace(/(^|[\s(])\*\*\*([^*\n]+?)\*(?=$|[\s.,;:!?)]|$)/g, "$1**$2**")
    .replace(/__MD_NESTED_(\d+)__/g, (_, index) => {
      return preservedNestedSegments[Number(index)] || "";
    });
}

function appendFormattedText(container, text, citationMap, formDownloads = []) {
  const safeText = sanitizeMarkdownEmphasis(text);
  const formMatches = findFormDownloadMatches(safeText, formDownloads);
  const tokenPattern =
    /(\[(\d+)\]|\*\*([^*\n]*?)\*([^*\n]+?)\*([^*\n]*?)\*\*|\*\*([^*]+)\*\*|\*([^*\s][^*]*?)\*)/g;
  let cursor = 0;
  let match = tokenPattern.exec(safeText);

  while (match) {
    if (match.index > cursor) {
      appendTextWithFormChips(
        container,
        safeText.slice(cursor, match.index),
        cursor,
        formMatches,
      );
    }

    if (match[2]) {
      const citationEntry = citationMap.get(match[2]);
      if (citationEntry) {
        container.append(
          createCitationChip(citationEntry.citation, citationEntry.index, true),
        );
      } else {
        container.append(document.createTextNode(match[0]));
      }
    } else if (match[4] !== undefined) {
      const strong = document.createElement("strong");
      const leadingText = match[3] || "";
      const emphasizedText = match[4] || "";
      const trailingText = match[5] || "";
      let strongOffset = match.index + 2;
      appendTextWithFormChips(
        strong,
        leadingText,
        strongOffset,
        formMatches,
      );
      strongOffset += leadingText.length + 1;
      const emphasis = document.createElement("em");
      appendTextWithFormChips(
        emphasis,
        emphasizedText,
        strongOffset,
        formMatches,
      );
      strong.append(emphasis);
      strongOffset += emphasizedText.length + 1;
      appendTextWithFormChips(strong, trailingText, strongOffset, formMatches);
      container.append(strong);
    } else if (match[6]) {
      const strong = document.createElement("strong");
      appendTextWithFormChips(strong, match[6], match.index + 2, formMatches);
      container.append(strong);
    } else if (match[7]) {
      const emphasis = document.createElement("em");
      appendTextWithFormChips(emphasis, match[7], match.index + 1, formMatches);
      container.append(emphasis);
    }

    cursor = tokenPattern.lastIndex;
    match = tokenPattern.exec(safeText);
  }

  if (cursor < safeText.length) {
    appendTextWithFormChips(
      container,
      safeText.slice(cursor),
      cursor,
      formMatches,
    );
  }
}

function findFormDownloadMatches() {
  // Form downloads always render in the bottom "Form yang bisa diunduh" block.
  // Returning no matches keeps them out of the answer text so their placement is
  // consistent regardless of whether the answer happens to use the word "form".
  return [];
}

function appendTextWithFormChips(container, text, offset, formMatches) {
  const segmentStart = offset;
  const segmentEnd = offset + text.length;
  const matches = formMatches.filter(
    (match) => match.start >= segmentStart && match.end <= segmentEnd,
  );

  if (!matches.length) {
    container.append(document.createTextNode(text));
    return;
  }

  let cursor = 0;
  matches.forEach((match) => {
    const localStart = match.start - segmentStart;
    const localEnd = match.end - segmentStart;
    if (localStart > cursor) {
      container.append(document.createTextNode(text.slice(cursor, localStart)));
    }
    container.append(document.createTextNode(text.slice(localStart, localEnd)));
    const group = document.createElement("span");
    group.className = "form-download-inline-group";
    match.items.forEach((item) => {
      group.appendChild(createFormDownloadChip(item, true));
    });
    container.append(group);
    cursor = localEnd;
  });

  if (cursor < text.length) {
    container.append(document.createTextNode(text.slice(cursor)));
  }
}
