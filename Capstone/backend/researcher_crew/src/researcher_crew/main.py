from __future__ import annotations

import re
import sys
import json
import logging
import time
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
from backend.settings import get_env, get_int_env, get_required_env, load_capstone_env
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
    "- Jangan pernah menaruh citation sebagai bullet/baris sendiri seperti '- [1]'; tempelkan ke kalimat sebelumnya.\n"
    "- Jika satu langkah punya beberapa bullet, citation cukup ditempel di bullet berisi klaim utama; jangan buat bullet baru hanya untuk citation.\n"
    "- Sebelum final, cek ulang: tidak boleh ada baris yang isinya hanya citation seperti '[1]', '- [1]', '* [1]', atau '1. [1]'.\n"
    "- Jika membuat tabel, pastikan minimal kalimat pengantar atau heading tabel memiliki marker citation yang mendukung isi tabel.\n"
    "- Jika membuat tabel markdown, setiap baris harus diawali dan diakhiri karakter |, termasuk baris terakhir.\n"
    "- Jangan tulis nama file/source/section sebagai bagian jawaban visible kecuali user memang bertanya sumbernya.\n"
    "- Hindari citation bertumpuk seperti [1] [2] [3]; pecah kalimat/bullet jika perlu.\n"
    "- Jangan pakai marker generik seperti [n].\n"
    "- Jangan buat bagian sources/references terpisah.\n\n"
    "Aturan pemilihan form:\n"
    "- Jika jawaban membutuhkan downloadable form, pilih hanya dari available downloadable forms.\n"
    "- Jangan invent nama form.\n"
    "- Jangan menulis filename PDF atau section download form di jawaban visible; app akan render form terpisah.\n"
    "- Jangan membuat heading/kalimat visible seperti 'Form yang digunakan', 'Form terkait', atau 'Form yang bisa diunduh'; cukup isi FORM_SELECTION.\n"
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


class ModelGenerationError(RuntimeError):
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


def _groq_model_name() -> str:
    # Groq SDK memakai nama model tanpa prefix LiteLLM provider.
    return _configured_model().removeprefix("groq/")


def _groq_reasoning_effort() -> str:
    effort = get_env("GROQ_REASONING_EFFORT", "low").lower()
    if effort not in {"low", "medium", "high"}:
        raise ModelGenerationError(
            "GROQ_REASONING_EFFORT must be low, medium, or high in .env."
        )
    return effort


def _generate_with_model(
    prompt: str,
    *,
    num_predict: int,
    temperature: float,
    seed: int | None = None,
) -> str:
    try:
        from groq import Groq
    except ImportError as error:
        raise ModelGenerationError(
            "Dependency Groq belum terpasang. Jalankan pip install -r requirements.txt."
        ) from error

    try:
        client = Groq(
            api_key=get_required_env("GROQ_API_KEY"),
            timeout=get_int_env("GROQ_TIMEOUT_SECONDS", 240),
        )
        request_payload: dict[str, Any] = {
            "model": _groq_model_name(),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_completion_tokens": num_predict,
            "top_p": 0.95,
            "reasoning_effort": _groq_reasoning_effort(),
            "stream": False,
            "stop": None,
        }
        if seed is not None:
            request_payload["seed"] = seed
        completion = client.chat.completions.create(**request_payload)
    except Exception as error:
        raise ModelGenerationError(f"Groq gagal membuat jawaban: {error}") from error

    choices: Any = getattr(completion, "choices", None)
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    return _strip_thinking_blocks(str(getattr(message, "content", "") or ""))


_CONTEXT_REFERENCE_PATTERN = re.compile(
    r"\b(?:itu|ini|tersebut|tadi|barusan|sebelumnya|tadinya|begitu)\b"
    r"|\b\w+nya\b",
    flags=re.IGNORECASE,
)


def _has_context_reference(question: str) -> bool:
    return bool(_CONTEXT_REFERENCE_PATTERN.search(question))


