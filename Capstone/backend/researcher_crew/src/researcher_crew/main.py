from __future__ import annotations

import re
import sys
import json
import logging
import time
import urllib.error
import urllib.request
import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[5]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.settings import get_int_env, get_required_env, load_capstone_env
from backend.semantic_cache import lookup_semantic_cache, store_semantic_cache

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
FORM_SELECTION_PATTERN = re.compile(
    r"^\s*FORM_SELECTION\s*:\s*(?P<selection>\[[^\n\r]*\])\s*$",
    flags=re.IGNORECASE | re.MULTILINE,
)
FORM_SELECTION_LINE_PATTERN = re.compile(
    r"^\s*FORM_SELECTION\s*:.*$",
    flags=re.IGNORECASE | re.MULTILINE,
)
DOWNLOADABLE_FORM_LINE_PATTERN = re.compile(
    r"^\s*(?:[-*•]\s*)?.*\.xlsx\b.*$",
    flags=re.IGNORECASE | re.MULTILINE,
)
DOWNLOADABLE_FORM_INTRO_PATTERN = re.compile(
    r"^\s*(?:selain itu,\s*)?(?:ada\s*)?(?:form|formulir)\s+"
    r"(?:terkait\s+)?(?:yang\s+)?(?:tersedia|dapat|bisa|downloadable).*(?::)?\s*$",
    flags=re.IGNORECASE | re.MULTILINE,
)
DOWNLOADABLE_FORM_SECTION_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:\*\*)?(?:form|formulir)\s+"
    r"(?:terkait|yang\s+(?:bisa|dapat)\s+(?:diunduh|didownload)|downloadable)"
    r"(?:\*\*)?\s*:?\s*(?:\n\s*)+"
    r"(?:(?:[-*•]|\d+[\.)])\s+.*(?:\n|$))+",
    flags=re.IGNORECASE,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger("uvicorn.error")


class OllamaGenerationError(RuntimeError):
    """Muncul saat stack LLM lokal gagal menyelesaikan proses generasi."""


UNSUPPORTED_ANSWER = (
    "Sistem tidak dapat menemukan informasi terkait hal tersebut di dalam dokumen SOP. "
    "Silakan lakukan eskalasi ke HR atau manajer terkait untuk instruksi manual."
)

# Marker ini masih dipakai untuk mengenali jawaban fallback versi bebas dari LLM
# lalu menormalkannya kembali ke satu unsupported answer yang konsisten.
UNSUPPORTED_ANSWER_MARKERS = (
    "tidak tersedia dalam dokumen",
    "tidak tersedia di dokumen",
    "tidak disebutkan",
    "tidak dinyatakan",
    "tidak ada ketentuan",
    "tidak ada informasi",
    "tidak memuat",
    "tidak mencakup",
    "tidak menjelaskan",
    "tanpa menyebutkan",
    "tidak ditemukan",
    "belum tersedia",
    "belum dapat dikonfirmasi",
    "tidak dapat dikonfirmasi",
    "dokumen yang terindeks tidak",
    "dokumen terindeks tidak",
)


def _is_unsupported_answer(answer: str) -> bool:
    # Deteksi jawaban fallback yang berarti dokumen tidak mendukung query.
    normalized = " ".join(answer.lower().split())
    return any(marker in normalized for marker in UNSUPPORTED_ANSWER_MARKERS)


def _ollama_model_name() -> str:
    # Ambil nama model Ollama tanpa prefix provider.
    return get_required_env("MODEL").removeprefix("ollama/")


def _ollama_base_url() -> str:
    # Ambil base URL Ollama yang sudah dirapikan.
    return get_required_env("OLLAMA_BASE_URL").rstrip("/")


def _read_ollama_error(error: urllib.error.HTTPError) -> str:
    # Ambil pesan error paling jelas dari respons HTTP Ollama.
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

    return str(payload.get("error") or payload.get("detail") or raw_body).strip()


