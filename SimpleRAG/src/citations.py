from pathlib import Path

from langchain_core.documents import Document


def is_section_heading(lines: list[str], index: int) -> bool:
    line = lines[index].strip()
    if not line:
        return False

    if ":" in line or line[0].isdigit():
        return False

    if line[-1] in ".!?":
        return False

    words = line.split()
    if len(words) > 6 or len(line) > 60:
        return False

    previous_line = lines[index - 1].strip() if index > 0 else ""
    next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""

    return previous_line == "" and next_line == ""


def chunk_documents_by_section(documents: list) -> list[Document]:
    chunks = []

    for document in documents:
        source_path = document.metadata.get("source")
        if not source_path:
            continue

        source_name = Path(source_path).name
        lines = document.page_content.splitlines()

        current_section: str | None = None
        current_content: list[str] = []

        def flush_section() -> None:
            nonlocal current_content

            if not current_section:
                current_content = []
                return

            body = "\n".join(current_content).strip()
            if not body:
                current_content = []
                return

            section_text = f"{current_section}\n\n{body}"
            chunks.append(
                Document(
                    page_content=section_text,
                    metadata={
                        "source": source_name,
                        "section": current_section,
                    },
                )
            )
            current_content = []

        for index, line in enumerate(lines):
            if is_section_heading(lines, index):
                flush_section()
                current_section = line.strip()
                continue

            if current_section:
                current_content.append(line)

        flush_section()

    return chunks


def build_citations(docs: list, max_citations: int = 1) -> list[dict[str, str]]:
    citations = []
    seen = set()

    for doc in docs:
        source_name = doc.metadata.get("source", "unknown")
        section_name = doc.metadata.get("section", "section unknown")

        key = (source_name, section_name)
        if key in seen:
            continue

        seen.add(key)
        citations.append(
            {
                "source": source_name,
                "section": section_name,
            }
        )

        if len(citations) >= max_citations:
            break

    return citations
