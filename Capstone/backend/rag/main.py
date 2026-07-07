from __future__ import annotations

import re
import sys
import json
import urllib.error
import urllib.request
import warnings

from backend.settings import get_int_env, get_required_env, load_capstone_env

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

from backend.rag.tools import retrieve_knowledge

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


class OllamaGenerationError(RuntimeError):
    """Raised when the local LLM stack cannot complete a generation request."""


UNSUPPORTED_ANSWER = (
    "Sistem tidak dapat menemukan informasi terkait hal tersebut di dalam dokumen SOP. "
    "Silakan lakukan eskalasi ke HR atau manajer terkait untuk instruksi manual."
)

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
    normalized = " ".join(answer.lower().split())
    return any(marker in normalized for marker in UNSUPPORTED_ANSWER_MARKERS)


def _ollama_model_name() -> str:
    return get_required_env("MODEL").removeprefix("ollama/")


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

    return str(payload.get("error") or payload.get("detail") or raw_body).strip()


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


def _ollama_generate(
    prompt: str,
    *,
    num_predict: int,
    temperature: float = 0.1,
    seed: int | None = None,
) -> str:
    """Send a prompt to Ollama, disabling hidden reasoning (with a safe retry)."""
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
        # Keep the whole token budget for the output, not hidden <think> tokens.
        "think": False,
        "options": options,
    }
    try:
        return _post_ollama_generate(payload)
    except OllamaGenerationError as error:
        # Non-thinking models (e.g. gemma3) reject the `think` flag; retry once.
        if "think" not in str(error).lower():
            raise
        payload.pop("think", None)
        return _post_ollama_generate(payload)


def _rewrite_is_safe(original: str, rewritten: str) -> bool:
    """Reject rewrites that smuggle in content instead of resolving references.

    A rewrite may only substitute reference words with their topic, so it must
    not introduce numbers the user never typed (e.g. "12 hari" from an old
    answer) and must stay roughly the same size.
    """
    new_digits = set(re.findall(r"\d+", rewritten)) - set(re.findall(r"\d+", original))
    if new_digits:
        return False
    if len(rewritten.split()) > 2 * len(original.split()) + 6:
        return False
    return True


