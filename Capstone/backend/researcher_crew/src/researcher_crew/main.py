from __future__ import annotations

import re
import sys
import json
import urllib.error
import urllib.request
import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[5]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.settings import get_int_env, get_required_env, load_capstone_env

from researcher_crew.tools import retrieve_knowledge

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")
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
    """Raised when Ollama rejects or cannot complete a generation request."""


def _ollama_model_name() -> str:
    model = get_required_env("MODEL")
    return model.removeprefix("ollama/")


def _ollama_base_url() -> str:
    return get_required_env("OLLAMA_BASE_URL").rstrip("/")


def _read_ollama_error(error: urllib.error.HTTPError) -> str:
    try:
        raw_body = error.read().decode("utf-8", errors="replace")
    except Exception:
        raw_body = ""

    if not raw_body:
        return f"Ollama returned HTTP {error.code}."

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return raw_body.strip()

    detail = payload.get("error") or payload.get("detail") or raw_body
    return str(detail).strip()


def _post_ollama_generate(payload: dict[str, object]) -> str:
    request = urllib.request.Request(
        f"{_ollama_base_url()}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=get_int_env("OLLAMA_TIMEOUT_SECONDS", 240),
        ) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = _read_ollama_error(error)
        raise OllamaGenerationError(
            f"Ollama gagal membuat jawaban: {detail}"
        ) from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise OllamaGenerationError(
            f"Ollama belum bisa dihubungi atau responsnya tidak valid: {error}"
        ) from error

    return str(body.get("response", "")).strip()


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
        "dengan gaya natural, jelas, dan enak dibaca seperti rekan kerja yang sedang menjelaskan SOP. "
        "Gunakan konteks percakapan sebelumnya bila membantu, lalu pilih sendiri bentuk jawaban terbaik: "
        "paragraf, poin-poin, tahapan, ringkasan, atau kombinasi. Jangan terpaku pada template tertentu.\n\n"
        "Aturan penting: pakai hanya informasi yang benar-benar ada di evidence. Jangan menambahkan detail "
        "proses, dokumen pendukung, alasan audit, PIC, approval, atau saran lanjutan kalau tidak disebutkan "
        "di evidence. Kalau user meminta hal yang lebih lengkap daripada evidence, jelaskan bagian yang bisa "
        "dikonfirmasi dan bagian yang belum terlihat di dokumen.\n\n"
        "Kalau jawaban perlu menyebut form yang harus diisi atau diunduh, gunakan frasa yang jelas seperti "
        "'Berikut form yang harus diisi:' sebelum daftar formnya, lalu sebutkan nama form secara eksplisit.\n\n"
        "Untuk sitasi, gunakan secukupnya saja. Taruh nomor seperti [1] di akhir paragraf atau akhir poin, "
        "bukan setelah setiap frasa atau setiap kalimat pendek. Idealnya satu paragraf atau satu bullet hanya "
        "punya satu sitasi, kecuali memang menggabungkan informasi dari sumber berbeda. Jangan membuat bagian "
        "sumber terpisah karena aplikasi sudah menampilkan detail dokumen dari marker tersebut.\n\n"
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
            "temperature": 0.25,
            "seed": 7,
            "num_ctx": get_int_env("OLLAMA_NUM_CTX", 4096),
            "num_predict": get_int_env("OLLAMA_NUM_PREDICT", 900),
        },
    }
    return _post_ollama_generate(payload)


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
            "num_ctx": get_int_env("OLLAMA_NUM_CTX", 4096),
            "num_predict": get_int_env("FAQ_NUM_PREDICT", 220),
        },
    }
    return _post_ollama_generate(payload)


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
