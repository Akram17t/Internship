from __future__ import annotations

import re
import sys
import json
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

project_root = Path(__file__).resolve().parents[5]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from backend.answer_policy import (
    faq_unavailable_answer_text,
    is_unsupported_answer,
    strip_trailing_unsupported_answer,
    unsupported_answer_text,
)
from backend.settings import get_int_env, get_required_env, load_capstone_env
from backend.semantic_cache import lookup_semantic_cache, store_semantic_cache

from researcher_crew.tools import retrieve_knowledge

load_capstone_env()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger("uvicorn.error")

ANSWER_ROLE_PROMPT = (
    "Kamu adalah ICS Knowledge Assistant. Kamu menjelaskan dokumen operasional "
    "seperti rekan kerja yang reliable: jelas untuk ditindaklanjuti, fleksibel "
    "dalam format, dan jujur ketika evidence tidak lengkap."
)

ANSWER_TASK_RULES = (
    "Jawab pertanyaan user dalam bahasa Indonesia hanya memakai retrieved evidence "
    "yang diberikan.\n\n"
    "Gaya jawaban:\n"
    "- Natural, jelas, dan membantu.\n"
    "- Pilih format yang paling cocok: paragraf, bullet, numbered steps, tabel kecil, atau campuran.\n"
    "- Jika membahas proses/SOP, jelaskan alur, aktor, form, approval, output, deadline, kondisi, dan pengecualian hanya jika didukung evidence.\n\n"
    "Aturan sitasi:\n"
    "- Pertahankan marker sitasi angka seperti [1] dan [2] di jawaban visible.\n"
    "- Letakkan citation di akhir paragraf, bullet, atau baris tabel yang penting.\n"
    "- Jika membuat tabel, pastikan minimal kalimat pengantar atau heading tabel memiliki marker citation yang mendukung isi tabel.\n"
    "- Jangan tulis nama file/source/section sebagai bagian jawaban visible kecuali user memang bertanya sumbernya.\n"
    "- Hindari citation bertumpuk seperti [1] [2] [3]; pecah kalimat/bullet jika perlu.\n"
    "- Jangan pakai marker generik seperti [n].\n"
    "- Jangan buat bagian sources/references terpisah.\n\n"
    "Aturan pemilihan form:\n"
    "- Jika jawaban membutuhkan downloadable form, pilih hanya dari available downloadable forms.\n"
    "- Jangan invent nama form.\n"
    "- Jangan menulis filename PDF atau section download form di jawaban visible; app akan render form terpisah.\n"
    "- Jika evidence menjawab pertanyaan, di akhir jawaban tambahkan tepat satu baris machine-readable:\n"
    "FORM_SELECTION: [\"exact form filename.pdf\"]\n"
    "- Jika tidak perlu form, tulis tepat:\n"
    "FORM_SELECTION: []\n\n"
    "Aturan reliabilitas:\n"
    "- Jangan invent detail policy, file, page, form number, approval, aktor, kalkulasi, requirement, pengecualian, atau rekomendasi.\n"
    "- Jangan pernah output reasoning tersembunyi, chain-of-thought, atau tag <think>...</think>.\n"
    "- Jika evidence tidak menjawab langsung, balas persis kalimat ini saja tanpa FORM_SELECTION:\n"
    "\"Sistem tidak dapat menemukan informasi terkait hal tersebut di dalam dokumen SOP. Silakan lakukan eskalasi ke HR atau manajer terkait untuk instruksi manual.\""
)


class OllamaGenerationError(RuntimeError):
    """Muncul saat stack LLM gagal menyelesaikan proses generasi."""


def _strip_trailing_unsupported_answer(answer: str) -> str:
    """Buang fallback sentence yang nyasar setelah jawaban valid.

    Kalau output hanya fallback murni, biarkan tetap utuh supaya guard
    unsupported bisa mengembalikan jawaban tanpa citation/form.
    """
    return strip_trailing_unsupported_answer(answer)


