from __future__ import annotations

import re
import sys
import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[5]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.settings import load_capstone_env

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

from researcher_crew.crew import ResearcherCrew
from researcher_crew.tools import retrieve_knowledge

load_capstone_env()

GENERATED_SOURCES_SECTION = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*)?"
    r"(?:referensi|sumber|references?|sources?)"
    r"(?:\*\*)?\s*:\s*.*$",
    flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


class OllamaGenerationError(RuntimeError):
    """Raised when the local LLM stack cannot complete a generation request."""


def _build_retrieval_query(question: str, conversation_context: str = "") -> str:
    if not conversation_context:
        return question
    return (
        "Konteks percakapan sebelumnya:\n"
        f"{conversation_context}\n\n"
        f"Pertanyaan terbaru:\n{question}"
    )


def _crew_output_to_text(result: object) -> str:
    raw = getattr(result, "raw", None)
    return str(raw if raw is not None else result).strip()


def _generate_answer(question: str, evidence: str, conversation_context: str = "") -> str:
    inputs = {
        "question": question,
        "evidence": evidence,
        "conversation_context": conversation_context or "-",
    }
    try:
        result = ResearcherCrew().crew().kickoff(inputs=inputs)
    except Exception as error:
        raise OllamaGenerationError(f"CrewAI gagal membuat jawaban: {error}") from error

    return _crew_output_to_text(result)


def _generate_faq_answer(question: str, evidence: str) -> str:
    inputs = {
        "question": question,
        "evidence": evidence,
    }
    try:
        result = ResearcherCrew().faq_crew().kickoff(inputs=inputs)
    except Exception as error:
        raise OllamaGenerationError(f"CrewAI gagal membuat FAQ: {error}") from error

    return _crew_output_to_text(result)


def run_knowledge_crew(
    question: str,
    conversation_context: str = "",
) -> tuple[str, list[dict[str, object]]]:
    """Retrieve relevant document evidence and answer through the chat crew."""
    retrieval_query = _build_retrieval_query(question, conversation_context)
    evidence, citations = retrieve_knowledge(retrieval_query)
    if not citations:
        return (
            "Informasi tersebut tidak tersedia dalam dokumen yang saat ini terindeks. "
            "Silakan gunakan sumber lain atau tambahkan dokumen yang relevan.",
            [],
        )

    inputs = {
        "question": question,
        "evidence": evidence,
        "conversation_context": conversation_context,
    }
    answer = GENERATED_SOURCES_SECTION.sub("", _generate_answer(**inputs)).strip()
    if citations:
        answer = re.sub(r"\[[nN]\]", f"[{citations[0]['id']}]", answer)
    used_citation_ids = {int(value) for value in re.findall(r"\[(\d+)\]", answer)}
    if used_citation_ids:
        citations = [citation for citation in citations if citation["id"] in used_citation_ids]
    elif citations:
        answer = f"{answer} [{citations[0]['id']}]"
        citations = citations[:1]
    return answer, citations


def run_faq_crew(question: str) -> tuple[str, list[dict[str, object]]]:
    """Generate a short FAQ answer and citations from local RAG evidence."""
    evidence, citations = retrieve_knowledge(question)
    if not citations:
        return (
            "Informasi ini belum tersedia dalam dokumen yang saat ini terindeks.",
            [],
        )

    answer = GENERATED_SOURCES_SECTION.sub("", _generate_faq_answer(question, evidence)).strip()
    if citations:
        answer = re.sub(r"\[[nN]\]", f"[{citations[0]['id']}]", answer)
    used_citation_ids = {int(value) for value in re.findall(r"\[(\d+)\]", answer)}
    if used_citation_ids:
        citations = [citation for citation in citations if citation["id"] in used_citation_ids]
    elif citations:
        answer = f"{answer} [{citations[0]['id']}]"
        citations = citations[:1]
    return answer, citations
