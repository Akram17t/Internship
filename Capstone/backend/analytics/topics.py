from __future__ import annotations

"""Simple rule-based topic classifier for analytics.

Reduced-scope replacement for the full versioned taxonomy/classifier service
in the original design: a fixed keyword-to-topic table with a confidence
score based on match strength. No taxonomy versioning, no ML model, no
evaluation harness.
"""

import re
from dataclasses import dataclass

UNCLASSIFIED_TOPIC = "unclassified"
CONFIDENCE_THRESHOLD = 0.34

# (topic_code, display name, keywords) - HR/SOP domain relevant to this app.
# Keywords are matched against a normalized (casefolded, punctuation-stripped)
# version of the question text.
_TOPIC_RULES: list[tuple[str, str, list[str]]] = [
    (
        "leave_and_attendance",
        "Leave & Attendance",
        ["cuti", "izin", "absen", "kehadiran", "leave", "attendance", "lembur", "overtime"],
    ),
    (
        "payroll_and_benefits",
        "Payroll & Benefits",
        [
            "gaji", "payroll", "tunjangan", "bonus", "bpjs", "asuransi", "benefit",
            "reimburse", "reimbursement", "pajak", "pph21", "slip gaji",
        ],
    ),
    (
        "recruitment_and_onboarding",
        "Recruitment & Onboarding",
        [
            "rekrutmen", "recruitment", "onboarding", "interview", "wawancara",
            "kontrak kerja", "probation", "masa percobaan", "tenaga kerja",
        ],
    ),
    (
        "performance_and_discipline",
        "Performance & Discipline",
        [
            "kinerja", "performance", "penilaian", "sanksi", "sp1", "sp2", "sp3",
            "peringatan", "pelanggaran", "disiplin",
        ],
    ),
    (
        "exit_and_termination",
        "Exit & Termination",
        [
            "resign", "pengunduran diri", "phk", "pemutusan hubungan kerja",
            "exit interview", "exit clearance", "pesangon",
        ],
    ),
    (
        "workplace_policy_and_facilities",
        "Workplace Policy & Facilities",
        [
            "kebersihan", "kerapihan", "fasilitas", "kantor", "dress code",
            "seragam", "keselamatan kerja", "k3", "tata tertib",
        ],
    ),
    (
        "travel_and_expense",
        "Travel & Expense",
        [
            "perjalanan dinas", "dinas", "uang muka", "spd", "tiket", "hotel",
            "travel", "business trip",
        ],
    ),
    (
        "it_and_system_access",
        "IT & System Access",
        [
            "akses sistem", "system access", "password", "akun", "login",
            "email kantor", "vpn", "it support",
        ],
    ),
]


@dataclass(frozen=True)
class TopicClassification:
    topic_code: str
    confidence: float


def _normalize(text: str) -> str:
    normalized = re.sub(r"[^\w\s]", " ", text.casefold())
    return " ".join(normalized.split())


def classify_topic(question_text: str) -> TopicClassification:
    normalized = _normalize(question_text or "")
    if not normalized:
        return TopicClassification(UNCLASSIFIED_TOPIC, 0.0)

    words = set(normalized.split())
    best_topic = UNCLASSIFIED_TOPIC
    best_score = 0.0

    for topic_code, _display_name, keywords in _TOPIC_RULES:
        hits = 0
        for keyword in keywords:
            if " " in keyword:
                if keyword in normalized:
                    hits += 1
            elif keyword in words:
                hits += 1
        if hits == 0:
            continue
        # Confidence grows with number of distinct keyword hits but saturates
        # quickly; a single strong keyword hit is enough to clear threshold.
        score = min(1.0, 0.34 + 0.22 * (hits - 1) + 0.34)
        if score > best_score:
            best_score = score
            best_topic = topic_code

    if best_score < CONFIDENCE_THRESHOLD:
        return TopicClassification(UNCLASSIFIED_TOPIC, round(best_score, 2))
    return TopicClassification(best_topic, round(best_score, 2))


def topic_display_name(topic_code: str) -> str:
    for code, display_name, _keywords in _TOPIC_RULES:
        if code == topic_code:
            return display_name
    return "Unclassified"