def _strip_generated_sources_section(answer: str) -> str:
    pattern = re.compile(
        r"^\s*(?:#{1,6}\s*)?(?:\*\*)?"
        r"(?:referensi|sumber|references?|sources?)"
        r"(?:\*\*)?\s*:\s*.*$",
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    return pattern.sub("", answer).strip()


def _strip_thinking_blocks(text: str) -> str:
    # Qwen reasoning models via Groq can emit <think>...</think>; never show it.
    value = re.sub(
        r"^\s*<think\b[^>]*>.*?</think>\s*",
        "",
        str(text),
        flags=re.IGNORECASE | re.DOTALL,
    )
    value = re.sub(
        r"<think\b[^>]*>.*?</think>",
        "",
        value,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return value.replace("<think>", "").replace("</think>", "").strip()


def _configured_model() -> str:
    return get_required_env("MODEL")


def _ollama_model_name() -> str:
    # Ambil nama model Ollama tanpa prefix provider.
    return _configured_model().removeprefix("ollama/")


def _groq_model_name() -> str:
    # Groq SDK memakai nama model tanpa prefix LiteLLM provider.
    return _configured_model().removeprefix("groq/")


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

    return _strip_thinking_blocks(str(body.get("response", "")))


def _groq_generate(
    prompt: str,
    *,
    num_predict: int,
    temperature: float,
) -> str:
    try:
        from groq import Groq
    except ImportError as error:
        raise OllamaGenerationError(
            "Dependency Groq belum terpasang. Jalankan pip install -r requirements.txt."
        ) from error

    try:
        client = Groq(
            api_key=get_required_env("GROQ_API_KEY"),
            timeout=get_int_env("GROQ_TIMEOUT_SECONDS", 240),
        )
        completion = client.chat.completions.create(
            model=_groq_model_name(),
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_completion_tokens=num_predict,
            top_p=0.95,
            reasoning_effort="default",
            stream=False,
            stop=None,
        )
    except Exception as error:
        raise OllamaGenerationError(f"Groq gagal membuat jawaban: {error}") from error

    choices: Any = getattr(completion, "choices", None)
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    return _strip_thinking_blocks(str(getattr(message, "content", "") or ""))


def _ollama_generate(
    prompt: str,
    *,
    num_predict: int,
    temperature: float = 0.1,
    seed: int | None = None,
) -> str:
    """Kirim prompt ke provider aktif, tetap mempertahankan nama lama untuk test."""
    if _configured_model().startswith("groq/"):
        return _groq_generate(
            prompt,
            num_predict=num_predict,
            temperature=temperature,
        )

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


def _is_referential_token(token: str) -> bool:
    # 'itu'/'tersebut' dan klitik '-nya' (formnya, alurnya) bersifat merujuk.
    return token.endswith("nya") or token in {
        "itu",
        "ini",
        "tersebut",
        "tadi",
        "sebelumnya",
        "barusan",
        "tadinya",
        "begitu",
    }


def _rewrite_may_add_context(original: str) -> bool:
    """Tentukan apakah rewrite boleh menambah subjek dari percakapan.

    Kita sengaja konservatif: penambahan konteks hanya diizinkan untuk bentuk
    follow-up yang memang terlihat belum mandiri, misalnya "Form apa buat itu?"
    atau "Kalau luar negeri gimana?".
    """
    normalized = " ".join(re.findall(r"\w+", original.casefold()))
    original_tokens = re.findall(r"\w+", original.casefold())
    non_referential_tokens = [
        token for token in original_tokens if not _is_referential_token(token)
    ]

    if not non_referential_tokens:
        return True

    has_referential_token = any(_is_referential_token(token) for token in original_tokens)
    if has_referential_token and len(non_referential_tokens) <= 5:
        return True

    if re.match(r"^(?:kalau|terus|lalu|habis|setelah|sesudah|dan)\b", normalized):
        return len(non_referential_tokens) <= 6

    return False


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

    original_tokens = set(re.findall(r"\w+", original.casefold()))
    rewritten_tokens = set(re.findall(r"\w+", rewritten.casefold()))
    for token in re.findall(r"\w+", original.casefold()):
        if _is_referential_token(token):
            continue
        if token not in rewritten_tokens:
            return False

    added_tokens = {
        token
        for token in rewritten_tokens - original_tokens
        if not _is_referential_token(token)
    }
    if added_tokens and not _rewrite_may_add_context(original):
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
        "Tugas utama Anda BUKAN memperbaiki bahasa. Tugas Anda hanya menentukan "
        "apakah pertanyaan terakhir perlu dibuat mandiri karena benar-benar "
        "bergantung pada percakapan sebelumnya.\n\n"
        "Aturan keputusan:\n"
        "1. Jika pertanyaan SUDAH mandiri dan topiknya jelas, balas persis: KEEP\n"
        "2. Jika pertanyaan sudah menyebut subjek/topiknya sendiri, pertanyaan itu "
        "SUDAH mandiri: balas KEEP. JANGAN PERNAH mengganti, mempersempit, "
        "memperluas, atau menambahkan detail dari percakapan sebelumnya ke "
        "pertanyaan yang sudah mandiri.\n"
        "3. Jika pertanyaan mandiri tapi percakapan sebelumnya membahas versi yang "
        "lebih spesifik, tetap balas KEEP. Riwayat hanya boleh dipakai untuk "
        "mengisi subjek yang hilang, bukan menambah batasan, kategori, lokasi, "
        "jabatan, durasi, kondisi, atau konteks baru.\n"
        "4. REWRITE hanya boleh dilakukan jika tanpa riwayat percakapan pertanyaan "
        "terakhir tidak jelas subjeknya.\n"
        "5. Jika pertanyaan bergantung pada percakapan, balas: REWRITE: <pertanyaan mandiri>\n"
        "6. Saat REWRITE, ganti atau tambahkan HANYA subjek yang dirujuk. Pertahankan "
        "semua kata, gaya bahasa, maksud, angka, dan tanda baca lainnya.\n"
        "7. Jangan mengubah sinonim, bahasa informal, ejaan, atau susunan kalimat "
        "jika pertanyaan sudah mandiri.\n"
        "8. Jangan menjawab pertanyaan dan jangan beri penjelasan.\n\n"
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
        "Contoh 6 (mandiri, jangan tambahkan scope dari percakapan):\n"
        "Percakapan: membahas perjalanan dinas dalam negeri.\n"
        "Pertanyaan: Tolong sebutin nominal uang saku dan uang makan selama perjalanan dinas\n"
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
    rewrite_match = re.match(
        r"^\s*REWRITE\s*:\s*(?P<question>.+?)\s*$",
        decision,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not rewrite_match:
        return question
    rewritten_question = rewrite_match.group("question").strip().strip('"').strip()
    if not rewritten_question or not _rewrite_is_safe(question, rewritten_question):
        return question
    return rewritten_question


def _direct_answer_prompt(question: str, evidence: str, available_forms: str) -> str:
    return (
        f"{ANSWER_ROLE_PROMPT}\n\n"
        f"Pertanyaan terbaru:\n{question}\n\n"
        f"Retrieved evidence:\n{evidence}\n\n"
        f"Available downloadable forms:\n{available_forms or '[]'}\n\n"
        f"{ANSWER_TASK_RULES}\n\n"
        "Jawaban:"
    )


def _generate_answer(question: str, evidence: str, available_forms: str) -> str:
    # Generate jawaban akhir langsung lewat provider aktif.
    return _ollama_generate(
        _direct_answer_prompt(question, evidence, available_forms),
        num_predict=get_int_env("OLLAMA_NUM_PREDICT", 1100),
        temperature=0.05,
    )


def _split_form_selection(answer: str) -> tuple[str, list[str]]:
    # Ambil pilihan form tersembunyi dan buang daftar form dari jawaban.
    selected_forms: list[str] = []
    form_selection_pattern = re.compile(
        r"^\s*(?:[-*]\s*)?(?:\*\*)?FORM_SELECTION(?:\*\*)?\s*:\s*"
        r"(?:\*\*)?\s*(?P<selection>\[[^\n\r]*\])\s*(?:\*\*)?\s*$",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    form_selection_line_pattern = re.compile(
        r"^\s*(?:[-*]\s*)?(?:\*\*)?FORM_SELECTION\b.*$",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    downloadable_form_section_pattern = re.compile(
        r"(?:^|\n)\s*(?:\*\*)?(?:form|formulir)\s+"
        r"(?:terkait|yang\s+(?:bisa|dapat)\s+(?:diunduh|didownload)|downloadable)"
        r"(?:\*\*)?\s*:?\s*(?:\n\s*)+"
        r"(?:(?:[-*•]|\d+[\.)])\s+.*(?:\n|$))+",
        flags=re.IGNORECASE,
    )
    downloadable_form_intro_pattern = re.compile(
        r"^\s*(?:selain itu,\s*)?(?:ada\s*)?(?:form|formulir)\s+"
        r"(?:terkait\s+)?(?:yang\s+)?(?:tersedia|dapat|bisa|downloadable).*(?::)?\s*$",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    # Hanya baris yang menyebut nama file form (diawali "Form" dan berakhiran .pdf)
    # yang dibuang; sitasi SOP berformat .pdf tidak ikut terhapus.
    downloadable_form_line_pattern = re.compile(
        r"^\s*(?:[-*•]\s*)?.*\bForm\b[^\n\r]*\.pdf\b.*$",
        flags=re.IGNORECASE | re.MULTILINE,
    )

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

    cleaned_answer = form_selection_pattern.sub(collect, answer)
    cleaned_answer = form_selection_line_pattern.sub("", cleaned_answer).strip()
    if selected_forms:
        cleaned_answer = downloadable_form_section_pattern.sub("\n", cleaned_answer)
        cleaned_answer = downloadable_form_intro_pattern.sub("", cleaned_answer)
        cleaned_answer = downloadable_form_line_pattern.sub("", cleaned_answer).strip()
    cleaned_answer = re.sub(r"\n{3,}", "\n\n", cleaned_answer).strip()
    return cleaned_answer, selected_forms


def _normalize_visible_citation_style(answer: str) -> str:
    """Rapikan gaya citation supaya body jawaban tidak terasa seperti debug source."""

    answer = re.sub(r"【\s*(\d+)\s*】", r"[\1]", answer)
    answer = re.sub(r"\[\s*(\d+)\s*\]", r"[\1]", answer)
    # Model kadang menumpuk marker di akhir kalimat: "[1] [2] [3]".
    # UI sudah merender detail citation, jadi cukup pertahankan marker pertama.
    answer = re.sub(
        r"\[(?P<first>\d+)\](?:\s*\[\d+\])+",
        lambda match: f"[{match.group('first')}]",
        answer,
    )
    answer = re.sub(
        r"\[(?P<first>\d+)\](?:\s*,\s*\[\d+\])+",
        lambda match: f"[{match.group('first')}]",
        answer,
    )
    return answer.strip()


def _finalize_answer_citations(
    answer: str,
    citations: list[dict[str, object]],
) -> tuple[str, list[dict[str, object]]]:
    if not citations:
        return answer.strip(), []

    valid_ids = {int(citation["id"]) for citation in citations if "id" in citation}
    first_id = int(citations[0]["id"])
    answer = re.sub(r"\[[nN]\]", f"[{first_id}]", answer)
    answer = _normalize_visible_citation_style(answer)

    def replace_invalid(match: re.Match[str]) -> str:
        citation_id = int(match.group(1))
        return match.group(0) if citation_id in valid_ids else f"[{first_id}]"

    answer = re.sub(r"\[(\d+)\]", replace_invalid, answer)
    used_ids = {int(value) for value in re.findall(r"\[(\d+)\]", answer)}
    if not used_ids:
        answer = f"{answer} [{first_id}]"
        used_ids = {first_id}

    # Tetap kirim semua citation ke frontend agar panel sumber bawah lengkap,
    # walaupun model lupa menaruh marker inline untuk salah satu sumber.
    return answer.strip(), citations


def _generate_faq_answer(question: str, evidence: str) -> str:
    # Buat jawaban FAQ yang ringkas, tetapi tetap memuat detail paling berguna.
    prompt = (
        "Kamu adalah HR Assistant ICS Compute. Tulis jawaban FAQ dalam bahasa Indonesia "
        "yang singkat, padat, dan informatif dengan hanya memakai evidence yang diberikan.\n\n"
        "Aturan jawaban:\n"
        "1. Jawab inti pertanyaan langsung dalam 1-2 kalimat pembuka, tanpa pembuka generik.\n"
        "2. Jika ada tiga atau lebih detail penting, lanjutkan dengan 3-6 bullet menggunakan "
        "format '- '. Jika detailnya sedikit, gunakan paragraf biasa.\n"
        "3. Targetkan 80-150 kata. Jangan berhenti di tengah kalimat.\n"
        "4. Masukkan semua detail material yang benar-benar membantu menjawab pertanyaan, "
        "terutama syarat, pihak yang bertanggung jawab, urutan proses, batas waktu, nominal, "
        "persetujuan, pengecualian, dan form terkait yang tersedia di evidence.\n"
        "5. Prioritaskan detail konkret. Jangan mengulang pertanyaan, mengulang gagasan yang "
        "sama, atau memakai filler seperti 'secara umum', 'pada dasarnya', dan 'penting untuk diketahui'.\n"
        "6. Pertahankan marker sitasi angka seperti [1] atau [2] setelah kalimat yang didukung. "
        "Jangan gunakan [n] dan jangan membuat sumber baru. Jangan menumpuk citation seperti "
        "[1] [2] [3]; pisahkan antar kalimat/bullet jika memang butuh sumber berbeda.\n"
        "7. Bullet boleh memakai label singkat dalam bold, misalnya '- **Persetujuan:** ...'. "
        "Jangan menulis markdown table, bagian sumber terpisah, nama file/dokumen/section "
        "sebagai penjelasan sumber, atau informasi yang tidak ada di evidence.\n"
        "8. Jika evidence tidak menjawab pertanyaan secara langsung, balas persis: "
        f"\"{faq_unavailable_answer_text()}\"\n\n"
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
) -> tuple[str, list[dict[str, object]], list[str], str]:
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
        cached_answer, cached_citations = _finalize_answer_citations(
            _strip_thinking_blocks(cache_hit.answer),
            cache_hit.citations,
        )
        return cached_answer, cached_citations, cache_hit.selected_forms, "cache"

    evidence, citations = retrieve_knowledge(standalone_question)
    if not citations:
        logger.info(
            "[%s] total   | %.2fs (tanpa sumber)", trace_label, time.perf_counter() - started_at
        )
        return unsupported_answer_text(), [], [], "fallback"

    crew_started = time.perf_counter()
    answer = _strip_generated_sources_section(
        _generate_answer(standalone_question, evidence, available_forms)
    )
    logger.info("[%s] crew    | %.2fs", trace_label, time.perf_counter() - crew_started)

    answer, selected_forms = _split_form_selection(answer)
    answer = _strip_trailing_unsupported_answer(answer)
    if is_unsupported_answer(answer):
        logger.info(
            "[%s] total   | %.2fs (tanpa sumber)", trace_label, time.perf_counter() - started_at
        )
        return unsupported_answer_text(), [], [], "fallback"
    answer, citations = _finalize_answer_citations(answer, citations)
    store_semantic_cache(
        standalone_question,
        answer,
        citations,
        selected_forms,
        trace_id=trace_label,
    )
    logger.info("[%s] total   | %.2fs", trace_label, time.perf_counter() - started_at)
    return answer, citations, selected_forms, "model"


def run_faq_crew(question: str) -> tuple[str, list[dict[str, object]]]:
    """Buat jawaban FAQ singkat beserta citation dari evidence RAG lokal."""
    evidence, citations = retrieve_knowledge(question)
    if not citations:
        return (
            faq_unavailable_answer_text(),
            [],
        )

    answer = _strip_generated_sources_section(_generate_faq_answer(question, evidence))
    answer, citations = _finalize_answer_citations(answer, citations)
    return answer, citations
