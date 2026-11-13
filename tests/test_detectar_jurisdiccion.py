import hashlib
import json
from pathlib import Path

import pytest

from importlib import import_module

detect_jurisdiction = import_module("scripts.03_bis_detectar_jurisdiccion").detect_jurisdiction
from scripts.evaluar_jurisdiccion import _article_metrics, classification_metrics, evaluate_retrieval

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "evalucacion/preguntas_jurisdiccion.json"
FIXTURE_SHA256 = "3ef5fa9188caefb85876c531bf95b12a5db9612389b17a08583db5e4f45a06fe"


@pytest.mark.parametrize("question,status,jurisdictions", [
    ("¿Qué establece el artículo 12 del Código Electoral Nacional?", "identified", ["nacional"]),
    ("¿Qué indica la Ley 5.109 sobre diputados provinciales?", "identified", ["pba"]),
    ("¿Cómo define la ley provincial santafesina al voto recurrido?", "identified", ["santa_fe"]),
    ("¿Cómo define la Ley 14.478 la autoridad de mesa?", "identified", ["santa_fe"]),
    ("¿Cómo se vota presidente en PBA?", "identified", ["nacional"]),
    ("¿Cómo se elige gobernador en Santa Fe?", "identified", ["santa_fe"]),
    ("¿Qué reglas rigen la elección provincial en Santa Fe?", "identified", ["santa_fe"]),
    ("¿Quiénes están exentos de votar en Santa Fe?", "ambiguous", []),
    ("¿Cómo se vota en PBA?", "ambiguous", []),
    ("¿Cómo se elige gobernador?", "ambiguous", []),
    ("¿Qué diferencias hay entre la ley electoral de PBA y la de Santa Fe?", "comparative", ["pba", "santa_fe"]),
    ("¿Qué diferencias hay entre las reglas nacionales y las de PBA?", "comparative", ["nacional", "pba"]),
    ("¿A qué hora comienza la votación?", "unspecified", []),
    ("¿Cómo se vota en CABA?", "unsupported", []),
    ("¿Cómo voto en Buenos Aires?", "ambiguous", []),
    ("¿Qué partido ganó la elección presidencial argentina de 2023?", "identified", ["nacional"]),
    ("LEY 5.109: ¿Qué dice?", "identified", ["pba"]),
    ("Artículo 12, inciso a: ¿qué establece?", "unspecified", []),
    ("En Santa Fe y PBA, ¿quiénes votan?", "ambiguous", []),
    ("Compará las reglas nacionales con las de PBA para el sufragio.", "comparative", ["nacional", "pba"]),
    ("¿En qué se distinguen las normas electorales de Santa Fe y Nación?", "comparative", ["nacional", "santa_fe"]),
])
def test_expected_routing_cases(question, status, jurisdictions):
    result = detect_jurisdiction(question)
    assert result["status"] == status
    assert result["jurisdictions"] == jurisdictions
    assert isinstance(result["signals"], dict)
    assert result["reason"]
    if status in {"ambiguous", "unspecified"}:
        assert result["clarification_question"]


def test_detector_normalizes_accents_case_punctuation_and_phrase_boundaries():
    assert detect_jurisdiction("CÓDIGO ELECTORAL NACIONAL!!!")["jurisdictions"] == ["nacional"]
    assert detect_jurisdiction("Ley 14.478")["jurisdictions"] == ["santa_fe"]
    assert detect_jurisdiction("Ley 14 478")["jurisdictions"] == ["santa_fe"]
    assert detect_jurisdiction("Ley 14478")["jurisdictions"] == ["santa_fe"]
    assert detect_jurisdiction("Ley N° 14.478")["jurisdictions"] == ["santa_fe"]
    assert detect_jurisdiction("Ley Nº 5.109")["jurisdictions"] == ["pba"]
    assert detect_jurisdiction("Ley N° 19.945")["jurisdictions"] == ["nacional"]
    assert detect_jurisdiction("artículo 19.945 no identifica una ley")["status"] == "unspecified"
    assert detect_jurisdiction("Buenos Aires no es una ley electoral")["status"] == "ambiguous"


def test_explicit_conflicts_are_ambiguous_unless_comparison_is_requested():
    conflict = detect_jurisdiction("¿Qué dice el Código Electoral Nacional sobre la elección de gobernador en Santa Fe?")
    assert conflict["status"] == "ambiguous" and conflict["jurisdictions"] == []
    comparison = detect_jurisdiction("Comparar la Ley 5.109 con la Ley 14.478")
    assert comparison["status"] == "comparative"
    assert comparison["jurisdictions"] == ["pba", "santa_fe"]


