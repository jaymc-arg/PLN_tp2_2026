"""Comprueba la evaluación enrutada sin consumir modelos ni índices reales."""

import hashlib
import json
from pathlib import Path

import pytest

from scripts import evaluar_generacion as evaluation


class FakeRetriever:
    def __init__(self):
        self.calls = []

    def integrity_snapshot(self):
        return {"count": 828, "ids_match_chunks": True}


def fake_routed_result(question, k=3, **kwargs):
    """Imita un resultado auditable completo sin depender de generación real."""
    jurisdiction = "nacional" if "Código Electoral Nacional" in question or "presidencial" in question else "pba"
    record = {"chunk_id": f"{jurisdiction}-{k}", "source_article_id": f"{jurisdiction}_article",
              "jurisdiccion": jurisdiction, "source": f"{jurisdiction}.txt", "ley": "1",
              "articulo": "1", "rank": 1, "text": "Texto de prueba íntegro.", "distance": 0.1}
    return {
        "question": question, "generation_model": "granite4:latest", "temperature": 0, "k": k,
        "jurisdiccion": jurisdiction, "embedding_model": evaluation.DEFAULT_EMBEDDING_MODEL, "answer": "Respuesta [1].",
        "original_response": "Respuesta [1].", "answer_status": "answered", "fallback_reason": None,
        "abstained": False, "references_used": [{"number": 1, "label": "[1]", "chunk_id": record["chunk_id"]}],
        "citation_check": {"citations_valid": True, "citations_missing": False, "citations_invalid": False},
        "source_map": [{"number": 1, "label": "[1]", "chunk_id": record["chunk_id"], "source": record["source"],
                        "jurisdiccion": jurisdiction, "ley": "1", "articulo": "1"}],
        "retrieval_records": [record], "context_sent": "[1]\nTexto de prueba íntegro.", "model_invoked": True,
        "prompt_template_sha256": "prompt-hash", "routing_status": "identified", "jurisdiction_status": "identified",
        "jurisdictions": [jurisdiction], "jurisdiction_source": "automatic", "routing_signals": {},
        "routing_reason": "automatic test route", "clarification_question": None, "applied_filter": jurisdiction,
        "per_jurisdiction_retrievals": None,
    }


def test_generation_evaluation_uses_answer_question_for_all_fixed_and_comparison_calls(tmp_path, monkeypatch, five_case_protocol_fixture):
    """Impide evaluar por error la API histórica que omite el enrutamiento."""
    calls = []
    def routed(question, *, k=3, model=None, retriever=None, embedding_model=None):
        calls.append({"question": question, "k": k, "model": model, "retriever": retriever,
                      "embedding_model": embedding_model})
        return fake_routed_result(question, k=k)

    monkeypatch.setattr(evaluation, "answer_question", routed)
    monkeypatch.setattr(evaluation, "inspect_local_model", lambda model: {"model_tag": model, "temperature": 0})
    retriever = FakeRetriever()
    report_path = tmp_path / "routed.json"
    markdown_path = tmp_path / "routed.md"
    report = evaluation.evaluate(questions_path=five_case_protocol_fixture, retriever=retriever, report_path=report_path, markdown_path=markdown_path,
                                 review_path=tmp_path / "no-review.json")

    assert len(calls) == 6
    assert [call["k"] for call in calls] == [3, 3, 3, 3, 3, 1]
    assert all(call["retriever"] is retriever for call in calls)
    assert report["routing_protocol"] == "answer_question; automatic jurisdiction routing"
    assert report["embedding_model"] == "qwen3-embedding:0.6b"
    assert report["baseline"]["retrieval_protocol"] == (
        "one routed generation call per fixed question; reuse existing qwen3-embedding:0.6b index")
    assert all(case["generation"]["jurisdiction_source"] == "automatic" for case in report["fixed_cases"])
    assert all(case["generation"]["routing_status"] == "identified" for case in report["fixed_cases"])
    assert report["k_comparison"]["k1"]["routing_status"] == "identified"
    assert report["index_integrity"]["unchanged"] is True
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "Ruta / filtro" in markdown
    assert report_path.is_file()


def test_historical_unrouted_report_is_not_reused_by_routed_evaluator(tmp_path, five_case_protocol_fixture):
    legacy_path = tmp_path / "synthetic-unrouted-report.json"
    legacy_path.write_text(json.dumps({"evaluation_questions_sha256": hashlib.sha256(five_case_protocol_fixture.read_bytes()).hexdigest()}))
    report_path = tmp_path / "must-not-be-written.json"
    with pytest.raises(ValueError, match="no usó el protocolo de enrutamiento"):
        evaluation.evaluate(questions_path=five_case_protocol_fixture, existing_report_path=legacy_path, report_path=report_path,
                            markdown_path=tmp_path / "must-not-be-written.md")
    assert not report_path.exists()
    assert evaluation.REPORT_PATH.name == "reporte_generacion_enrutada.json"