def _post_ollama_generate(payload: dict[str, object]) -> str:
    # Kirim request generate mentah ke Ollama dan ambil teks hasilnya.
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


def _ollama_generate(
    prompt: str,
    *,
    num_predict: int,
    temperature: float = 0.1,
    seed: int | None = None,
) -> str:
    """Kirim prompt ke Ollama sambil mematikan hidden reasoning bila didukung."""
    options: dict[str, object] = {
        "temperature": temperature,
        "num_ctx": get_int_env("OLLAMA_NUM_CTX", 4096),
        "num_predict": num_predict,
    }
    if seed is not None:
        options["seed"] = seed

    payload: dict[str, object] = {
        "model": _ollama_model_name(),
        "prompt": prompt,
        "stream": False,
        # Simpan seluruh jatah token untuk output, bukan token <think> tersembunyi.
        "think": False,
        "options": options,
    }
    try:
        return _post_ollama_generate(payload)
    except OllamaGenerationError as error:
        # Model non-thinking seperti gemma3 bisa menolak flag `think`; coba ulang sekali.
        if "think" not in str(error).lower():
            raise
        payload.pop("think", None)
        return _post_ollama_generate(payload)


def _rewrite_is_safe(original: str, rewritten: str) -> bool:
    """Tolak hasil rewrite yang menyisipkan isi baru, bukan sekadar merujuk ulang.

    Rewrite hanya boleh mengganti kata rujukan dengan topik aslinya, jadi
    tidak boleh menambah angka baru dan panjangnya harus tetap masuk akal.
    """
    new_digits = set(re.findall(r"\d+", rewritten)) - set(re.findall(r"\d+", original))
    if new_digits:
        return False
    if len(rewritten.split()) > 2 * len(original.split()) + 6:
        return False
    return True


def _rewrite_query(question: str, conversation_context: str = "") -> str:
    """Ubah pertanyaan follow-up menjadi query mandiri dengan bantuan LLM.

    Prompt-nya memaksa rewrite hanya saat ada kata rujukan. Jika hasil rewrite
    menambah angka atau isi lain, guard kode akan membuangnya dan kembali ke
    pertanyaan asli.
    """
    if not conversation_context.strip():
        return question

    prompt = (
        "Anda menormalkan pertanyaan untuk pencarian dokumen. Ikuti prosedur ini:\n"
        "1. Periksa apakah pertanyaan terakhir memakai kata rujukan yang menunjuk "
        "ke percakapan sebelumnya: 'itu', 'tersebut', 'tadi', 'sebelumnya', "
        "'barusan', atau akhiran '-nya' (misal 'formnya', 'alurnya').\n"
        "2. Jika TIDAK ADA kata rujukan: salin pertanyaan terakhir PERSIS sama, "
        "kata demi kata, tanpa mengubah atau menambahkan apa pun.\n"
        "3. Jika ADA kata rujukan: ganti HANYA kata rujukannya dengan topik yang "
        "dirujuk. Bagian lain biarkan sama persis. DILARANG menambahkan angka, "
        "syarat, detail, atau topik lain dari percakapan.\n"
        "Jangan menjawab pertanyaan. Balas HANYA satu kalimat pertanyaan.\n\n"
        "Contoh 1 (ada rujukan 'itu'):\n"
        "Percakapan: membahas prosedur resign.\n"
        "Pertanyaan: Form apa aja yang harus diisi buat itu?\n"
        "Jawaban: Form apa aja yang harus diisi buat resign?\n\n"
        "Contoh 2 (ada rujukan akhiran '-nya'):\n"
        "Percakapan: membahas prosedur resign.\n"
        "Pertanyaan: Alurnya gimana?\n"
        "Jawaban: Alur resign gimana?\n\n"
        "Contoh 3 (tanpa rujukan, salin persis):\n"
        "Percakapan: membahas prosedur resign.\n"
        "Pertanyaan: Apakah ada ketentuan lain ketika perjalanan dinas berlangsung lama?\n"
        "Jawaban: Apakah ada ketentuan lain ketika perjalanan dinas berlangsung lama?\n\n"
        f"Percakapan sebelumnya:\n{conversation_context}\n\n"
        f"Pertanyaan terakhir:\n{question}\n\n"
        "Jawaban:"
    )
    try:
        rewritten = _ollama_generate(prompt, num_predict=120, temperature=0.0)
    except OllamaGenerationError:
        return question

    rewritten = rewritten.strip().strip('"').strip()
    if not rewritten or not _rewrite_is_safe(question, rewritten):
        return question
    return rewritten


