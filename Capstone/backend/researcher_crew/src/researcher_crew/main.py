from __future__ import annotations

import re
import sys
import json
import os
import urllib.request
import warnings

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


def _ollama_model_name() -> str:
    model = os.getenv("MODEL", "ollama/qwen2.5:7b-instruct-q6_K")
    return model.removeprefix("ollama/")


def _ollama_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", os.getenv("API_BASE", "http://localhost:11434")).rstrip("/")


def _build_retrieval_query(question: str, conversation_context: str = "") -> str:
    if not conversation_context:
        return question
    return (
        "Konteks percakapan sebelumnya:\n"
        f"{conversation_context}\n\n"
        f"Pertanyaan terbaru:\n{question}"
    )


def _generate_answer(question: str, evidence: str, conversation_context: str = "") -> str:
    memory_block = ""
    if conversation_context:
        memory_block = f"Konteks percakapan sebelumnya:\n{conversation_context}\n\n"

    prompt = (
        "Kamu adalah HR Assistant ICS Compute. Jawab pertanyaan user dalam bahasa Indonesia "
        "dengan memperhatikan konteks percakapan sebelumnya dan evidence yang diberikan. "
        "Tentukan sendiri bentuk jawaban yang paling enak dibaca: boleh paragraf, poin-poin, "
        "jawaban singkat, atau penjelasan lebih detail sesuai kebutuhan pertanyaan. "
        "Jangan memaksakan format, jumlah kalimat, atau gaya tertentu. "
        "Pakai evidence yang paling relevan, abaikan potongan evidence yang tidak nyambung, "
        "dan gunakan nomor sitasi seperti [1] untuk klaim yang berasal dari evidence. "
        "Kalau evidence menyebut form yang perlu diisi atau diunduh, sebutkan nama formnya dengan jelas. "
        "Kalau evidence memang tidak cukup, jelaskan dengan natural bagian mana yang belum tersedia.\n\n"
        f"{memory_block}"
        f"Pertanyaan:\n{question}\n\n"
        f"Evidence:\n{evidence}\n\n"
        "Jawaban:"
    )
    payload = {
        "model": _ollama_model_name(),
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "seed": 7,
            "num_ctx": 2048,
            "num_predict": 360,
        },
    }
    request = urllib.request.Request(
        f"{_ollama_base_url()}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        body = json.loads(response.read().decode("utf-8"))
    return str(body.get("response", "")).strip()


def _generate_faq_answer(question: str, evidence: str) -> str:
    prompt = (
        "Kamu adalah HR Assistant ICS Compute. Buat jawaban FAQ yang ringkas dalam bahasa Indonesia. "
        "Jawaban harus cocok untuk accordion FAQ: cukup 1 paragraf pendek, maksimal 2 kalimat, "
        "langsung ke inti, dan tetap memakai nomor sitasi seperti [1] untuk klaim dari evidence. "
        "Jangan membuat pembuka panjang, jangan membuat daftar, dan jangan menambahkan bagian sumber terpisah.\n\n"
        f"Pertanyaan FAQ:\n{question}\n\n"
        f"Evidence:\n{evidence}\n\n"
        "Jawaban FAQ:"
    )
    payload = {
        "model": _ollama_model_name(),
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "seed": 11,
            "num_ctx": 2048,
            "num_predict": 150,
        },
    }
    request = urllib.request.Request(
        f"{_ollama_base_url()}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        body = json.loads(response.read().decode("utf-8"))
    return str(body.get("response", "")).strip()


def run_knowledge_crew(
    question: str,
    conversation_context: str = "",
) -> tuple[str, list[dict[str, object]]]:
    """Retrieve relevant document evidence and answer with local Ollama."""
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
