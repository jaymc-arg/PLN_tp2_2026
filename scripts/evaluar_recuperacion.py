"""Evalúa retrieval por artículo; no genera respuestas ni altera el índice."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from importlib import import_module

_recuperar = import_module("scripts.03_recuperar")
SemanticRetriever = _recuperar.SemanticRetriever
build_evidence_context = _recuperar.build_evidence_context
_indexar = import_module("scripts.02_indexar")
COLLECTION = _indexar.COLLECTION
DEFAULT_INDEX = _indexar.DEFAULT_INDEX
DEFAULT_INPUT = _indexar.DEFAULT_INPUT
DEFAULT_MODEL = _indexar.DEFAULT_MODEL

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_PATH = ROOT / "evalucacion/preguntas.json"
REVIEW_PATH = ROOT / "evalucacion/revision_manual_recuperacion_qwen3_0_6b.json"
REPORT_PATH = ROOT / "evalucacion/reporte_recuperacion_qwen3_0_6b.json"
MARKDOWN_PATH = ROOT / "evalucacion/validacion_recuperacion_qwen3_0_6b.md"
PLOT_PATH = ROOT / "evalucacion/distancias_recuperacion_qwen3_0_6b.svg"
MAX_K = 5


def display_path(path: Path) -> str:
    """Presenta rutas relativas al proyecto cuando es posible para reportes legibles."""
    resolved = Path(path).expanduser().resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)
PARAPHRASE = "¿En qué situaciones puede una persona electora quedar exceptuada de votar en una elección nacional?"
DISTANCE_NOTE = "Distancia nativa de Chroma: un valor menor indica un vecino más cercano, no una probabilidad de corrección."


def article_metrics(results: list[dict[str, Any]], expected_article_ids: list[str]) -> dict[str, Any]:
    """Calcula Hit@K y rango recíproco a nivel de artículo fuente.

    Un chunk del artículo esperado cuenta como hit, aunque no incluya el
    pasaje que responde: esa cobertura exige revisión separada.
    """
    expected = set(expected_article_ids)
    ranks = [r["rank"] for r in results if r["source_article_id"] in expected]
    first = min(ranks) if ranks else None
    return {
        "expected_article_ids": expected_article_ids,
        "first_expected_rank": first,
        "hit_at_1": first is not None and first <= 1,
        "hit_at_3": first is not None and first <= 3,
        "hit_at_5": first is not None and first <= 5,
        "reciprocal_rank_at_5": 1 / first if first is not None and first <= 5 else 0.0,
        "metric_unit": "retrieved chunks ranked; binary article hit, repeated chunks do not add extra hits",
    }


def aggregate_metrics(rows: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    """Promedia métricas sobre preguntas positivas, con denominador explícito."""
    metrics = [row[mode]["article_metrics"] for row in rows]
    denominator = len(metrics)
    return {
        "positive_question_denominator": denominator,
        "hit_at_1": sum(m["hit_at_1"] for m in metrics) / denominator if denominator else 0.0,
        "hit_at_3": sum(m["hit_at_3"] for m in metrics) / denominator if denominator else 0.0,
        "hit_at_5": sum(m["hit_at_5"] for m in metrics) / denominator if denominator else 0.0,
        "mrr_at_5": sum(m["reciprocal_rank_at_5"] for m in metrics) / denominator if denominator else 0.0,
        "misses_contribute_zero_to_mrr": True,
        "unit": "article-level binary hit; chunks are not deduplicated before ranking",
    }


def _verify_context(results: list[dict[str, Any]], context: str) -> None:
    """Comprueba que el prompt de evidencia conserva orden, IDs y texto recuperado."""
    cursor = 0
    for number, result in enumerate(results, 1):
        required = [f"[{number}]", f"chunk_id: {result['chunk_id']}",
                    f"source_article_id: {result['source_article_id']}",
                    f"jurisdiccion: {result['jurisdiccion']}", f"ley: {result['ley']}",
                    f"articulo: {result['articulo']}", f"source: {result['source']}",
                    "texto:", result["text"]]
        if "pagina_inicio" in result:
            required.insert(-2, f"paginas_articulo: {result['pagina_inicio']}–{result['pagina_fin']}")
        for value in required:
            position = context.find(value, cursor)
            if position < 0:
                raise ValueError(f"Contexto no conserva en orden el campo/texto de {result['chunk_id']}: {value[:80]!r}")
            cursor = position + len(value)


def validate_manual_review(review: dict[str, Any], questions: list[dict[str, Any]],
                           retrieval_map: dict[tuple[str, str], list[dict[str, Any]]]) -> dict[str, Any]:
    """Comprueba las citas manuales contra el texto íntegro efectivamente recuperado."""
    positives = {q["id"] for q in questions if q["respondible"]}
    negatives = {q["id"] for q in questions if not q["respondible"]}
    fixed_positive = review.get("fixed_positive", {})
    fixed_negative = review.get("negative", {})
    for question_id in positives:
        if question_id not in fixed_positive:
            raise ValueError(f"Falta inspección humana positiva: {question_id}")
        for mode in ("unfiltered", "jurisdiction_filtered"):
            manual = fixed_positive[question_id].get(mode)
            ranked = retrieval_map[(question_id, mode)][:3]
            if manual is None:
                raise ValueError(f"Falta modo {mode} para inspección {question_id}")
            if manual.get("top3_passage_coverage") not in {"yes", "partial", "no"}:
                raise ValueError(f"Cobertura manual inválida: {question_id}/{mode}")
            by_id = {r["chunk_id"]: r for r in ranked}
            expected_top3_ids = [r["chunk_id"] for r in ranked]
            if manual.get("reviewed_top3_chunk_ids") != expected_top3_ids:
                raise ValueError(f"La inspección no identifica exactamente el top-3 revisado: {question_id}/{mode}")
            citations = manual.get("evidence", []) + manual.get("retrieved_nonanswering_matches", [])
            for evidence in citations:
                chunk_id, quote = evidence.get("chunk_id"), evidence.get("quote", "")
                if chunk_id not in by_id or not quote or quote not in by_id[chunk_id]["text"]:
                    raise ValueError(f"Cita manual no coteja con top-3 real: {question_id}/{chunk_id}")
    for question_id in negatives:
        item = fixed_negative.get(question_id)
        ranked = retrieval_map[(question_id, "unfiltered")][:3]
        expected_top3_ids = [r["chunk_id"] for r in ranked]
        if (not item or item.get("can_substantiate_requested_fact") is not False
                or not item.get("explanation")
                or item.get("reviewed_top3_chunk_ids") != expected_top3_ids):
            raise ValueError(f"Falta inspección de no-respuesta/top-3: {question_id}")
        by_id = {r["chunk_id"]: r for r in ranked}
        for evidence in item.get("retrieved_nonanswering_matches", []):
            chunk_id, quote = evidence.get("chunk_id"), evidence.get("quote", "")
            if chunk_id not in by_id or not quote or quote not in by_id[chunk_id]["text"]:
                raise ValueError(f"Cita negativa no coteja con top-3 real: {question_id}/{chunk_id}")
    comparison = review.get("k_comparison", {})
    if comparison.get("question_id") not in positives or not comparison.get("k1_coverage") or not comparison.get("k3_coverage"):
        raise ValueError("Falta la comparación manual k=1/k=3 sobre una pregunta positiva")
    paraphrase = review.get("paraphrase", {})
    paraphrase_results = retrieval_map.get(("__paraphrase__", "unfiltered"), [])
    if paraphrase_results:
        if paraphrase.get("reviewed_top3_chunk_ids") != [r["chunk_id"] for r in paraphrase_results[:3]]:
            raise ValueError("La paráfrasis no identifica exactamente el top-3 revisado")
        by_id = {r["chunk_id"]: r for r in paraphrase_results}
        for evidence in paraphrase.get("evidence", []):
            if evidence.get("chunk_id") not in by_id or evidence.get("quote", "") not in by_id[evidence["chunk_id"]]["text"]:
                raise ValueError("Cita de paráfrasis no coteja con el retrieval real")
    return review


def make_distance_svg(results: list[dict[str, Any]], question: str) -> str:
    """Dibuja distancias nativas con sus etiquetas; no las convierte en probabilidades."""
    rows = [r for r in results[:3] if isinstance(r.get("distance"), (int, float))]
    width, row_height, left, right = 900, 58, 310, 850
    height = 135 + row_height * max(1, len(rows))
    max_distance = max((float(r["distance"]) for r in rows), default=1.0) or 1.0
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="#fff"/>',
             '<text x="24" y="30" font-family="sans-serif" font-size="18" font-weight="bold">',
             f'{html.escape(question)}</text>',
             '<text x="24" y="57" font-family="sans-serif" font-size="13">Chroma native distance — smaller is closer; not a probability</text>']
    for index, result in enumerate(rows):
        y = 91 + index * row_height
        label = f"{result['rank']}. {result['chunk_id']}"
        bar_width = (float(result["distance"]) / max_distance) * (right - left)
        parts.extend([
            f'<text x="24" y="{y + 18}" font-family="sans-serif" font-size="12">{html.escape(label)}</text>',
            f'<rect x="{left}" y="{y}" width="{bar_width:.2f}" height="22" fill="#3b82f6"/>',
            f'<text x="{min(left + bar_width + 8, right - 5):.2f}" y="{y + 17}" font-family="sans-serif" font-size="12">{float(result["distance"]):.6f}</text>',
        ])
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def evaluate(questions_path: Path = QUESTIONS_PATH, *, index_dir: Path = DEFAULT_INDEX,
             chunks_path: Path = DEFAULT_INPUT, model: str = DEFAULT_MODEL,
             report_path: Path = REPORT_PATH, markdown_path: Path = MARKDOWN_PATH,
             plot_path: Path = PLOT_PATH, review_path: Path = REVIEW_PATH,
             retriever: SemanticRetriever | None = None,
             existing_report_path: Path | None = None,
             baseline_report_path: Path | None = None) -> dict[str, Any]:
    """Evalúa recuperación sobre preguntas fijas, con y sin filtro jurisdiccional.

    Separa métricas automáticas por artículo y revisión humana del pasaje
    que permite contestar; no invoca generación.
    """
    question_bytes = questions_path.read_bytes()
    fixture = json.loads(question_bytes)
    questions = fixture["preguntas"]
    positives = [q for q in questions if q["respondible"]]
    negatives = [q for q in questions if not q["respondible"]]
    if len(positives) != 3 or len(negatives) != 2:
        raise ValueError("Se esperan exactamente tres positivas y dos negativas fijas")

    if existing_report_path is not None:
        report = json.loads(existing_report_path.read_text(encoding="utf-8"))
        if report.get("evaluation_questions_sha256") != hashlib.sha256(question_bytes).hexdigest():
            raise ValueError("El reporte previo no pertenece a este fixture fijo")
        if report.get("embedding_model") != model:
            raise ValueError("El reporte previo no corresponde al modelo solicitado")
        if report.get("question_count") != 5 or report.get("max_k") != MAX_K:
            raise ValueError("El reporte previo no contiene la evaluación completa top-5")
    else:
        retriever = retriever or SemanticRetriever(index_dir=index_dir, chunks_path=chunks_path, model=model)
        integrity_before = retriever.integrity_snapshot()
        positive_rows = []
        negative_rows = []
        retrieval_map: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for question in positives:
            unfiltered = retriever.retrieve(question["pregunta"], k=MAX_K)
            filtered = retriever.retrieve(question["pregunta"], k=MAX_K,
                                          jurisdiccion=question["jurisdiccion"])
            retrieval_map[(question["id"], "unfiltered")] = unfiltered
            retrieval_map[(question["id"], "jurisdiction_filtered")] = filtered
            positive_rows.append({
                "id": question["id"], "question": question["pregunta"],
                "jurisdiccion": question["jurisdiccion"],
                "expected_article_ids": question["fuentes_esperadas"],
                "reference_answer": question["respuesta_referencia"],
                "unfiltered": {"filter": None, "results": unfiltered,
                               "article_metrics": article_metrics(unfiltered, question["fuentes_esperadas"])},
                "jurisdiction_filtered": {"filter": question["jurisdiccion"], "results": filtered,
                                          "article_metrics": article_metrics(filtered, question["fuentes_esperadas"])},
                "filter_comparison": {
                    "top1_changed": (unfiltered[0]["chunk_id"] if unfiltered else None) !=
                                    (filtered[0]["chunk_id"] if filtered else None),
                    "top3_ids_changed": [r["chunk_id"] for r in unfiltered[:3]] !=
                                        [r["chunk_id"] for r in filtered[:3]],
                },
                "answer_passage_review": {"status": "pending human inspection"},
            })
        for question in negatives:
            results = retriever.retrieve(question["pregunta"], k=MAX_K)
            retrieval_map[(question["id"], "unfiltered")] = results
            negative_rows.append({
                "id": question["id"], "question": question["pregunta"],
                "filter": None, "results": results,
                "answerability_review": {"can_substantiate_requested_fact": None,
                                          "explanation": "pending human inspection"},
            })
        paraphrase_results = retriever.retrieve(PARAPHRASE, k=MAX_K)
        context_results = retrieval_map[(positives[0]["id"], "unfiltered")][:3]
        context = build_evidence_context(context_results)
        _verify_context(context_results, context)
        integrity_after = retriever.integrity_snapshot()
        if integrity_before != integrity_after:
            raise RuntimeError("El índice/manifest cambió durante la recuperación; revisión abortada")
        report = {
            "version": 1,
            "evaluation_questions_sha256": hashlib.sha256(question_bytes).hexdigest(),
            "question_count": len(questions), "positive_count": len(positives), "negative_count": len(negatives),
            "max_k": MAX_K, "distance_semantics": DISTANCE_NOTE,
            "embedding_model": model, "collection": COLLECTION,
            "positive_questions": positive_rows, "negative_questions": negative_rows,
            "aggregate_positive_metrics": {
                "unfiltered": aggregate_metrics(positive_rows, "unfiltered"),
                "jurisdiction_filtered": aggregate_metrics(positive_rows, "jurisdiction_filtered"),
                "denominator": "three positive questions; misses count zero; negatives excluded",
            },
            "paraphrase_trial": {"label": "separate paraphrase; excluded from fixed metrics",
                                 "question": PARAPHRASE, "expected_article_ids": ["nacional_19945_art_12"],
                                 "results": paraphrase_results},
            "k_comparison": {"question_id": positives[0]["id"], "question": positives[0]["pregunta"],
                             "source_ranking": "same unfiltered top-5 result; no second query",
                             "k1": {"results": context_results[:1]},
                             "k3": {"results": context_results[:3]},
                             "manual_coverage": "pending human inspection"},
            "numbered_evidence_context": {"question_id": positives[0]["id"],
                                          "source_chunk_ids": [r["chunk_id"] for r in context_results],
                                          "text": context},
            "distance_plot": {"path": display_path(plot_path), "question": positives[0]["pregunta"],
                              "ranks": [r["rank"] for r in context_results],
                              "distances": [r["distance"] for r in context_results]},
            "index_integrity": {"before_queries": integrity_before, "after_queries": integrity_after,
                                "unchanged": integrity_before == integrity_after},
            "manual_review": {"status": "pending", "source": display_path(review_path)},
        }

    review = None
    if review_path.is_file():
        review = json.loads(review_path.read_text(encoding="utf-8"))
        if review.get("embedding_model", model) != model:
            raise ValueError("La revisión manual no corresponde al modelo solicitado")
        review = validate_manual_review(review, questions, _retrieval_map(report))
        _apply_manual_review(report, review, review_path)
    if baseline_report_path is not None:
        baseline = json.loads(baseline_report_path.read_text(encoding="utf-8"))
        report["baseline_comparison"] = compare_reports(baseline, report)
        report["baseline_comparison"]["source"] = display_path(baseline_report_path)
    report["artifacts"] = {"report": display_path(report_path), "review": display_path(review_path),
                           "markdown": display_path(markdown_path), "plot": display_path(plot_path)}
    report["distance_plot"]["path"] = display_path(plot_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    svg_data = make_distance_svg(report["positive_questions"][0]["unfiltered"]["results"],
                                 report["positive_questions"][0]["question"])
    plot_path.parent.mkdir(parents=True, exist_ok=True)
    plot_path.write_text(svg_data, encoding="utf-8")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"Evaluación guardada: {report_path}; 5 preguntas; k={MAX_K}; "
          f"índice intacto={report.get('index_integrity', {}).get('unchanged', 'reutilizó reporte previo')}")
    print(f"Distancias SVG: {plot_path}; manual review={'complete' if review else 'pending'}")
    return report


def _retrieval_map(report: dict[str, Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Indexa rankings guardados por pregunta y modo para contrastar revisiones."""
    mapping = {}
    for row in report["positive_questions"]:
        mapping[(row["id"], "unfiltered")] = row["unfiltered"]["results"]
        mapping[(row["id"], "jurisdiction_filtered")] = row["jurisdiction_filtered"]["results"]
    for row in report["negative_questions"]:
        mapping[(row["id"], "unfiltered")] = row["results"]
    mapping[("__paraphrase__", "unfiltered")] = report["paraphrase_trial"]["results"]
    return mapping