def _rewrite_query(question: str, conversation_context: str = "") -> str:
    """Resolve follow-up references into a standalone search query via the LLM.

    The prompt is a strict decision procedure: rewrite ONLY when the question
    contains a reference word, otherwise copy it verbatim. A small code-side
    guard (`_rewrite_is_safe`) discards rewrites that inject numbers or extra
    content, falling back to the original question.
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


CHAT_ANSWER_INSTRUCTIONS = (
    "Kamu adalah ICS Knowledge Assistant. Jawab pertanyaan kebijakan internal dalam "
    "bahasa Indonesia dengan gaya natural, membantu, dan grounded. Jelaskan dokumen "
    "operasional seperti rekan kerja yang andal: cukup jelas untuk ditindaklanjuti, "
    "fleksibel formatnya, dan jujur ketika evidence tidak lengkap. Gunakan HANYA "
    "evidence yang diberikan.\n\n"
    "Pilih format yang paling cocok: paragraf, bullet, langkah bernomor, tabel kecil, "
    "atau campuran. Jangan paksakan template tetap. Jika soal proses atau SOP, buat "
    "alurnya jelas dan sertakan aktor, form, approval, output, tenggat, syarat, dan "
    "pengecualian yang didukung evidence.\n\n"
    "Aturan sitasi:\n"
    "- Pertahankan marker sitasi seperti [1] dan [2] di jawaban.\n"
    "- Taruh sitasi di akhir paragraf, bullet, atau baris tabel yang penting.\n"
    "- Jangan sitasi tiap frasa kecil bila satu sitasi cukup untuk seluruh kalimat.\n"
    "- Jangan pernah keluarkan marker generik seperti [n].\n"
    "- Jangan tulis section sumber/referensi terpisah; aplikasi merender detail sumber "
    "dari marker.\n\n"
    "Aturan pemilihan form:\n"
    "- Jika jawaban butuh satu atau lebih form yang dapat diunduh, pilih HANYA dari "
    "daftar 'Form tersedia' di bawah.\n"
    "- Jika tidak ada form yang dibutuhkan, pilih list kosong.\n"
    "- Jangan mengarang nama form.\n"
    "- Jangan tulis nama file form, nama .xlsx, atau section 'formulir terkait/tersedia', "
    "'form yang bisa diunduh', atau sejenisnya di dalam jawaban yang terlihat. Aplikasi "
    "merender form terpilih secara terpisah.\n"
    "- Jika sebuah form relevan, sebut nama form (human-readable) hanya di tempat yang "
    "wajar dalam penjelasan, lalu pilih nama file-nya di FORM_SELECTION.\n"
    "- Jika jawaban secara eksplisit menyatakan tidak ada form tambahan, FORM_SELECTION "
    "harus [].\n"
    "- Jika evidence menjawab pertanyaan secara langsung, di paling akhir tambahkan TEPAT "
    "satu baris machine-readable:\n"
    '  FORM_SELECTION: ["nama file form persis.xlsx"]\n'
    "- Jika tidak ada form yang dibutuhkan, tulis persis:\n"
    "  FORM_SELECTION: []\n\n"
    "Aturan keandalan:\n"
    "- Jangan mengarang detail kebijakan, file, nomor halaman, nomor form, approval, "
    "aktor, perhitungan, syarat, pengecualian, atau rekomendasi.\n"
    "- Jika evidence tidak menjawab pertanyaan secara langsung, jawab singkat HANYA "
    'dengan kalimat ini: "' + UNSUPPORTED_ANSWER + '". Jangan tambahkan FORM_SELECTION '
    "pada kasus unsupported ini."
)


def _generate_answer(question: str, evidence: str, available_forms: str) -> str:
    prompt = (
        f"{CHAT_ANSWER_INSTRUCTIONS}\n\n"
        f"Pertanyaan:\n{question}\n\n"
        f"Evidence:\n{evidence}\n\n"
        f"Form tersedia (JSON):\n{available_forms or '[]'}\n\n"
        "Jawaban:"
    )
    answer = _ollama_generate(
        prompt,
        num_predict=get_int_env("OLLAMA_NUM_PREDICT", 2000),
        temperature=0.3,
        seed=7,
    )
    if not answer:
        raise OllamaGenerationError("Ollama mengembalikan jawaban kosong.")
    return answer


def _split_form_selection(answer: str) -> tuple[str, list[str]]:
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
) -> tuple[str, list[dict[str, object]], list[str]]:
    """Retrieve relevant document evidence and answer through the chat crew."""
    # Rewrite follow-ups ("form untuk itu?") into a standalone query. That query
    # is used for BOTH retrieval and generation, and the conversation context is
    # deliberately NOT passed to generation: once the question is standalone, the
    # previous turn only bleeds the old topic into the new answer.
    standalone_question = _rewrite_query(question, conversation_context)
    evidence, citations = retrieve_knowledge(standalone_question)
    if not citations:
        return UNSUPPORTED_ANSWER, [], []

    answer = GENERATED_SOURCES_SECTION.sub(
        "", _generate_answer(standalone_question, evidence, available_forms)
    ).strip()
    answer, selected_forms = _split_form_selection(answer)
    if _is_unsupported_answer(answer):
        return UNSUPPORTED_ANSWER, [], []
    if citations:
        answer = re.sub(r"\[[nN]\]", f"[{citations[0]['id']}]", answer)
    used_citation_ids = {int(value) for value in re.findall(r"\[(\d+)\]", answer)}
    if used_citation_ids:
        citations = [citation for citation in citations if citation["id"] in used_citation_ids]
    elif citations:
        answer = f"{answer} [{citations[0]['id']}]"
        citations = citations[:1]
    return answer, citations, selected_forms


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