def _extract_rewrite_decision(raw_decision: str) -> str | None:
    decision = raw_decision.strip().strip('"').strip()
    rewrite_match = re.search(
        r"^\s*REWRITE\s*:\s*(?P<question>.+?)\s*$",
        decision,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if not rewrite_match:
        return None
    rewritten_question = rewrite_match.group("question").strip().strip('"').strip()
    return rewritten_question or None


def _rewrite_query(question: str, conversation_context: str = "") -> str:
    """Ubah pertanyaan follow-up menjadi query mandiri dengan bantuan LLM.

    Rewrite dibuat sederhana: AI memutuskan KEEP atau REWRITE, lalu hasil
    REWRITE langsung dipakai sebagai query retrieval.
    """
    if not conversation_context.strip():
        return question

    if _has_context_reference(question):
        prompt = (
            "Pertanyaan terakhir mengandung rujukan ke percakapan sebelumnya. "
            "Tulis ulang menjadi satu pertanyaan mandiri yang tetap memakai "
            "bahasa user.\n\n"
            "Balas hanya dengan format:\n"
            "REWRITE: <pertanyaan mandiri>\n\n"
            "Jangan menjawab pertanyaan user. Jangan menambah fakta yang tidak "
            "ada di percakapan; cukup isi rujukan seperti 'itu', 'tadi', "
            "'kasus tadi', 'barusan', 'durasinya', atau 'totalnya'.\n\n"
            "Contoh 1:\n"
            "Percakapan: membahas perjalanan dinas Manager ke luar negeri selama 3 hari.\n"
            "Pertanyaan: Dari kasus tadi, uang makan dan uang sakunya itu dihitung per hari atau langsung total?\n"
            "Jawaban: REWRITE: Untuk perjalanan dinas Manager ke luar negeri selama 3 hari, uang makan dan uang sakunya dihitung per hari atau langsung total?\n\n"
            "Contoh 2:\n"
            "Percakapan: membahas perjalanan dinas Manager ke luar negeri selama 3 hari dengan total USD 345.\n"
            "Pertanyaan: Kalau durasinya berubah jadi 5 hari, total yang diterima jadi berapa?\n"
            "Jawaban: REWRITE: Kalau durasi perjalanan dinas Manager ke luar negeri berubah jadi 5 hari, total uang makan dan uang saku yang diterima jadi berapa?\n\n"
            f"Percakapan sebelumnya:\n{conversation_context}\n\n"
            f"Pertanyaan terakhir:\n{question}\n\n"
            "Jawaban:"
        )
        try:
            rewritten = _generate_with_model(prompt, num_predict=140, temperature=0.0)
        except ModelGenerationError:
            return question

        return _extract_rewrite_decision(rewritten) or question

    prompt = (
        "Tentukan apakah pertanyaan terakhir perlu ditulis ulang agar bisa "
        "dipahami tanpa membaca percakapan sebelumnya.\n\n"
        "Balas hanya salah satu format berikut:\n"
        "- KEEP\n"
        "- REWRITE: <pertanyaan mandiri>\n\n"
        "Gunakan REWRITE kalau pertanyaan terakhir merujuk ke konteks sebelumnya, "
        "misalnya memakai kata/frasa seperti 'itu', 'tadi', 'barusan', "
        "'kasus barusan', 'case tadi', 'yang tadi', 'formnya', 'alurnya', "
        "atau pertanyaan lanjutan seperti 'kalau luar negeri gimana?'.\n"
        "Gunakan KEEP kalau pertanyaan terakhir sudah jelas tanpa konteks "
        "percakapan. Jangan menjawab pertanyaan user.\n\n"
        "Contoh 1 (rujukan eksplisit):\n"
        "Percakapan: membahas prosedur resign.\n"
        "Pertanyaan: Form apa aja yang harus diisi buat itu?\n"
        "Jawaban: REWRITE: Form apa aja yang harus diisi buat resign?\n\n"
        "Contoh 2 (rujukan implisit):\n"
        "Percakapan: membahas perjalanan dinas dalam negeri.\n"
        "Pertanyaan: Kalau luar negeri gimana?\n"
        "Jawaban: REWRITE: Kalau perjalanan dinas luar negeri gimana?\n\n"
        "Contoh 3 (kasus barusan):\n"
        "Percakapan: membahas perjalanan dinas ke Bali selama 11 hari.\n"
        "Pertanyaan: Kalau kasus barusan, uang makan dan uang sakunya itu dihitung per hari atau gimana?\n"
        "Jawaban: REWRITE: Kalau perjalanan dinas ke Bali selama 11 hari, uang makan dan uang sakunya dihitung per hari atau gimana?\n\n"
        "Contoh 4 (mandiri, jangan diubah):\n"
        "Percakapan: membahas prosedur resign.\n"
        "Pertanyaan: HRIS tuh apa sih?\n"
        "Jawaban: KEEP\n\n"
        f"Percakapan sebelumnya:\n{conversation_context}\n\n"
        f"Pertanyaan terakhir:\n{question}\n\n"
        "Keputusan:"
    )
    try:
        rewritten = _generate_with_model(prompt, num_predict=120, temperature=0.0)
    except ModelGenerationError:
        return question

    decision = rewritten.strip().strip('"').strip()
    if decision.upper() == "KEEP":
        return question
    return _extract_rewrite_decision(decision) or question


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
    return _generate_with_model(
        _direct_answer_prompt(question, evidence, available_forms),
        num_predict=get_int_env("MODEL_NUM_PREDICT", 1100),
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
        r"(?:terkait|yang\s+(?:digunakan|dipakai)|yang\s+(?:bisa|dapat)\s+(?:diunduh|didownload)|downloadable)"
        r"(?:\*\*)?\s*:?\s*(?:\n\s*)+"
        r"(?:(?:[-*•]|\d+[\.)])\s+.*(?:\n|$))+",
        flags=re.IGNORECASE,
    )
    downloadable_form_intro_pattern = re.compile(
        r"^\s*(?:selain itu,\s*)?(?:ada\s*)?(?:form|formulir)\s+"
        r"(?:terkait\s+)?(?:yang\s+)?(?:digunakan|dipakai|tersedia|dapat|bisa|downloadable).*(?::)?\s*$",
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
        cleaned_answer = _strip_visible_form_download_copy(cleaned_answer)
        cleaned_answer = downloadable_form_line_pattern.sub("", cleaned_answer).strip()
    cleaned_answer = re.sub(r"\n{3,}", "\n\n", cleaned_answer).strip()
    return cleaned_answer, selected_forms


def _strip_visible_form_download_copy(answer: str) -> str:
    """Buang heading form visible karena form dirender sebagai blok terpisah."""
    pattern = re.compile(
        r"^\s*(?:#{1,6}\s*)?(?:\*\*)?(?:form|formulir)\s+"
        r"(?:(?:yang\s+)?(?:digunakan|dipakai|terkait)|(?:yang\s+)?(?:bisa|dapat)\s+(?:diunduh|didownload)|downloadable)"
        r"(?:\*\*)?\s*:?\s*$",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    cleaned = pattern.sub("", str(answer))
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _normalize_visible_citation_style(answer: str) -> str:
    """Rapikan gaya citation supaya body jawaban tidak terasa seperti debug source."""

    answer = re.sub(r"【\s*(\d+)\s*】", r"[\1]", answer)
    answer = re.sub(r"\[\s*(\d+)\s*\]", r"[\1]", answer)
    answer = _merge_standalone_citation_lines(answer)
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


def _merge_standalone_citation_lines(answer: str) -> str:
    """Pindahkan baris citation-only ke baris konten sebelumnya."""
    lines = str(answer).splitlines()
    merged: list[str] = []
    standalone_pattern = re.compile(r"^\s*(?:[-*\u2022]\s*)?((?:\[\d+\]\s*)+)\s*$")

    for line in lines:
        match = standalone_pattern.match(line)
        if not match or not merged:
            merged.append(line)
            continue

        marker = " ".join(match.group(1).split())
        target_index = len(merged) - 1
        while target_index >= 0 and not merged[target_index].strip():
            target_index -= 1
        if target_index < 0:
            merged.append(line)
            continue
        if marker in merged[target_index]:
            continue
        merged[target_index] = f"{merged[target_index].rstrip()} {marker}"

    return "\n".join(merged)


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
    answer = _normalize_visible_citation_style(answer)
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
    answer = _generate_with_model(
        prompt,
        num_predict=max(get_int_env("FAQ_NUM_PREDICT", 180), 384),
        temperature=0.1,
        seed=11,
    )
    if not answer:
        raise ModelGenerationError("Groq mengembalikan jawaban FAQ kosong.")
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
        if cache_hit.selected_forms:
            cached_answer = _strip_visible_form_download_copy(cached_answer)
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
