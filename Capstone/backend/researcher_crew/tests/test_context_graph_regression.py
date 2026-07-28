"""Regression suite: verifies the new context resolution graph handles the
same cases the old regex+LLM _rewrite_query was designed for, PLUS cases
the old regex got wrong (false positives/negatives).

These tests call the REAL LLM endpoint (no mocking) via resolve_query_context
with llm_caller=None, so they are integration/regression tests, not fast
unit tests. Skipped automatically if the configured endpoint is unreachable,
so the rest of the suite still runs in environments without a live endpoint.

Run explicitly:
    backend/researcher_crew/.venv/Scripts/python.exe -m pytest \
        backend/researcher_crew/tests/test_context_graph_regression.py -v -s
"""
from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from researcher_crew.context_schema import is_retrieval_decision


def _endpoint_available() -> bool:
    try:
        from researcher_crew.context_graph import _default_llm_caller

        caller = _default_llm_caller()
        result = caller("Balas dengan kata: OK")
        return bool(result)
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _endpoint_available(),
    reason="Live CHAT_BASE_URL endpoint is not reachable; skipping regression suite.",
)


def _resolve(question: str, context: str):
    from researcher_crew.context_graph import resolve_query_context

    return resolve_query_context(question, context, conversation_id="regression-test")


class TestRegressionExplicitReference:
    """Old regex WOULD have matched these (contains itu/tadi/-nya etc)."""

    def test_uang_saku_per_hari_or_total(self):
        result = _resolve(
            "Dari kasus tadi, uang makan dan uang sakunya itu dihitung per hari atau langsung total?",
            "User: Bagaimana perjalanan dinas Manager ke luar negeri selama 3 hari?\n"
            "Assistant: Perjalanan dinas Manager ke luar negeri selama 3 hari mencakup uang makan dan uang saku.",
        )
        assert is_retrieval_decision(result["decision"])
        rq = result["retrieval_query"].lower()
        assert "dinas" in rq or "manager" in rq or "luar negeri" in rq

    def test_durasi_berubah_5_hari(self):
        result = _resolve(
            "Kalau durasinya berubah jadi 5 hari, total yang diterima jadi berapa?",
            "User: Perjalanan dinas Manager ke luar negeri 3 hari dengan total USD 345.\n"
            "Assistant: Total yang diterima adalah USD 345 untuk 3 hari.",
        )
        assert is_retrieval_decision(result["decision"])
        rq = result["retrieval_query"].lower()
        assert "5 hari" in rq or "dinas" in rq

    def test_form_untuk_itu(self):
        result = _resolve(
            "Form apa aja yang harus diisi buat itu?",
            "User: Bagaimana prosedur resign?\nAssistant: Prosedur resign melibatkan pengajuan surat resign ke HR.",
        )
        assert is_retrieval_decision(result["decision"])
        assert "resign" in result["retrieval_query"].lower()


class TestRegressionImplicitReference:
    """Old regex WOULD NOT have matched these (no trigger words) - this is
    exactly the class of bug the new semantic approach is meant to fix."""

    def test_kalau_luar_negeri_gimana(self):
        result = _resolve(
            "Kalau luar negeri gimana?",
            "User: Bagaimana aturan perjalanan dinas dalam negeri?\n"
            "Assistant: Perjalanan dinas dalam negeri diatur dengan uang saku harian.",
        )
        assert is_retrieval_decision(result["decision"])
        rq = result["retrieval_query"].lower()
        assert "luar negeri" in rq or "dinas" in rq

    def test_berapa_lama_prosesnya_implicit(self):
        result = _resolve(
            "Berapa lama prosesnya?",
            "User: Bagaimana cara mengajukan cuti tahunan?\n"
            "Assistant: Cuti tahunan diajukan melalui sistem HRIS dan disetujui atasan.",
        )
        assert is_retrieval_decision(result["decision"])


class TestRegressionStandaloneQuestion:
    """Old regex: KEEP path. New graph: should also decide RETRIEVE with an
    unchanged (or near-unchanged) query since it's already self-contained -
    there is no NO_RETRIEVAL reason to skip retrieval for a real question."""

    def test_hris_tuh_apa_sih(self):
        result = _resolve(
            "HRIS tuh apa sih?",
            "User: Bagaimana prosedur resign?\nAssistant: Prosedur resign melibatkan pengajuan surat resign ke HR.",
        )
        # Should still retrieve (it's a real question), just not dependent on context.
        assert is_retrieval_decision(result["decision"])
        assert "hris" in result["retrieval_query"].lower()


class TestRegressionSocialPleasantry:
    """New capability the old system didn't have: skip retrieval entirely
    for non-informational follow-ups."""

    def test_makasih_ya(self):
        result = _resolve(
            "Oke makasih ya infonya",
            "User: Bagaimana prosedur resign?\nAssistant: Prosedur resign melibatkan pengajuan surat resign ke HR.",
        )
        assert result["decision"] == "NO_RETRIEVAL"


class TestRegressionFalsePositiveRegexCase:
    """Old regex false-positive case: '-nya' suffix triggers on words that
    aren't referencing the conversation at all. The new system should not
    crash or produce garbage; decision correctness here is best-effort
    (LLM judgment) but the pipeline must not error out."""

    def test_unrelated_nya_suffix_does_not_crash(self):
        result = _resolve(
            "Mobil kantor warnanya apa ya?",
            "User: Bagaimana prosedur resign?\nAssistant: Prosedur resign melibatkan pengajuan surat resign ke HR.",
        )
        assert result["decision"] in {"NO_RETRIEVAL", "RETRIEVE", "REUSE_EVIDENCE"}
        assert result["retrieval_query"].strip() != ""
        assert result["cache_query"].strip() != ""
