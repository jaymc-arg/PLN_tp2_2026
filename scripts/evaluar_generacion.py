"""Evalúa las cinco preguntas fijas usando el enrutamiento de `answer_question()`."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from importlib import import_module

_generar = import_module("scripts.04_generar")
DEFAULT_GENERATION_MODEL = _generar.DEFAULT_GENERATION_MODEL
OLLAMA_BASE_URL = _generar.OLLAMA_BASE_URL
GeneratorUnavailableError = _generar.GeneratorUnavailableError
answer_question = _generar.answer_question
_indexar = import_module("scripts.02_indexar")
DEFAULT_INDEX = _indexar.DEFAULT_INDEX
DEFAULT_INPUT = _indexar.DEFAULT_INPUT
DEFAULT_EMBEDDING_MODEL = _indexar.DEFAULT_MODEL
SemanticRetriever = import_module("scripts.03_recuperar").SemanticRetriever

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_PATH = ROOT / "evalucacion/preguntas.json"
REVIEW_PATH = ROOT / "evalucacion/revision_manual_generacion_enrutada.json"
REPORT_PATH = ROOT / "evalucacion/reporte_generacion_enrutada.json"
MARKDOWN_PATH = ROOT / "evalucacion/validacion_generacion_enrutada.md"
K_COMPARISON_QUESTION_ID = "nacional_respondible_deber_votar"


class EvaluationRuntimeError(RuntimeError):
    """No se pudo verificar el runtime/modelo local solicitado."""


def display_path(path: Path) -> str:
    resolved = Path(path).expanduser().resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _get_json(endpoint: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE_URL}{endpoint}", timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise EvaluationRuntimeError(
            f"No se pudo consultar Ollama en {OLLAMA_BASE_URL}; inicia `ollama serve` y vuelve a intentar."
        ) from exc


def inspect_local_model(model: str) -> dict[str, Any]:
    version = _get_json("/api/version").get("version", "unknown")
    tags = _get_json("/api/tags").get("models", [])
    item = next((entry for entry in tags if entry.get("name") == model or entry.get("model") == model), None)
    if item is None:
        raise EvaluationRuntimeError(
            f"El modelo local {model!r} no está instalado. Ejecuta `ollama pull {model}`; no se cambiará de modelo."
        )
    try:
        client_version = importlib.metadata.version("ollama")
    except importlib.metadata.PackageNotFoundError:
        client_version = "not installed"
    return {
        "ollama_server_version": version,
        "ollama_python_client_version": client_version,
        "api_base_url": OLLAMA_BASE_URL,
        "model_tag": model,
        "model_digest": item.get("digest"),
        "model_size_bytes": item.get("size"),
        "model_details": item.get("details", {}),
        "temperature": 0,
    }


def _generation_record(result: dict[str, Any]) -> dict[str, Any]:
    # Keep full retrieved text and exact prompt context in the evaluation artifact.
    keys = (
        "question", "generation_model", "temperature", "k", "jurisdiccion", "embedding_model",
        "answer", "original_response", "answer_status", "fallback_reason", "abstained",
        "references_used", "citation_check", "source_map", "retrieval_records", "context_sent",
        "model_invoked", "prompt_template_sha256", "routing_status", "jurisdiction_status",
        "jurisdictions", "jurisdiction_source", "routing_signals", "routing_reason",
        "clarification_question", "applied_filter", "per_jurisdiction_retrievals",
    )
    return {key: result.get(key) for key in keys}


def _run_comparison(case: dict[str, Any], k1_result: dict[str, Any]) -> dict[str, Any]:
    k3 = case["generation"]
    return {
        "question_id": case["id"],
        "question": case["question"],
        "prompt_template_sha256": k3["prompt_template_sha256"],
        "model": k3["generation_model"],
        "temperature": k3["temperature"],
        "k1": _generation_record(k1_result),
        "k3": k3,
        "context_chunk_ids_changed": [r["chunk_id"] for r in k1_result["retrieval_records"]] !=
                                      [r["chunk_id"] for r in k3["retrieval_records"]],
        "answer_changed": k1_result["answer"] != k3["answer"],
        "references_changed": k1_result["references_used"] != k3["references_used"],
        "manual_diagnosis": {"status": "pending"},
    }


def validate_manual_review(review: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    actual_cases = {case["id"]: case for case in report.get("fixed_cases", [])}
    question_ids = set(actual_cases)
    cases = review.get("cases", {})
    if set(cases) != question_ids:
        missing, extra = question_ids - set(cases), set(cases) - question_ids
        raise ValueError(f"Revisión manual incompleta/ajena; faltan={sorted(missing)}, sobran={sorted(extra)}")
    allowed_coverage = {"full", "partial", "none", "not_applicable"}
    allowed_support = {"yes", "partially", "no", "unclear", "not_applicable"}
    for question_id, item in cases.items():
        actual_response = actual_cases[question_id].get("generation", {}).get("original_response")
        response_hash = hashlib.sha256((actual_response or "").encode("utf-8")).hexdigest()
        if item.get("original_response_sha256") != response_hash:
            raise ValueError(f"La revisión de {question_id} no corresponde a la respuesta real guardada")
        if item.get("evidence_coverage") not in allowed_coverage:
            raise ValueError(f"evidence_coverage inválida para {question_id}")
        if item.get("answer_supported_by_context") not in allowed_support:
            raise ValueError(f"answer_supported_by_context inválida para {question_id}")
        if not item.get("failure_categories") and not item.get("observations"):
            raise ValueError(f"La revisión necesita observaciones para {question_id}")
    comparison = review.get("k_comparison", {})
    actual_comparison = report.get("k_comparison") or {}
    for key in ("k1", "k3"):
        response = actual_comparison.get(key, {}).get("original_response")
        response_hash = hashlib.sha256((response or "").encode("utf-8")).hexdigest()
        if comparison.get(f"{key}_original_response_sha256") != response_hash:
            raise ValueError(f"La revisión de comparación {key} no corresponde a la respuesta guardada")
    if not comparison.get("k1_vs_k3") or not comparison.get("observations"):
        raise ValueError("Falta el diagnóstico controlado k=1/k=3")
    return review


def apply_manual_review(report: dict[str, Any], review: dict[str, Any], review_path: Path) -> None:
    for case in report["fixed_cases"]:
        case["diagnosis"] = review["cases"][case["id"]]
    report["k_comparison"]["manual_diagnosis"] = review["k_comparison"]
    report["manual_review"] = {
        "status": "complete; coding-agent inspection of supplied evidence and model output",
        "source": display_path(review_path),
        "student_independently_verified": False,
        "note": "This is not an independent legal review; the student should personally verify the interpretation.",
    }


def evaluate(*, questions_path: Path = QUESTIONS_PATH, index_dir: Path = DEFAULT_INDEX,
             chunks_path: Path = DEFAULT_INPUT, model: str = DEFAULT_GENERATION_MODEL,
             embedding_model: str = DEFAULT_EMBEDDING_MODEL, report_path: Path = REPORT_PATH,
             markdown_path: Path = MARKDOWN_PATH, review_path: Path = REVIEW_PATH,
             retriever: Any = None, existing_report_path: Path | None = None) -> dict[str, Any]:
    question_bytes = questions_path.read_bytes()
    fixture = json.loads(question_bytes)
    questions = fixture["preguntas"]
    if len(questions) != 5 or sum(bool(q["respondible"]) for q in questions) != 3:
        raise ValueError("El fixture debe conservar sus cinco preguntas (tres positivas y dos negativas)")
    question_ids = {q["id"] for q in questions}

    if existing_report_path is not None:
        report = json.loads(existing_report_path.read_text(encoding="utf-8"))
        if report.get("evaluation_questions_sha256") != hashlib.sha256(question_bytes).hexdigest():
            raise ValueError("El reporte previo no pertenece al fixture congelado")
        if report.get("routing_protocol") != "answer_question; automatic jurisdiction routing":
            raise ValueError("El reporte previo no usó el protocolo de enrutamiento actual; los resultados históricos no se mezclarán")
        if len(report.get("fixed_cases", [])) != 5:
            raise ValueError("El reporte previo no contiene las cinco ejecuciones")
    else:
        runtime = inspect_local_model(model)
        active_retriever = retriever or SemanticRetriever(
            index_dir=index_dir, chunks_path=chunks_path, model=embedding_model)
        before = active_retriever.integrity_snapshot()
        case_records = []
        run_error = None
        for question_index, question in enumerate(questions):
            expected = {
                "answerable_in_corpus": question["respondible"],
                "expected_answer": question["respuesta_referencia"],
                "expected_source_article_ids": question["fuentes_esperadas"],
            }
            try:
                result = answer_question(
                    question["pregunta"], k=3, model=model,
                    retriever=active_retriever, embedding_model=embedding_model,
                )
                case_records.append({
                    "id": question["id"], "question": question["pregunta"],
                    "expected": expected, "filter": result.get("applied_filter"),
                    "generation_status": "completed",
                    "generation": _generation_record(result),
                    "diagnosis": {"status": "pending inspection of actual supplied snippets and response"},
                })
            except GeneratorUnavailableError as exc:
                run_error = str(exc)
                case_records.append({
                    "id": question["id"], "question": question["pregunta"],
                    "expected": expected, "filter": None, "generation_status": "error",
                    "generation_error": run_error,
                    "diagnosis": {"status": "local generation invocation failed"},
                })
                for pending in questions[question_index + 1:]:
                    pending_expected = {
                        "answerable_in_corpus": pending["respondible"],
                        "expected_answer": pending["respuesta_referencia"],
                        "expected_source_article_ids": pending["fuentes_esperadas"],
                    }
                    case_records.append({
                        "id": pending["id"], "question": pending["pregunta"],
                        "expected": pending_expected, "filter": None, "generation_status": "not_run",
                        "skip_reason": "not invoked after a prior Ollama generation error",
                        "diagnosis": {"status": "not run; local generation invocation failed earlier"},
                    })
                break
        comparison = None
        if run_error is None:
            comparison_case = next(case for case in case_records if case["id"] == K_COMPARISON_QUESTION_ID)
            original_question = next(q["pregunta"] for q in questions if q["id"] == K_COMPARISON_QUESTION_ID)
            try:
                k1_result = answer_question(original_question, k=1, model=model,
                                             retriever=active_retriever, embedding_model=embedding_model)
                comparison = _run_comparison(comparison_case, _generation_record(k1_result))
            except GeneratorUnavailableError as exc:
                run_error = str(exc)
                comparison = {"question_id": K_COMPARISON_QUESTION_ID, "generation_error": run_error,
                              "manual_diagnosis": {"status": "not run; local generation invocation failed"}}
        after = active_retriever.integrity_snapshot()
        report = {
            "version": 1,
            "evaluation_questions_sha256": hashlib.sha256(question_bytes).hexdigest(),
            "fixed_question_count": len(questions),
            "baseline": {"k": 3, "jurisdiction_policy": "automatic conservative routing via answer_question",
                         "retrieval_protocol": "one routed generation call per fixed question; reuse existing bge-m3 index"},
            "routing_protocol": "answer_question; automatic jurisdiction routing",
            "runtime": runtime,
            "embedding_model": embedding_model,
            "fixed_cases": case_records,
            "k_comparison": comparison,
            "index_integrity": {"before_generation": before, "after_generation": after,
                                "unchanged": before == after},
            "overall_generation_error": run_error,
            "manual_review": {"status": "pending", "student_independently_verified": False},
        }

    review = None
    if report.get("overall_generation_error"):
        report["manual_review"] = {
            "status": "not applied; one or more model calls failed",
            "student_independently_verified": False,
            "note": "Inspect the recorded invocation error; do not infer a generation result.",
        }
    elif review_path.is_file():
        try:
            review = validate_manual_review(json.loads(review_path.read_text(encoding="utf-8")), report)
        except ValueError as exc:
            if existing_report_path is not None:
                raise
            report["manual_review"] = {
                "status": "stale review not applied",
                "source": display_path(review_path),
                "student_independently_verified": False,
                "note": f"Model output differs from the response hashes inspected previously: {exc}",
            }
        else:
            apply_manual_review(report, review, review_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"Generación evaluada: {report_path}; casos={len(report['fixed_cases'])}; "
          f"k=3; modelo={model}; revisión={'complete' if review else 'pending'}; "
          f"índice intacto={report.get('index_integrity', {}).get('unchanged', 'reporte previo')}")
    return report


def _answer_for_markdown(case: dict[str, Any]) -> str:
    status = case.get("generation_status", "completed" if "generation" in case else "error")
    if status == "error" or "generation_error" in case:
        return f"ERROR: {case.get('generation_error', 'model invocation failed')}"
    if status == "not_run":
        return f"NOT RUN: {case.get('skip_reason', 'model invocation was not attempted')}"
    generation = case["generation"]
    return generation["answer"].replace("|", "\\|").replace("\n", "<br>")


def _supplied_sources(generation: dict[str, Any]) -> str:
    sources = []
    for item in generation.get("source_map", []):
        page = f", pp. {item['pagina_inicio']}–{item['pagina_fin']}" if "pagina_inicio" in item else ""
        sources.append(f"{item['label']} `{item['chunk_id']}` ({item['source']}, {item['jurisdiccion']}, Ley {item['ley']} art. {item['articulo']}{page})")
    return "; ".join(sources) or "sin fragmentos"


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Evaluación de generación con enrutamiento automático", "",
             "Ejecución actual vía `answer_question()` (detector, filtro jurisdiccional y generación). Se escribe en un reporte nuevo y no reemplaza el baseline histórico TP2-RAG-06. No es una métrica de exactitud general. La temperatura 0 no garantiza veracidad ni repetibilidad. Las citas se validan sólo en formato/rango; apoyo semántico requiere inspección del texto realmente enviado.", "",
             "## Runtime verificado", ""]
    runtime = report.get("runtime", {})
    if runtime:
        lines.append(f"Ollama server `{runtime.get('ollama_server_version')}`; cliente Python `{runtime.get('ollama_python_client_version')}`; modelo `{runtime.get('model_tag')}`; digest `{runtime.get('model_digest')}`; detalles `{json.dumps(runtime.get('model_details', {}), ensure_ascii=False)}`; embeddings `{report.get('embedding_model', DEFAULT_EMBEDDING_MODEL)}` (índice existente).")
    else:
        lines.append("No se conservó metadata de runtime (reporte previo incompleto).")
    lines.extend(["", "## Cinco preguntas fijas: contexto y respuesta observados", "",
                  "Los campos esperado y observado se mantienen separados. El JSON contiene los fragmentos íntegros efectivamente enviados, el mapa `[n]` a fuente/artículo/página y las respuestas originales completas.", "",
                  "| ID / pregunta | Esperado (answer/source) | Ruta / filtro | IDs y fuentes realmente enviados | Respuesta generada | Referencias usadas / chequeo de formato | Diagnóstico de evidencia y generación |",
                  "|---|---|---|---|---|---|---|"])
    for case in report.get("fixed_cases", []):
        expected = case["expected"]
        expected_text = f"{expected['expected_answer']} / {expected['expected_source_article_ids']}"
        generation_status = case.get("generation_status", "completed" if "generation" in case else "error")
        if generation_status != "completed":
            sources, answer, citation = "—", _answer_for_markdown(case), "no invocado"
            route_text = "—"
            diagnosis = case.get("diagnosis", {}).get("status", "pending")
        else:
            generation = case["generation"]
            sources = _supplied_sources(generation)
            answer = _answer_for_markdown(case)
            route_text = (f"{generation.get('routing_status')} / {generation.get('jurisdiction_source')} / "
                          f"{generation.get('applied_filter')}")
            cited = generation.get("references_used") or []
            check = generation.get("citation_check")
            citation = (f"{[x['label'] for x in cited]}; valid={check['citations_valid']}, missing={check['citations_missing']}, invalid={check['citations_invalid']}"
                        if check else "no invocado por aclaración de ruta")
            diag = case.get("diagnosis", {})
            diagnosis = diag.get("observations", diag.get("status", "pending manual diagnosis"))
            if diag.get("failure_categories"):
                diagnosis += f"; stage={diag['failure_categories']}"
            if diag.get("evidence_coverage"):
                diagnosis = f"coverage={diag['evidence_coverage']}; {diagnosis}"
            if diag.get("answer_supported_by_context"):
                diagnosis += f"; supported={diag['answer_supported_by_context']}"
        lines.append(f"| {case['id']} — {case['question']} | {expected_text} | {route_text} | {sources} | {answer} | {citation} | {diagnosis} |")
    comparison = report.get("k_comparison")
    lines.extend(["", "## Comparación controlada k=1 vs k=3", ""])
    if comparison and "k1" in comparison and "k3" in comparison:
        lines.append(f"Pregunta `{comparison['question_id']}`: mismo modelo `{comparison['model']}`, temperatura {comparison['temperature']}, mismo prompt (SHA-256 `{comparison['prompt_template_sha256']}`).")
        for name in ("k1", "k3"):
            run = comparison[name]
            lines.append(f"- **k={run['k']}**; contexto: {_supplied_sources(run)}; respuesta: {run['answer']!r}; referencias: {[x['label'] for x in run['references_used']]}; cita-formato-válido={run['citation_check']['citations_valid']}.")
        diagnosis = comparison.get("manual_diagnosis", {})
        lines.append(f"- Observación: {diagnosis.get('observations', diagnosis.get('status', 'pending manual diagnosis'))}")
    else:
        lines.append(f"No completada: {comparison.get('generation_error', 'no hay ambas salidas k=1/k=3')}" if comparison else "No completada.")
    integrity = report.get("index_integrity", {})
    lines.extend(["", "## Trazabilidad, límites y revisión", "",
                  f"Snapshot de colección/IDs/manifest antes y después de generación: `{integrity.get('unchanged', 'not measured')}`. `context_sent` en el JSON es el bloque exacto entregado como `{{contexto}}`; para TXT no se inventan páginas PDF.",
                  "La verificación automática sólo detecta ausencia, formato y números de referencia fuera del mapa recuperado; no demuestra que una cita respalde la afirmación. No se aplicó reparación silenciosa de citas ni sustitución del modelo.",
                  f"Revisión: `{report.get('manual_review', {}).get('status', 'pending')}`. {report.get('manual_review', {}).get('note', 'Las observaciones diagnósticas deben completarse tras leer los fragmentos y las respuestas reales.')}",
                  "", "La instrucción de abstención no garantiza conducta fiable. Las salidas de las dos preguntas ausentes y los casos con cobertura incompleta deben leerse junto al contexto íntegro, no como evidencia legal verificada.",
                  "Los casos de este reporte pasan por `answer_question()`; las respuestas históricas sin enrutamiento siguen en `reporte_generacion.json` y no se mezclan aquí.", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=QUESTIONS_PATH)
    parser.add_argument("--index-dir", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--model", default=DEFAULT_GENERATION_MODEL)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--markdown", type=Path, default=MARKDOWN_PATH)
    parser.add_argument("--review", type=Path, default=REVIEW_PATH)
    parser.add_argument("--usar-reporte-existente", type=Path, default=None,
                        help="aplicar diagnóstico manual sin volver a invocar el modelo")
    args = parser.parse_args()
    try:
        evaluate(questions_path=args.questions, index_dir=args.index_dir, chunks_path=args.chunks,
                 model=args.model, embedding_model=args.embedding_model, report_path=args.report,
                 markdown_path=args.markdown, review_path=args.review,
                 existing_report_path=args.usar_reporte_existente)
    except Exception as exc:
        print(f"Error al evaluar generación: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