def _crew_output_to_text(result: object) -> str:
    # Ubah output CrewAI menjadi teks respons biasa.
    raw = getattr(result, "raw", None)
    return str(raw if raw is not None else result).strip()


def _generate_answer(question: str, evidence: str, available_forms: str) -> str:
    # Jalankan chat crew untuk menghasilkan jawaban akhir ke user.
    inputs = {
        "question": question,
        "evidence": evidence,
        "available_forms": available_forms or "[]",
    }
    try:
        result = ResearcherCrew().crew().kickoff(inputs=inputs)
    except Exception as error:
        raise OllamaGenerationError(f"CrewAI gagal membuat jawaban: {error}") from error

    return _crew_output_to_text(result)


def _split_form_selection(answer: str) -> tuple[str, list[str]]:
    # Ambil pilihan form tersembunyi dan buang daftar form dari jawaban.
    selected_forms: list[str] = []

    def collect(match: re.Match[str]) -> str:
        raw_selection = match.group("selection")
        try:
            parsed = json.loads(raw_selection)
        except json.JSONDecodeError:
            return ""
        if isinstance(parsed, list):
            selected_forms.extend(
                str(item).strip()
                for item in parsed
                if isinstance(item, str) and item.strip()
            )
        return ""

    cleaned_answer = FORM_SELECTION_PATTERN.sub(collect, answer)
    cleaned_answer = FORM_SELECTION_LINE_PATTERN.sub("", cleaned_answer).strip()
    if selected_forms:
        cleaned_answer = DOWNLOADABLE_FORM_SECTION_PATTERN.sub("\n", cleaned_answer)
        cleaned_answer = DOWNLOADABLE_FORM_INTRO_PATTERN.sub("", cleaned_answer)
        cleaned_answer = DOWNLOADABLE_FORM_LINE_PATTERN.sub("", cleaned_answer).strip()
    cleaned_answer = re.sub(r"\n{3,}", "\n\n", cleaned_answer).strip()
    return cleaned_answer, selected_forms


FAQ_MAX_WORDS = 45


def _generate_faq_answer(question: str, evidence: str) -> str:
    # Buat jawaban FAQ singkat dari evidence yang ditemukan.
    prompt = (
        "Kamu adalah HR Assistant ICS Compute. Buat jawaban FAQ singkat dalam bahasa Indonesia. "
        "Gunakan hanya evidence yang diberikan. Jawaban harus 1 paragraf, "
        f"MAKSIMAL {FAQ_MAX_WORDS} kata, dan HARUS berupa kalimat yang utuh dan selesai "
        "(jangan berhenti di tengah kalimat). Langsung ke inti, dan tetap memakai "
        "marker sitasi seperti [1] di akhir klaim. Jangan tulis sumber terpisah, heading, "
        "bullet, atau markdown table. Jangan gunakan [n].\n\n"
        f"Pertanyaan:\n{question}\n\n"
        f"Evidence:\n{evidence}\n\n"
        "Jawaban FAQ:"
    )
    answer = _ollama_generate(
        prompt,
        num_predict=max(get_int_env("FAQ_NUM_PREDICT", 180), 256),
        temperature=0.1,
        seed=11,
    )
    if not answer:
        raise OllamaGenerationError("Ollama mengembalikan jawaban FAQ kosong.")
    return answer


