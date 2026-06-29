from __future__ import annotations

import re
import sys
import warnings

from researcher_crew.crew import ResearcherCrew
from researcher_crew.tools import retrieve_knowledge

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

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


def run_knowledge_crew(question: str) -> tuple[str, list[dict[str, object]]]:
    """Run the knowledge crew and return its answer with referenced citations."""
    evidence, citations = retrieve_knowledge(question)
    inputs = {
        "question": question,
        "evidence": evidence,
    }
    result = ResearcherCrew().crew().kickoff(inputs=inputs)
    answer = GENERATED_SOURCES_SECTION.sub("", str(result)).strip()
    if citations:
        answer = re.sub(r"\[[nN]\]", f"[{citations[0]['id']}]", answer)
    used_citation_ids = {int(value) for value in re.findall(r"\[(\d+)\]", answer)}
    if used_citation_ids:
        citations = [citation for citation in citations if citation["id"] in used_citation_ids]
    elif citations:
        answer = f"{answer} [{citations[0]['id']}]"
        citations = citations[:1]
    return answer, citations