def _apply_manual_review(report: dict[str, Any], review: dict[str, Any], review_path: Path) -> None:
    """Adjunta juicios manuales sin confundirlos con métricas automáticas."""
    for row in report["positive_questions"]:
        row["answer_passage_review"] = review["fixed_positive"][row["id"]]
    for row in report["negative_questions"]:
        row["answerability_review"] = review["negative"][row["id"]]
    comparison = review["k_comparison"]
    report["k_comparison"]["manual_coverage"] = comparison
    report["paraphrase_trial"]["manual_review"] = review.get("paraphrase", {})
    if review.get("model_comparison_notes"):
        report["model_comparison_notes"] = review["model_comparison_notes"]
    report.pop("human_review", None)
    report["manual_review"] = {"status": "complete; quotes validated verbatim against retrieved texts",
                               "source": display_path(review_path),
                               "method": "Manual text inspection by the coding agent; quote checks are consistency aids, not legal QA. Student/legal review remains separate."}


def compare_reports(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Compara resultados ya guardados; nunca compara distancias entre espacios."""
    if baseline["evaluation_questions_sha256"] != current["evaluation_questions_sha256"]:
        raise ValueError("La comparación requiere el mismo fixture fijo")
    metrics = ("hit_at_1", "hit_at_3", "hit_at_5", "mrr_at_5")
    aggregate = {}
    rows = []
    by_id = {row["id"]: row for row in baseline["positive_questions"]}
    for mode in ("unfiltered", "jurisdiction_filtered"):
        old = baseline["aggregate_positive_metrics"][mode]
        new = current["aggregate_positive_metrics"][mode]
        if old["positive_question_denominator"] != new["positive_question_denominator"]:
            raise ValueError("Denominadores incompatibles")
        aggregate[mode] = {key: {"baseline": old[key], "current": new[key],
                                 "absolute_delta": new[key] - old[key]} for key in metrics}
        for row in current["positive_questions"]:
            prior = by_id[row["id"]]
            pair = {"question_id": row["id"], "mode": mode}
            for label, entry in (("baseline", prior), ("current", row)):
                results = entry[mode]["results"]
                pair[label] = {
                    "metrics": entry[mode]["article_metrics"],
                    "passage_coverage": entry.get("answer_passage_review", {}).get(mode, {}).get("top3_passage_coverage", "pending"),
                    "wrong_jurisdiction_top3": sum(r["jurisdiccion"] != row["jurisdiccion"] for r in results[:3]),
                    "wrong_jurisdiction_top5": sum(r["jurisdiccion"] != row["jurisdiccion"] for r in results),
                }
            rows.append(pair)
    tracked = {}
    for chunk_id in ("nacional_19945_art_12__chunk_0002", "santa_fe_14478_art_4__chunk_0001"):
        tracked[chunk_id] = {}
        for label, report in (("baseline", baseline), ("current", current)):
            tracked[chunk_id][label] = {
                f"{row['id']}/{mode}": next((i for i, r in enumerate(row[mode]["results"], 1)
                                            if r["chunk_id"] == chunk_id), None)
                for row in report["positive_questions"] for mode in ("unfiltered", "jurisdiction_filtered")
                if row["expected_article_ids"] == [chunk_id.split("__chunk_")[0]]
            }
    paraphrase = {}
    for label, report in (("baseline", baseline), ("current", current)):
        trial = report["paraphrase_trial"]
        paraphrase[label] = article_metrics(trial["results"], trial["expected_article_ids"])
    return {"baseline_model": baseline["embedding_model"], "current_model": current["embedding_model"],
            "aggregate": aggregate, "positive_questions": rows,
            "tracked_chunk_ranks": tracked, "paraphrase": paraphrase}


def render_comparison(report: dict[str, Any]) -> list[str]:
    """Convierte resultados de comparación entre modelos en filas explicativas."""
    comparison = report.get("baseline_comparison")
    if not comparison:
        return []
    lines = [f"## Comparación {comparison['baseline_model']} (histórico) vs {comparison['current_model']}", "",
             f"Baseline conservado: `{comparison['source']}`. Mismas preguntas, chunks, filtros y k=5; sin prefijos/instrucciones adicionales para consultas ni documentos. No se ejecutó generación.", "",
             "Las distancias de espacios de embeddings diferentes NO son puntajes de calidad comparables.", "",
             "| Modo | Métrica | BGE-M3 | Qwen | Δ absoluto |", "|---|---|---:|---:|---:|"]
    for mode, metrics in comparison["aggregate"].items():
        for metric, values in metrics.items():
            lines.append(f"| {mode} | {metric} | {values['baseline']:.3f} | {values['current']:.3f} | {values['absolute_delta']:+.3f} |")
    lines.extend(["", "| Pregunta/modo | Primer rango BGE→Qwen | H@1/3/5 BGE→Qwen | RR@5 BGE→Qwen | Pasaje BGE→Qwen | Otra jurisdicción top-3/top-5 BGE→Qwen |",
                  "|---|---|---|---|---|---|"])
    for row in comparison["positive_questions"]:
        old, new = row["baseline"], row["current"]
        a, b = old["metrics"], new["metrics"]
        hits = lambda m: "/".join(str(int(m[key])) for key in ("hit_at_1", "hit_at_3", "hit_at_5"))
        lines.append(f"| {row['question_id']}/{row['mode']} | {a['first_expected_rank']}→{b['first_expected_rank']} | {hits(a)}→{hits(b)} | {a['reciprocal_rank_at_5']:.3f}→{b['reciprocal_rank_at_5']:.3f} | {old['passage_coverage']}→{new['passage_coverage']} | {old['wrong_jurisdiction_top3']}/{old['wrong_jurisdiction_top5']}→{new['wrong_jurisdiction_top3']}/{new['wrong_jurisdiction_top5']} |")
    lines.extend(["", "Rangos de pasajes específicos (`None` = no recuperado en top-5; no significa ausente del corpus):", "",
                  "```json", json.dumps(comparison["tracked_chunk_ranks"], indent=2), "```", "",
                  "Paráfrasis separada, primer rango del artículo esperado: "
                  f"{comparison['paraphrase']['baseline']['first_expected_rank']}→{comparison['paraphrase']['current']['first_expected_rank']}.", ""])
    lines.extend(report.get("model_comparison_notes", []))
    lines.append("")
    return lines


def render_markdown(report: dict[str, Any]) -> str:
    """Construye un informe auditable con rankings, pasajes y métricas."""
    lines = [f"# TP2-RAG-05 — recuperación semántica: {report['embedding_model']}", "",
             f"Se usó Chroma persistente y Ollama `{report['embedding_model']}`; no hubo generación. " + DISTANCE_NOTE,
             "Hit@k/MRR se calculan a nivel de artículo y no prueban que un chunk contenga la respuesta.", "",
             "## Métricas agregadas sobre las tres positivas", "",
             "| Modo | Denominador | Hit@1 | Hit@3 | Hit@5 | MRR@5 |", "|---|---:|---:|---:|---:|---:|"]
    for mode, title in (("unfiltered", "Sin filtro"), ("jurisdiction_filtered", "Filtrada por jurisdicción")):
        m = report["aggregate_positive_metrics"][mode]
        lines.append(f"| {title} | {m['positive_question_denominator']} | {m['hit_at_1']:.3f} | {m['hit_at_3']:.3f} | {m['hit_at_5']:.3f} | {m['mrr_at_5']:.3f} |")
    headers = ["Pregunta", "Evidencia esperada", "Hit@1 sin filtro", "Hit@3 sin filtro", "Hit@5 sin filtro", "RR@5 sin filtro", "Hit@1 filtrada", "Hit@3 filtrada", "Hit@5 filtrada", "RR@5 filtrada", "Cambio top-1/top-3 por filtro", "Cobertura pasaje top-3 (sin/con filtro)", "Fuente/chunk/distancia top-3 sin filtro", "Limitación observada", "Diagnóstico", "Experimento futuro"]
    lines.extend(["", "Denominador: tres positivas; los fallos aportan 0 al MRR; negativas excluidas. Los chunks repetidos permanecen en el ranking, y el hit por artículo es binario.", "",
                  "## Inspección diagnóstica (una fila por pregunta fija)", "",
                  "La inspección textual manual la realizó el agente de código sobre los chunks recuperados completos; no equivale a revisión jurídica ni a verificación personal del estudiante.", "",
                  "| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"])
    def metric_cells(row: dict[str, Any], mode: str) -> list[str]:
        """Formatea Hit@K y MRR para cada modo de recuperación."""
        m = row[mode]["article_metrics"]
        return [str(int(m["hit_at_1"])), str(int(m["hit_at_3"])), str(int(m["hit_at_5"])),
                f"{m['reciprocal_rank_at_5']:.3f}"]
    def passage_text(item: dict[str, Any]) -> str:
        """Presenta evidencia revisada y pasajes recuperados pero insuficientes."""
        citations = item.get("evidence", []) + item.get("retrieved_nonanswering_matches", [])
        quotes = "; ".join(f"`{e['chunk_id']}`: “{e['quote']}”" for e in citations) or "sin pasaje esperado"
        return f"{item.get('top3_passage_coverage', 'pending')}: {quotes}"
    def source_text(results: list[dict[str, Any]]) -> str:
        """Conserva identificadores, páginas y distancias visibles en el informe."""
        return "; ".join(f"{r['chunk_id']} ({r['source']}" +
                          (f", pp. {r['pagina_inicio']}–{r['pagina_fin']}" if "pagina_inicio" in r else "") +
                          f"; d={r['distance']:.6f})" for r in results[:3])
    for row in report["positive_questions"]:
        review = row.get("answer_passage_review", {})
        baseline, filtered_review = review.get("unfiltered", {}), review.get("jurisdiction_filtered", {})
        expected = f"{row['expected_article_ids']}; {row['reference_answer']}"
        comparison = row["filter_comparison"]
        cells = [row["id"], expected, *metric_cells(row, "unfiltered"), *metric_cells(row, "jurisdiction_filtered"),
                 f"top-1={'cambió' if comparison['top1_changed'] else 'igual'}; top-3={'cambió' if comparison['top3_ids_changed'] else 'igual'}",
                 f"sin filtro: {passage_text(baseline)}; filtrada: {passage_text(filtered_review)}",
                 source_text(row["unfiltered"]["results"]), baseline.get("limitation", "sin anotación"),
                 baseline.get("diagnostic_category", "pendiente"), baseline.get("next_experiment", "—")]
        lines.append("| " + " | ".join(cells) + " |")
    for row in report["negative_questions"]:
        review = row.get("answerability_review", {})
        cells = [row["id"], "hecho ausente: resultados presidenciales 2023 o rendiciones reales",
                 "n/a", "n/a", "n/a", "n/a", "—", "—", "—", "—", "n/a (negativa; sin filtro)",
                 f"no: {review.get('explanation', 'pending')}", source_text(row["results"]),
                 "vecinos legales próximos no son la evidencia factual pedida", "not answerable",
                 "incorporar fuente oficial de resultados/rendiciones en una etapa futura, no inferirla de leyes"]
        lines.append("| " + " | ".join(cells) + " |")
    paraphrase = report["paraphrase_trial"].get("manual_review", {})
    lines.extend(["", "## Filtros, k, paráfrasis y evidencia", "",
                  "Para cada positiva se consultó una vez sin filtro y una vez con jurisdicción; las dos negativas se consultaron sin filtro. Cada condición usa k=5; top-1/top-3/top-5 se obtienen cortando el mismo ranking. El JSON conserva todos los textos top-5, IDs, fuentes/páginas cuando existen y distancias nativas.", "",
                  f"Paráfrasis separada (fuera de métricas): “{report['paraphrase_trial']['question']}”. {paraphrase.get('assessment', 'Revisión pendiente')}", "",
                  f"Comparación k=1/k=3 desde el mismo ranking ({report['k_comparison']['question_id']}): {report['k_comparison']['manual_coverage']}", "",
                  f"El preview numerado completo se deriva de los mismos chunks recuperados y se guarda en `{report.get('artifacts', {}).get('report', 'reporte JSON')}`; se validaron orden, IDs, etiquetas y texto sin truncar. No se construye prompt ni se invoca un generador.", "",
                  "Chroma devuelve vecinos cercanos aunque el corpus no responda. Un resultado no vacío no demuestra answerability ni se usa un umbral universal de distancia para abstener.", "",
                  f"Integridad de índice antes/después: `{report.get('index_integrity', {}).get('unchanged', 'reutilizó reporte previo')}`. Distancias reales representativas: `{report['distance_plot']['path']}`. No se midió corrección de respuestas generadas.", ""])
    lines.extend(render_comparison(report))
    if report.get("runtime_metadata"):
        lines.extend(["## Entorno y preservación", "", "```json",
                      json.dumps(report["runtime_metadata"], ensure_ascii=False, indent=2), "```", ""])
    return "\n".join(lines)


def main() -> int:
    """CLI que permite ejecutar evaluación o trabajar con reportes existentes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=QUESTIONS_PATH)
    parser.add_argument("--index-dir", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--markdown", type=Path, default=MARKDOWN_PATH)
    parser.add_argument("--plot", type=Path, default=PLOT_PATH)
    parser.add_argument("--review", type=Path, default=REVIEW_PATH)
    parser.add_argument("--baseline-report", type=Path, default=None,
                        help="comparar métricas/rankings con un reporte histórico del mismo fixture, sin consultarlo")
    parser.add_argument("--usar-reporte-existente", type=Path, default=None,
                        help="rehacer resumen/plot tras anotación manual sin volver a consultar Chroma")
    args = parser.parse_args()
    try:
        evaluate(args.questions, index_dir=args.index_dir, chunks_path=args.chunks, model=args.model,
                 report_path=args.report, markdown_path=args.markdown, plot_path=args.plot,
                 review_path=args.review, existing_report_path=args.usar_reporte_existente,
                 baseline_report_path=args.baseline_report)
    except Exception as exc:
        print(f"Error al evaluar retrieval: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