def run_knowledge_crew(
    question: str,
    conversation_context: str = "",
    available_forms: str = "",
    trace_id: str = "",
) -> tuple[str, list[dict[str, object]], list[str]]:
    """Ambil evidence dokumen lalu hasilkan jawaban lewat chat crew."""
    trace_label = trace_id or "chat"
    started_at = time.perf_counter()

    # Ubah follow-up seperti "form untuk itu?" menjadi query mandiri.
    # Query mandiri ini dipakai untuk retrieval dan generation.
    # Context lama sengaja tidak dikirim ke generation agar topik lama tidak bocor.
    logger.info("[%s] Tahap 1/4 - normalisasi pertanyaan dimulai", trace_label)
    rewrite_started = time.perf_counter()
    standalone_question = _rewrite_query(question, conversation_context)
    logger.info(
        "[%s] Tahap 1/4 selesai dalam %.2fs%s",
        trace_label,
        time.perf_counter() - rewrite_started,
        " (pertanyaan diubah)" if standalone_question != question else "",
    )

    cache_hit = lookup_semantic_cache(standalone_question, trace_id=trace_label)
    if cache_hit is not None:
        logger.info(
            "[%s] Tahap 4/4 selesai dari semantic cache dalam %.2fs",
            trace_label,
            time.perf_counter() - started_at,
        )
        return cache_hit.answer, cache_hit.citations, cache_hit.selected_forms

    logger.info("[%s] Tahap 2/4 - pencarian dokumen dimulai", trace_label)
    retrieval_started = time.perf_counter()
    evidence, citations = retrieve_knowledge(standalone_question)
    logger.info(
        "[%s] Tahap 2/4 selesai dalam %.2fs dengan %s citation",
        trace_label,
        time.perf_counter() - retrieval_started,
        len(citations),
    )
    if not citations:
        logger.info(
            "[%s] Tahap 4/4 - selesai tanpa sumber dalam %.2fs",
            trace_label,
            time.perf_counter() - started_at,
        )
        return UNSUPPORTED_ANSWER, [], []

    logger.info("[%s] Tahap 3/4 - penyusunan jawaban dimulai", trace_label)
    generation_started = time.perf_counter()
    answer = GENERATED_SOURCES_SECTION.sub(
        "", _generate_answer(standalone_question, evidence, available_forms)
    ).strip()
    logger.info(
        "[%s] Tahap 3/4 selesai dalam %.2fs",
        trace_label,
        time.perf_counter() - generation_started,
    )

    logger.info("[%s] Tahap 4/4 - finalisasi respons dimulai", trace_label)
    answer, selected_forms = _split_form_selection(answer)
    if _is_unsupported_answer(answer):
        logger.info(
            "[%s] Tahap 4/4 selesai dalam %.2fs tanpa jawaban bersumber",
            trace_label,
            time.perf_counter() - started_at,
        )
        return UNSUPPORTED_ANSWER, [], []
    if citations:
        answer = re.sub(r"\[[nN]\]", f"[{citations[0]['id']}]", answer)
    used_citation_ids = {int(value) for value in re.findall(r"\[(\d+)\]", answer)}
    if used_citation_ids:
        citations = [citation for citation in citations if citation["id"] in used_citation_ids]
    elif citations:
        answer = f"{answer} [{citations[0]['id']}]"
        citations = citations[:1]
    logger.info(
        "[%s] Tahap 4/4 selesai dalam %.2fs, form terpilih=%s",
        trace_label,
        time.perf_counter() - started_at,
        len(selected_forms),
    )
    store_semantic_cache(
        standalone_question,
        answer,
        citations,
        selected_forms,
        trace_id=trace_label,
    )
    return answer, citations, selected_forms


def run_faq_crew(question: str) -> tuple[str, list[dict[str, object]]]:
    """Buat jawaban FAQ singkat beserta citation dari evidence RAG lokal."""
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
