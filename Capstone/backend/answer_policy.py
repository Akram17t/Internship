from __future__ import annotations

import re


def unsupported_answer_text() -> str:
    return (
        "Sistem tidak dapat menemukan informasi terkait hal tersebut di dalam dokumen SOP. "
        "Silakan lakukan eskalasi ke HR atau manajer terkait untuk instruksi manual."
    )


def faq_unavailable_answer_text() -> str:
    return "Informasi ini belum tersedia dalam dokumen yang saat ini terindeks."


def _normalize_exact_answer(answer: str) -> str:
    answer = re.sub(r"\[\d+\]", " ", answer)
    return " ".join(answer.casefold().split()).rstrip(".")


def is_unsupported_answer(answer: str) -> bool:
    normalized = _normalize_exact_answer(answer)
    return normalized in {
        _normalize_exact_answer(unsupported_answer_text()),
        _normalize_exact_answer(faq_unavailable_answer_text()),
    }


def strip_trailing_unsupported_answer(answer: str) -> str:
    canonical = re.escape(unsupported_answer_text())
    pattern = re.compile(
        rf"(?:\s*\n+\s*|\s+){canonical}\.?(?:\s*\[\d+\])?\s*$",
        flags=re.IGNORECASE,
    )
    match = pattern.search(answer)
    if match is None:
        return answer.strip()

    supported_part = answer[: match.start()].strip()
    if not supported_part:
        return answer.strip()
    return re.sub(r"\n{3,}", "\n\n", supported_part).strip()