def test_independently_labeled_fixture_is_frozen_and_metrics_are_arithmetically_consistent():
    raw = FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FIXTURE_SHA256
    cases = json.loads(raw)["preguntas"]
    assert len(cases) == 40 and len({c["id"] for c in cases}) == 40
    assert all(c["rationale"] and c["gold_status"] in {"identified", "ambiguous", "comparative", "unspecified", "unsupported"} for c in cases)
    labeled = [{**c, "predicted_status": c["gold_status"], "predicted_jurisdictions": c["gold_jurisdictions"]} for c in cases]
    metrics = classification_metrics(labeled)
    assert metrics["exact_routing_match"] == {"numerator": 40, "denominator": 40, "value": 1.0}
    assert metrics["auto_filter_coverage_single_identifiable"] == {"numerator": 21, "denominator": 21, "value": 1.0}
    assert metrics["clarification_abstention_appropriateness"] == {"numerator": 15, "denominator": 15, "value": 1.0}
    assert metrics["comparative_detection"]["correct_jurisdiction_set"] == {"numerator": 4, "denominator": 4, "value": 1.0}


def test_classification_metrics_count_wrong_comparisons_and_separate_coverage_from_accuracy():
    cases = [
        {"gold_status": "identified", "gold_jurisdictions": ["pba"], "predicted_status": "identified", "predicted_jurisdictions": ["santa_fe"]},
        {"gold_status": "comparative", "gold_jurisdictions": ["pba", "santa_fe"], "predicted_status": "comparative", "predicted_jurisdictions": ["pba", "nacional"]},
        {"gold_status": "ambiguous", "gold_jurisdictions": [], "predicted_status": "comparative", "predicted_jurisdictions": ["pba"]},
    ]
    metrics = classification_metrics(cases)
    assert metrics["auto_filter_coverage_single_identifiable"] == {"numerator": 1, "denominator": 1, "value": 1.0}
    assert metrics["correct_auto_filter_rate_single_identifiable"] == {"numerator": 0, "denominator": 1, "value": 0.0}
    assert metrics["harmful_misrouting"]["count"] == 3
    assert metrics["comparative_detection"]["precision"] == {"numerator": 1, "denominator": 3, "value": 1 / 3}
    assert metrics["comparative_detection"]["recall"] == {"numerator": 1, "denominator": 2, "value": 0.5}


def test_article_hit_and_retrieval_comparison_arithmetic_with_fake_rankings():
    rows = [
        {"expected_source_article_ids": ["a"], "results": [{"source_article_id": "a"}]},
        {"expected_source_article_ids": ["b"], "results": [{"source_article_id": "x"}, {"source_article_id": "b"}]},
        {"expected_source_article_ids": ["c"], "results": [{"source_article_id": "x"}]},
    ]
    metric = _article_metrics(rows, 1)
    assert metric["hit_at_k"] == {"numerator": 1, "denominator": 3, "value": 1 / 3}
    assert metric["mrr_at_5"] == {"numerator": 1.5, "denominator": 3, "value": 0.5}

    class FakeIndex:
        def __init__(self):
            self.calls = []
        def integrity_snapshot(self):
            return {"count": 828, "ids_match_chunks": True}
        def retrieve(self, question, k=5, jurisdiccion=None):
            self.calls.append((question, k, jurisdiccion))
            if "Código Electoral Nacional" in question:
                expected, expected_j = "nacional_19945_art_12", "nacional"
            elif "5.109" in question:
                expected, expected_j = "pba_5109_art_13", "pba"
            else:
                expected, expected_j = "santa_fe_14478_art_4", "santa_fe"
            if jurisdiccion == expected_j:
                ordered = [expected] + [f"other_{n}" for n in range(1, k)]
            else:
                ordered = [f"other_{n}" for n in range(1, k)]
                if k > 1:
                    ordered[1] = expected
            return [{"source_article_id": article, "jurisdiccion": expected_j if article == expected else "nacional",
                     "chunk_id": f"{article}-{n}"} for n, article in enumerate(ordered, 1)]

    fake = FakeIndex()
    impact = evaluate_retrieval(questions=[], index_dir=ROOT / ".chroma/electoral_laws",
                                chunks_path=ROOT / "datos/procesados/chunks.jsonl", model="bge-m3", retriever=fake)
    baseline = impact["metrics"]["baseline_unfiltered"]
    oracle = impact["metrics"]["oracle_filter"]
    automatic = impact["metrics"]["automatic_filter"]
    assert baseline["hit_at_1"] == {"numerator": 0, "denominator": 3, "value": 0.0}
    assert baseline["hit_at_3"] == {"numerator": 3, "denominator": 3, "value": 1.0}
    assert baseline["mrr_at_5"] == {"numerator": 1.5, "denominator": 3, "value": 0.5}
    assert oracle["hit_at_1"]["numerator"] == automatic["hit_at_1"]["numerator"] == 3
    assert impact["index_integrity"]["unchanged"] is True
    assert len(fake.calls) == 9
    assert impact["passage_review"]["santa_fe_respondible_autoridad_mesa"]["retrieved_expected_article"] is False
