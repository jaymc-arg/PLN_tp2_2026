"""Offline routing classification and optional read-only retrieval impact evaluation."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.detectar_jurisdiccion import JURISDICCIONES, detect_jurisdiction
from scripts.indexar import DEFAULT_INDEX, DEFAULT_INPUT, DEFAULT_MODEL
from scripts.recuperar import SemanticRetriever

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "evalucacion/preguntas_jurisdiccion.json"
BASELINE_FIXTURE = ROOT / "evalucacion/preguntas.json"
REPORT = ROOT / "evalucacion/reporte_jurisdiccion.json"
MARKDOWN = ROOT / "evalucacion/validacion_jurisdiccion.md"
STATUSES = ("identified", "ambiguous", "comparative", "unspecified", "unsupported")


def classification_metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    matrix = {gold: {pred: 0 for pred in STATUSES} for gold in STATUSES}
    exact = 0
    per_jurisdiction = {}
    harmful = 0
    applicable_single = 0
    auto_filter_coverage = 0
    correctly_routed_single = 0
    abstention_expected = 0
    abstention_appropriate = 0
    comp_tp = comp_pred = comp_gold = comp_set_correct = 0
    for case in cases:
        gold_status, pred_status = case["gold_status"], case["predicted_status"]
        gold = case["gold_jurisdictions"]
        pred = case["predicted_jurisdictions"]
        matrix[gold_status][pred_status] += 1
        exact += gold_status == pred_status and gold == pred
        if gold_status == "identified" and len(gold) == 1:
            applicable_single += 1
            if pred_status == "identified" and len(pred) == 1:
                auto_filter_coverage += 1
                correctly_routed_single += pred == gold
        if gold_status in {"ambiguous", "unspecified", "unsupported"}:
            abstention_expected += 1
            abstention_appropriate += pred_status == gold_status
            if pred:
                harmful += 1
        elif pred and pred != gold:
            harmful += 1
        if gold_status == "comparative":
            comp_gold += len(gold)
            comp_set_correct += pred_status == "comparative" and pred == gold
        if pred_status == "comparative":
            comp_pred += len(pred)
            comp_tp += len(set(gold) & set(pred)) if gold_status == "comparative" else 0
    for jurisdiction in JURISDICCIONES:
        tp = fp = fn = 0
        for case in cases:
            gold = set(case["gold_jurisdictions"])
            pred = set(case["predicted_jurisdictions"])
            tp += jurisdiction in gold and jurisdiction in pred
            fp += jurisdiction not in gold and jurisdiction in pred
            fn += jurisdiction in gold and jurisdiction not in pred
        per_jurisdiction[jurisdiction] = {
            "precision": {"numerator": tp, "denominator": tp + fp, "value": tp / (tp + fp) if tp + fp else None},
            "recall": {"numerator": tp, "denominator": tp + fn, "value": tp / (tp + fn) if tp + fn else None},
        }
    return {
        "exact_routing_match": {"numerator": exact, "denominator": len(cases), "value": exact / len(cases)},
        "confusion_matrix": matrix,
        "per_jurisdiction": per_jurisdiction,
        "auto_filter_coverage_single_identifiable": {"numerator": auto_filter_coverage, "denominator": applicable_single, "value": auto_filter_coverage / applicable_single if applicable_single else None},
        "correct_auto_filter_rate_single_identifiable": {"numerator": correctly_routed_single, "denominator": applicable_single, "value": correctly_routed_single / applicable_single if applicable_single else None},
        "harmful_misrouting": {"count": harmful, "denominator": len(cases), "rate": harmful / len(cases)},
        "clarification_abstention_appropriateness": {"numerator": abstention_appropriate, "denominator": abstention_expected, "value": abstention_appropriate / abstention_expected if abstention_expected else None},
        "comparative_detection": {
            "precision": {"numerator": comp_tp, "denominator": comp_pred, "value": comp_tp / comp_pred if comp_pred else None},
            "recall": {"numerator": comp_tp, "denominator": comp_gold, "value": comp_tp / comp_gold if comp_gold else None},
            "correct_jurisdiction_set": {"numerator": comp_set_correct, "denominator": sum(c["gold_status"] == "comparative" for c in cases), "value": comp_set_correct / sum(c["gold_status"] == "comparative" for c in cases)},
        },
    }


def _article_metrics(rows: list[dict[str, Any]], k: int) -> dict[str, Any]:
    denominator = len(rows)
    hits = [any(r.get("source_article_id") in row["expected_source_article_ids"] for r in row["results"][:k]) for row in rows]
    reciprocal = []
    for row in rows:
        rank = next((i for i, r in enumerate(row["results"][:5], 1) if r.get("source_article_id") in row["expected_source_article_ids"]), None)
        reciprocal.append(1 / rank if rank else 0)
    return {"hit_at_k": {"numerator": sum(hits), "denominator": denominator, "value": sum(hits) / denominator if denominator else None},
            "mrr_at_5": {"numerator": sum(reciprocal), "denominator": denominator, "value": sum(reciprocal) / denominator if denominator else None}}


def evaluate_retrieval(*, questions: list[dict[str, Any]], index_dir: Path, chunks_path: Path,
                       model: str, retriever: Any = None) -> dict[str, Any]:
    baseline = json.loads(BASELINE_FIXTURE.read_text(encoding="utf-8"))
    cases = [q for q in baseline["preguntas"] if q["respondible"]]
    active = retriever or SemanticRetriever(index_dir=index_dir, chunks_path=chunks_path, model=model)
    before = active.integrity_snapshot()
    runs: dict[str, list[dict[str, Any]]] = {name: [] for name in ("baseline_unfiltered", "oracle_filter", "automatic_filter")}
    auto_coverage = avoided = leakage = 0
    try:
        for q in cases:
            gold = q["jurisdiccion"]
            decision = detect_jurisdiction(q["pregunta"])
            for name, route in (("baseline_unfiltered", None), ("oracle_filter", gold)):
                rows = active.retrieve(q["pregunta"], k=5, jurisdiccion=route)
                runs[name].append({"id": q["id"], "question": q["pregunta"], "expected_source_article_ids": q["fuentes_esperadas"], "gold_jurisdiction": gold, "route_status": "retrieved", "results": rows})
            if decision["status"] == "identified" and len(decision["jurisdictions"]) == 1:
                auto_coverage += 1
                route = decision["jurisdictions"][0]
                rows = active.retrieve(q["pregunta"], k=5, jurisdiccion=route)
                leakage += sum(r.get("jurisdiccion") != gold for r in rows)
                runs["automatic_filter"].append({"id": q["id"], "question": q["pregunta"], "expected_source_article_ids": q["fuentes_esperadas"], "gold_jurisdiction": gold, "route_status": "retrieved", "selected_jurisdiction": route, "results": rows})
            else:
                avoided += 1
                runs["automatic_filter"].append({"id": q["id"], "question": q["pregunta"], "expected_source_article_ids": q["fuentes_esperadas"], "gold_jurisdiction": gold, "route_status": decision["status"], "selected_jurisdiction": None, "results": []})
        after = active.integrity_snapshot()
        if before != after:
            raise RuntimeError("La colección/manifest cambió durante la evaluación read-only")
    except Exception:
        after = active.integrity_snapshot()
        raise
    metrics = {}
    for strategy, rows in runs.items():
        metrics[strategy] = {f"hit_at_{k}": _article_metrics(rows, k)["hit_at_k"] for k in (1, 3, 5)}
        metrics[strategy]["mrr_at_5"] = _article_metrics(rows, 5)["mrr_at_5"]
    # Passage-level review is deliberately distinct from article-level Hit@k.
    passage_review = {
        "nacional_respondible_deber_votar": {
            "retrieved_expected_article": True,
            "complete_evidence_in_top3": False,
            "observed_limitation": "El top incluye el chunk 1 del art. 12, pero no la continuación con inciso d), certificación del empleador y carácter optativo; el artículo aparece como hit sin cubrir todo el pasaje pedido.",
            "stage": "fragmentation/retrieval",
        },
        "pba_respondible_representacion": {
            "retrieved_expected_article": True,
            "complete_evidence_in_top3": True,
            "observed_limitation": "El chunk superior del art. 13 contiene el dato preguntado (92 diputados y 46 senadores); no se interpreta la nota histórica como texto principal.",
            "stage": "passage inspection",
        },
        "santa_fe_respondible_autoridad_mesa": {
            "retrieved_expected_article": False,
            "complete_evidence_in_top3": False,
            "observed_limitation": "El art. 4 no aparece en top-5; el vecino art. 67 trata autoridades de mesa pero no es la definición consultada. El art. 4 existe en los chunks versionados.",
            "stage": "retrieval",
        },
    }
    return {"status": "completed", "model": model, "k": [1, 3, 5], "fixed_question_count": len(cases),
            "passage_review": passage_review,
            "end_to_end_denominator": len(cases), "auto_filter_coverage": {"numerator": auto_coverage, "denominator": len(cases)},
            "clarification_attempts_avoided": {"count": avoided, "denominator": len(cases)},
            "wrong_jurisdiction_source_leakage": {"count": leakage, "scope": "automatic-filter retrieved chunks"},
            "metrics": metrics, "runs": runs, "index_integrity": {"before": before, "after": after, "unchanged": before == after}}


def run(*, fixture_path: Path = FIXTURE, report_path: Path = REPORT, markdown_path: Path = MARKDOWN,
        index_dir: Path = DEFAULT_INDEX, chunks_path: Path = DEFAULT_INPUT, model: str = DEFAULT_MODEL,
        with_retrieval: bool = False, retriever: Any = None) -> dict[str, Any]:
    raw = fixture_path.read_bytes()
    fixture = json.loads(raw)
    questions = fixture["preguntas"]
    if len(questions) != 40 or len({q["id"] for q in questions}) != 40:
        raise ValueError("El fixture debe contener exactamente 40 IDs únicos")
    cases = []
    for q in questions:
        detected = detect_jurisdiction(q["pregunta"])
        cases.append({**q, "predicted_status": detected["status"], "predicted_jurisdictions": detected["jurisdictions"],
                      "signals": detected["signals"], "reason": detected["reason"],
                      "clarification_question": detected["clarification_question"],
                      "exact_match": detected["status"] == q["gold_status"] and detected["jurisdictions"] == q["gold_jurisdictions"]})
    report: dict[str, Any] = {"version": 1, "fixture": str(fixture_path), "fixture_sha256": hashlib.sha256(raw).hexdigest(),
                              "fixture_count": len(cases), "classification": {"cases": cases, "metrics": classification_metrics(cases)},
                              "retrieval_impact": {"status": "not requested"}}
    if with_retrieval:
        try:
            report["retrieval_impact"] = evaluate_retrieval(questions=questions, index_dir=index_dir, chunks_path=chunks_path, model=model, retriever=retriever)
        except Exception as exc:
            report["retrieval_impact"] = {"status": "blocked", "reason": f"{type(exc).__name__}: {exc}", "automatic_rebuild": False}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def render_markdown(report: dict[str, Any]) -> str:
    m = report["classification"]["metrics"]
    lines = ["# Evaluación de enrutamiento jurisdiccional", "",
             f"Fixture independiente: `{report['fixture_count']}` casos; SHA-256 `{report['fixture_sha256']}`. No se usa Ollama/Chroma para clasificar.", "",
             f"Coincidencia exacta status+jurs.: {m['exact_routing_match']['numerator']}/{m['exact_routing_match']['denominator']} = {m['exact_routing_match']['value']:.3f}.",
             f"Cobertura filtro único: {m['auto_filter_coverage_single_identifiable']['numerator']}/{m['auto_filter_coverage_single_identifiable']['denominator']}.",
             f"Ruteo correcto entre casos identificables: {m['correct_auto_filter_rate_single_identifiable']['numerator']}/{m['correct_auto_filter_rate_single_identifiable']['denominator']}.",
             f"Misruteo dañino: {m['harmful_misrouting']['count']}/{m['harmful_misrouting']['denominator']} = {m['harmful_misrouting']['rate']:.3f}.",
             f"Aclaración adecuada: {m['clarification_abstention_appropriateness']['numerator']}/{m['clarification_abstention_appropriateness']['denominator']}.", "",
             "## Matriz de confusión (filas reales, columnas predichas)", "",
             "| Real \\ Predicho | " + " | ".join(STATUSES) + " |", "|---|" + "---:|" * len(STATUSES)]
    for status in STATUSES:
        lines.append("| " + status + " | " + " | ".join(str(m["confusion_matrix"][status][p]) for p in STATUSES) + " |")
    lines += ["", "## Métricas por jurisdicción", "", "| Jurisdicción | Precisión (TP/predichos) | Recall (TP/reales) |", "|---|---:|---:|"]
    for j, values in m["per_jurisdiction"].items():
        p, r = values["precision"], values["recall"]
        lines.append(f"| {j} | {p['numerator']}/{p['denominator']} ({p['value'] if p['value'] is not None else 'n/a'}) | {r['numerator']}/{r['denominator']} ({r['value'] if r['value'] is not None else 'n/a'}) |")
    lines += ["", "## Errores observados", ""]
    errors = [c for c in report["classification"]["cases"] if not c["exact_match"]]
    lines.extend([f"- `{c['id']}` {c['pregunta']!r}: esperado {c['gold_status']}/{c['gold_jurisdictions']}, predicho {c['predicted_status']}/{c['predicted_jurisdictions']}. {c['reason']}" for c in errors] or ["- Ninguno en este fixture; esto no valida casos no representados."])
    retrieval = report.get("retrieval_impact", {})
    lines += ["", "## Impacto en recuperación local", ""]
    if retrieval.get("status") == "completed":
        lines.append(f"Índice intacto: `{retrieval['index_integrity']['unchanged']}`. Cobertura auto {retrieval['auto_filter_coverage']['numerator']}/{retrieval['auto_filter_coverage']['denominator']}; aclaraciones que evitaron retrieval: {retrieval['clarification_attempts_avoided']['count']}; fugas cross-jurisdicción auto: {retrieval['wrong_jurisdiction_source_leakage']['count']} chunks.")
        for name, values in retrieval["metrics"].items():
            lines.append(f"- **{name}** (denominador E2E={retrieval['end_to_end_denominator']}; no ruteadas cuentan como fallo): " + ", ".join(f"{k}={v['numerator']}/{v['denominator']} ({v['value']:.3f})" for k,v in values.items()))
        lines.append("Los hits son a nivel artículo, no demuestran cobertura completa del pasaje. Consulte el JSON para resultados íntegros y páginas.")
        lines.append("Inspección manual de los tres pasajes: " + " ".join(f"`{key}`: {value['observed_limitation']}" for key, value in retrieval.get("passage_review", {}).items()))
    else:
        lines.append(f"No ejecutada/completada: `{retrieval.get('status')}`. {retrieval.get('reason', 'Ejecute con --with-retrieval si el índice local y Ollama están disponibles.')}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--markdown", type=Path, default=MARKDOWN)
    parser.add_argument("--index-dir", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--with-retrieval", action="store_true", help="habilita comparación local de índice sin reconstruirlo")
    args = parser.parse_args()
    report = run(fixture_path=args.fixture, report_path=args.report, markdown_path=args.markdown,
                 index_dir=args.index_dir, chunks_path=args.chunks, model=args.model, with_retrieval=args.with_retrieval)
    print(f"Evaluación offline: {args.report}; fixture SHA-256={report['fixture_sha256']}; exactitud={report['classification']['metrics']['exact_routing_match']['numerator']}/{report['fixture_count']}; retrieval={report['retrieval_impact']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
