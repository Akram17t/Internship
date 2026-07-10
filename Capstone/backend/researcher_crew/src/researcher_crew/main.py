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
    r"^\s*(?:[-*]\s*)?(?:\*\*)?FORM_SELECTION(?:\*\*)?\s*:\s*"
    r"(?:\*\*)?\s*(?P<selection>\[[^\n\r]*\])\s*(?:\*\*)?\s*$",
    flags=re.IGNORECASE | re.MULTILINE,
)
FORM_SELECTION_LINE_PATTERN = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\*\*)?FORM_SELECTION\b.*$",
    flags=re.IGNORECASE | re.MULTILINE,
)
# Hanya baris yang menyebut nama file form (diawali "Form" dan berakhiran .pdf)
# yang dibuang; sitasi SOP berformat .pdf tidak ikut terhapus.
DOWNLOADABLE_FORM_LINE_PATTERN = re.compile(
    r"^\s*(?:[-*•]\s*)?.*\bForm\b[^\n\r]*\.pdf\b.*$",
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
REWRITE_DECISION_PATTERN = re.compile(
    r"^\s*REWRITE\s*:\s*(?P<question>.+?)\s*$",
    flags=re.IGNORECASE | re.DOTALL,
)
TRAILING_UNSUPPORTED_ANSWER_PATTERN = re.compile(
    r"(?:\s*\n+\s*|\s+)"
    r"Sistem\s+tidak\s+dapat\s+menemukan\s+informasi\s+terkait\s+hal\s+tersebut\s+"
    r"di\s+dalam\s+dokumen\s+SOP\.\s+Silakan\s+lakukan\s+eskalasi\s+ke\s+HR\s+atau\s+"
    r"manajer\s+terkait\s+untuk\s+instruksi\s+manual\.?"
    r"(?:\s*\[\d+\])?\s*$",
    flags=re.IGNORECASE,
)

# Marker ini masih dipakai untuk mengenali jawaban fallback versi bebas dari LLM
# lalu menormalkannya kembali ke satu unsupported answer yang konsisten.
UNSUPPORTED_ANSWER_MARKERS = (
    "tidak dapat menemukan informasi terkait hal tersebut",
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


def _strip_trailing_unsupported_answer(answer: str) -> str:
    """Buang fallback sentence yang nyasar setelah jawaban valid.

    Kalau output hanya fallback murni, biarkan tetap utuh supaya guard
    unsupported bisa mengembalikan jawaban tanpa citation/form.
    """
    match = TRAILING_UNSUPPORTED_ANSWER_PATTERN.search(answer)
    if match is None:
        return answer.strip()

    supported_part = answer[: match.start()].strip()
    if not supported_part:
        return answer.strip()
    return re.sub(r"\n{3,}", "\n\n", supported_part).strip()


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


# Kata rujukan/pengisi yang boleh hilang saat rewrite mengisi subjeknya.
_REFERENTIAL_WORDS = frozenset(
    {"itu", "ini", "tersebut", "tadi", "sebelumnya", "barusan", "tadinya", "begitu"}
)


def _is_referential_token(token: str) -> bool:
    # 'itu'/'tersebut' dan klitik '-nya' (formnya, alurnya) bersifat merujuk.
    return token in _REFERENTIAL_WORDS or token.endswith("nya")


def _rewrite_is_safe(original: str, rewritten: str) -> bool:
    """Tolak hasil rewrite yang menyisipkan isi baru, bukan sekadar merujuk ulang.

    Rewrite hanya boleh mengganti kata rujukan dengan topik aslinya, jadi
    tidak boleh menambah angka baru dan panjangnya harus tetap masuk akal.
    Selain itu, rewrite yang benar hanya MENAMBAH subjek yang dirujuk; ia tidak
    boleh MEMBUANG kata konten asli. Jika kata konten asli hilang (mis. 'resign'
    diganti 'perjalanan dinas'), itu penggantian topik dan harus ditolak.
    """
    new_digits = set(re.findall(r"\d+", rewritten)) - set(re.findall(r"\d+", original))
    if new_digits:
        return False
    if len(rewritten.split()) > 2 * len(original.split()) + 6:
        return False

    rewritten_tokens = set(re.findall(r"\w+", rewritten.casefold()))
    for token in re.findall(r"\w+", original.casefold()):
        if _is_referential_token(token):
            continue
        if token not in rewritten_tokens:
            return False
    return True


def _rewrite_query(question: str, conversation_context: str = "") -> str:
    """Ubah pertanyaan follow-up menjadi query mandiri dengan bantuan LLM.

    AI tetap memeriksa rujukan eksplisit maupun implisit. Output KEEP tidak
    pernah dipakai sebagai pertanyaan baru; kode langsung mempertahankan input
    asli agar model tidak sekadar memoles gaya bahasa atau tanda baca.
    """
    if not conversation_context.strip():
        return question

    prompt = (
        "Anda menentukan apakah pertanyaan terakhir bergantung pada percakapan "
        "sebelumnya. Periksa rujukan eksplisit dan implisit.\n\n"
        "Rujukan eksplisit contohnya: 'itu', 'tersebut', 'tadi', 'sebelumnya', "
        "'barusan', 'formnya', atau 'alurnya'.\n"
        "Rujukan implisit contohnya: 'Kalau luar negeri gimana?', 'Kalau gagal?', "
        "atau 'Terus setelah disetujui?' ketika subjeknya hanya dapat diketahui "
        "dari percakapan sebelumnya.\n"
        "PENTING: kata seperti 'itu' atau akhiran '-nya' HANYA dihitung rujukan "
        "bila kalimat itu tidak menyebut subjek konkretnya sendiri. 'itu' sering "
        "dipakai sebagai partikel pengisi (mis. 'alur yang harus dijalani itu "
        "gimana') dan bukan rujukan bila subjeknya sudah ada di kalimat.\n\n"
        "Aturan keputusan:\n"
        "1. Jika pertanyaan SUDAH mandiri dan topiknya jelas, balas persis: KEEP\n"
        "2. Jika pertanyaan sudah menyebut subjek/topiknya sendiri (mis. 'resign', "
        "'perjalanan dinas', 'onboarding'), pertanyaan itu SUDAH mandiri: balas KEEP. "
        "JANGAN PERNAH mengganti subjek yang sudah disebut dengan topik dari "
        "percakapan sebelumnya, meskipun topiknya berbeda.\n"
        "3. Jika pertanyaan bergantung pada percakapan, balas: REWRITE: <pertanyaan mandiri>\n"
        "4. Saat REWRITE, ganti atau tambahkan HANYA subjek yang dirujuk. Pertahankan "
        "semua kata, gaya bahasa, maksud, angka, dan tanda baca lainnya.\n"
        "5. Jangan mengubah sinonim, bahasa informal, ejaan, atau susunan kalimat "
        "jika pertanyaan sudah mandiri.\n"
        "6. Jangan menjawab pertanyaan dan jangan beri penjelasan.\n\n"
        "Contoh 1 (rujukan eksplisit):\n"
        "Percakapan: membahas prosedur resign.\n"
        "Pertanyaan: Form apa aja yang harus diisi buat itu?\n"
        "Jawaban: REWRITE: Form apa aja yang harus diisi buat resign?\n\n"
        "Contoh 2 (rujukan implisit):\n"
        "Percakapan: membahas perjalanan dinas dalam negeri.\n"
        "Pertanyaan: Kalau luar negeri gimana?\n"
        "Jawaban: REWRITE: Kalau perjalanan dinas luar negeri gimana?\n\n"
        "Contoh 3 (mandiri, jangan diubah):\n"
        "Percakapan: membahas prosedur resign.\n"
        "Pertanyaan: HRIS tuh apa sih?\n"
        "Jawaban: KEEP\n\n"
        "Contoh 4 (mandiri walaupun topiknya berbeda dari percakapan):\n"
        "Percakapan: membahas prosedur resign.\n"
        "Pertanyaan: Apakah ada ketentuan lain ketika perjalanan dinas berlangsung lama?\n"
        "Jawaban: KEEP\n\n"
        "Contoh 5 (sudah menyebut subjek sendiri walau ada 'itu', topik beda dari percakapan):\n"
        "Percakapan: membahas perjalanan dinas.\n"
        "Pertanyaan: Kalau gue mau resign, alur yang harus dijalani itu gimana?\n"
        "Jawaban: KEEP\n\n"
        f"Percakapan sebelumnya:\n{conversation_context}\n\n"
        f"Pertanyaan terakhir:\n{question}\n\n"
        "Keputusan:"
    )
    try:
        rewritten = _ollama_generate(prompt, num_predict=120, temperature=0.0)
    except OllamaGenerationError:
        return question

    decision = rewritten.strip().strip('"').strip()
    if decision.upper() == "KEEP":
        return question
    rewrite_match = REWRITE_DECISION_PATTERN.match(decision)
    if not rewrite_match:
        return question
    rewritten_question = rewrite_match.group("question").strip().strip('"').strip()
    if not rewritten_question or not _rewrite_is_safe(question, rewritten_question):
        return question
    return rewritten_question


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


FAQ_MIN_WORDS = 80
FAQ_MAX_WORDS = 150


def _generate_faq_answer(question: str, evidence: str) -> str:
    # Buat jawaban FAQ yang ringkas, tetapi tetap memuat detail paling berguna.
    prompt = (
        "Kamu adalah HR Assistant ICS Compute. Tulis jawaban FAQ dalam bahasa Indonesia "
        "yang singkat, padat, dan informatif dengan hanya memakai evidence yang diberikan.\n\n"
        "Aturan jawaban:\n"
        "1. Jawab inti pertanyaan langsung dalam 1-2 kalimat pembuka, tanpa pembuka generik.\n"
        "2. Jika ada tiga atau lebih detail penting, lanjutkan dengan 3-6 bullet menggunakan "
        "format '- '. Jika detailnya sedikit, gunakan paragraf biasa.\n"
        f"3. Targetkan {FAQ_MIN_WORDS}-{FAQ_MAX_WORDS} kata. Jangan berhenti di tengah kalimat.\n"
        "4. Masukkan semua detail material yang benar-benar membantu menjawab pertanyaan, "
        "terutama syarat, pihak yang bertanggung jawab, urutan proses, batas waktu, nominal, "
        "persetujuan, pengecualian, dan form terkait yang tersedia di evidence.\n"
        "5. Prioritaskan detail konkret. Jangan mengulang pertanyaan, mengulang gagasan yang "
        "sama, atau memakai filler seperti 'secara umum', 'pada dasarnya', dan 'penting untuk diketahui'.\n"
        "6. Pertahankan marker sitasi angka seperti [1] atau [2] setelah kalimat yang didukung. "
        "Jangan gunakan [n] dan jangan membuat sumber baru.\n"
        "7. Bullet boleh memakai label singkat dalam bold, misalnya '- **Persetujuan:** ...'. "
        "Jangan menulis markdown table, bagian sumber terpisah, atau informasi yang tidak ada di evidence.\n"
        "8. Jika evidence tidak menjawab pertanyaan secara langsung, balas persis: "
        "\"Informasi ini belum tersedia dalam dokumen yang saat ini terindeks.\"\n\n"
        f"Pertanyaan:\n{question}\n\n"
        f"Evidence:\n{evidence}\n\n"
        "Jawaban FAQ:"
    )
    answer = _ollama_generate(
        prompt,
        num_predict=max(get_int_env("FAQ_NUM_PREDICT", 180), 384),
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
    rewrite_started = time.perf_counter()
    standalone_question = _rewrite_query(question, conversation_context)
    rewrite_seconds = time.perf_counter() - rewrite_started
    if standalone_question != question:
        logger.info(
            '[%s] rewrite | changed (%.2fs) | "%s" -> "%s"',
            trace_label,
            rewrite_seconds,
            question,
            standalone_question,
        )
    else:
        logger.info("[%s] rewrite | kept (%.2fs)", trace_label, rewrite_seconds)

    cache_hit = lookup_semantic_cache(standalone_question, trace_id=trace_label)
    if cache_hit is not None:
        logger.info(
            "[%s] total   | %.2fs (dari cache)", trace_label, time.perf_counter() - started_at
        )
        return cache_hit.answer, cache_hit.citations, cache_hit.selected_forms

    evidence, citations = retrieve_knowledge(standalone_question)
    if not citations:
        logger.info(
            "[%s] total   | %.2fs (tanpa sumber)", trace_label, time.perf_counter() - started_at
        )
        return UNSUPPORTED_ANSWER, [], []

    crew_started = time.perf_counter()
    answer = GENERATED_SOURCES_SECTION.sub(
        "", _generate_answer(standalone_question, evidence, available_forms)
    ).strip()
    logger.info("[%s] crew    | %.2fs", trace_label, time.perf_counter() - crew_started)

    answer, selected_forms = _split_form_selection(answer)
    answer = _strip_trailing_unsupported_answer(answer)
    if _is_unsupported_answer(answer):
        logger.info(
            "[%s] total   | %.2fs (tanpa sumber)", trace_label, time.perf_counter() - started_at
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
    store_semantic_cache(
        standalone_question,
        answer,
        citations,
        selected_forms,
        trace_id=trace_label,
    )
    logger.info("[%s] total   | %.2fs", trace_label, time.perf_counter() - started_at)
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
