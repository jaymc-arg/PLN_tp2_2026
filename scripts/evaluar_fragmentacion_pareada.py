"""Ensayo local pareado 1000/150 vs 600/80: reutiliza índices y answer_question.

--ejecutar realiza consultas reales; sin ese flag solo revisa/renderiza trazas guardadas.
Las revisiones semánticas son entradas explícitas, no se infieren de Hit@k.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
from importlib import import_module
from importlib.metadata import version
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

indexar = import_module("scripts.02_indexar")
fragmentar = import_module("scripts.01_fragmentar")
recuperar = import_module("scripts.03_recuperar")
generar = import_module("scripts.04_generar")
lab = import_module("scripts.experimentos_fragmentacion")
generation_evaluation = import_module("scripts.evaluar_generacion")
ROOT = indexar.ROOT
FIXTURE = ROOT / "evalucacion/preguntas.json"
FIXTURE_HASH = "f25203f27d0dc12bdc430a47cc58911e1c023807d9179a7507e93cc200399275"
OUTPUT = ROOT / "evalucacion/experimentos_fragmentacion"
ARMS = ("1000_150", "600_80")
LABELS = {"supported", "partially_supported", "unsupported", "abstained_correctly",
          "abstained_incorrectly", "needs_review"}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def validate_fixture(path=FIXTURE):
    if digest(path) != FIXTURE_HASH:
        raise ValueError("El fixture no coincide con el SHA-256 acordado")
    questions = json.loads(path.read_text())["preguntas"]
    if len(questions) != 38 or len({q["id"] for q in questions}) != 38:
        raise ValueError("Se requieren 38 IDs únicos")
    if sum(q["respondible"] for q in questions) != 32:
        raise ValueError("Se requieren 32 positivas y seis negativas")
    articles = {}
    for j in fragmentar.JURISDICTIONS:
        for line in (lab.INPUT_DIR / f"{j}_articulos.jsonl").read_text().splitlines():
            article = json.loads(line)
            articles[article["id"]] = article
    comparisons = 0
    for q in questions:
        expected = q["fuentes_esperadas"]
        if not q["respondible"]:
            if expected:
                raise ValueError(f"Negativa con fuente esperada: {q['id']}")
            continue
        if not expected or any(i not in articles for i in expected):
            raise ValueError(f"Fuente esperada ausente: {q['id']}")
        jurisdictions = q.get("jurisdicciones") or [q["jurisdiccion"]]
        if set(jurisdictions) != {articles[i]["jurisdiccion"] for i in expected}:
            raise ValueError(f"Jurisdicciones inconsistentes: {q['id']}")
        if len(jurisdictions) > 1:
            comparisons += 1
            if len(jurisdictions) != 2 or len(expected) != 2:
                raise ValueError("La comparación debe cubrir dos fuentes y jurisdicciones")
    if comparisons != 2:
        raise ValueError("Se requieren dos comparaciones")
    return questions


def article_metrics(groups, expected):
    """K por jurisdicción. Hit comparativo exige TODOS; RR=1/rango completo."""
    first = {article: min((r["rank"] for g in groups for r in g["results"]
                          if r["source_article_id"] == article), default=None) for article in expected}
    complete_rank = max(first.values()) if first and all(v is not None for v in first.values()) else None
    result = {"first_rank_per_article": first, "first_complete_rank": complete_rank,
              "reciprocal_rank_at_5": 1 / complete_rank if complete_rank else 0.0}
    for k in (1, 3, 5):
        found = {r["source_article_id"] for g in groups for r in g["results"][:k]}
        matches = len(found.intersection(expected))
        result[f"hit_at_{k}"] = bool(expected) and matches == len(expected)
        result[f"expected_article_recall_at_{k}"] = matches / len(expected) if expected else None
    return result


def verify_or_resume(chunks_path, index_dir, *, allow_resume=False):
    """Inspecciona antes de indexar; solo completa IDs ausentes de un índice compatible."""
    chunks, chunks_hash = indexar.read_chunks(chunks_path)
    manifest = index_dir / indexar.MANIFEST
    expected = {r["id"]: (r["texto"], indexar.chunk_metadata(r)) for r in chunks}
    initial = 0
    if index_dir.exists() and any(index_dir.iterdir()):
        if not manifest.is_file() or json.loads(manifest.read_text()) != indexar.make_signature(chunks_hash, indexar.DEFAULT_MODEL):
            raise ValueError(f"Manifest incompatible; no se reconstruye: {index_dir}")
        store = recuperar.Chroma(collection_name=indexar.COLLECTION, persist_directory=str(index_dir),
                                 create_collection_if_not_exists=False)
        actual = store.get(include=["documents", "metadatas"])
        initial = len(actual["ids"])
        if initial != len(set(actual["ids"])):
            raise ValueError("IDs duplicados")
        for i, text, metadata in zip(actual["ids"], actual["documents"], actual["metadatas"]):
            if i not in expected or expected[i] != (text, metadata):
                raise ValueError(f"Texto/metadatos incompatibles: {i}; no se reescribe")
    if initial != len(expected):
        if not allow_resume:
            raise ValueError("El baseline falta o está incompleto; no se modifica")
        indexar.run_index(chunks_path, index_dir, model=indexar.DEFAULT_MODEL, rebuild=False)
    active = recuperar.SemanticRetriever(index_dir=index_dir, chunks_path=chunks_path, model=indexar.DEFAULT_MODEL)
    final = active.store.get(include=["documents", "metadatas"])
    stored = {i: (t, m) for i, t, m in zip(final["ids"], final["documents"], final["metadatas"])}
    if stored != expected or len(final["ids"]) != len(set(final["ids"])):
        raise ValueError("Verificación final de textos/metadatos fallida; no se borran artefactos")
    return active, {"all_stored_text_metadata_match_chunks": True, "initial_count": initial, "final_count": active.count,
                    "missing_ids_completed": active.count - initial, "chunks_sha256": chunks_hash,
                    "manifest": json.loads(manifest.read_text()),
                    "dimensions": len(active.store.get(include=["embeddings"], limit=1)["embeddings"][0]),
                    "chroma_configuration": active.store._collection.configuration}


def generation_from_ranking(question, groups, *, chat_model=None):
    """Reusa top-5 REAL de esta pregunta; nunca consulta otra vez ni reconstruye evidencia."""
    def retrieve(text, k, jurisdiccion):
        if text != question["pregunta"] or k not in (1, 3, 5):
            raise ValueError("Petición ajena al ranking guardado")
        for group in groups:
            if group["jurisdiccion"] == jurisdiccion:
                return deepcopy(group["results"][:k])
        raise ValueError(f"Jurisdicción fuera del fixture: {jurisdiccion}")
    scopes = question.get("jurisdicciones")
    kwargs = ({"jurisdicciones": scopes} if scopes else
              {"jurisdiccion": question["jurisdiccion"]} if question["jurisdiccion"] else {"sin_filtro": True})
    return generar.answer_question(question["pregunta"], k=3, model=generar.DEFAULT_GENERATION_MODEL,
                                    embedding_model=indexar.DEFAULT_MODEL,
                                    retriever=SimpleNamespace(retrieve=retrieve), chat_model=chat_model, **kwargs)


def protected_hashes():
    paths = [*lab.INPUT_DIR.glob("*.json*"), *ROOT.joinpath("evalucacion").glob("*")]
    return {str(p.relative_to(ROOT)): digest(p) for p in paths if p.is_file()}


def execute(output=OUTPUT):
    questions = validate_fixture()
    if indexar.DEFAULT_MODEL != "qwen3-embedding:0.6b":
        raise ValueError("Este ensayo requiere Qwen en ambos brazos")
    config = lab.configuration(600, 80)
    challenger = Path(config["chunks_path"])
    if not challenger.is_file():
        raise ValueError("No se encontró el experimento 600/80 preexistente; no se crea otro")
    inputs = protected_hashes()
    runtime = {"embedding": generation_evaluation.inspect_local_model(indexar.DEFAULT_MODEL),
               "generation": generation_evaluation.inspect_local_model(generar.DEFAULT_GENERATION_MODEL),
               "prompt_sha256": generar.PROMPT_TEMPLATE_SHA256,
               "versions": indexar.software_versions()}
    reports, retrievers = {}, {}
    for arm, chunks_path, index_dir in (
        (ARMS[0], indexar.DEFAULT_INPUT, indexar.DEFAULT_INDEX),
        (ARMS[1], challenger, Path(config["index_dir"]))):
        fragment_report = json.loads(chunks_path.with_name("reporte_fragmentacion.json").read_text())
        size, overlap = map(int, arm.split("_"))
        if (fragment_report["chunk_size_caracteres"], fragment_report["chunk_overlap_caracteres"]) != (size, overlap):
            raise ValueError("El reporte de fragmentación no corresponde al brazo")
        with TemporaryDirectory() as temp:
            rebuilt = Path(temp) / "chunks.jsonl"
            fragmentar.build_chunks(lab.INPUT_DIR, rebuilt, chunk_size=size, chunk_overlap=overlap)
            if rebuilt.read_bytes() != chunks_path.read_bytes():
                raise ValueError("Los chunks no corresponden a los artículos/código actuales; no se reindexan")
        retriever, verification = verify_or_resume(chunks_path, index_dir, allow_resume=arm == ARMS[1])
        verification["temporary_reconstruction_matches_exact_bytes"] = True
        verification["splitter_code_sha256"] = digest(fragmentar.__file__)
        verification["splitter_version"] = version("langchain-text-splitters")
        retrievers[arm] = retriever
        path = output / f"qwen_{arm}.json"
        header = {"fixture_sha256": FIXTURE_HASH, "runtime": runtime,
                  "protected_inputs_sha256": inputs, "arm": arm,
                  "index_path": str(index_dir.relative_to(ROOT)), "chunks_path": str(chunks_path.relative_to(ROOT)),
                  "fragmentation": fragment_report, "index_verification": verification}
        if path.exists():
            report = json.loads(path.read_text())
            for key in ("fixture_sha256", "runtime", "protected_inputs_sha256", "arm", "index_path", "chunks_path", "fragmentation"):
                if report[key] != header[key]:
                    raise ValueError(f"Checkpoint incompatible: {key}; no se sobrescribe")
        else:
            report = {**header, "index_before": retriever.integrity_snapshot(), "cases": []}
        reports[arm] = report
        save(path, report)
    if reports[ARMS[0]]["index_verification"]["chroma_configuration"] != reports[ARMS[1]]["index_verification"]["chroma_configuration"]:
        raise ValueError("Las configuraciones de distancia/Chroma difieren")
    if reports[ARMS[0]]["index_verification"]["dimensions"] != reports[ARMS[1]]["index_verification"]["dimensions"]:
        raise ValueError("Dimensiones incompatibles")
    for q in questions:
        for arm in ARMS:
            report, retriever = reports[arm], retrievers[arm]
            if any(c["id"] == q["id"] for c in report["cases"]):
                continue  # reanudación: no repite respuestas ya ejecutadas, tampoco errores
            scopes = q.get("jurisdicciones") or [q["jurisdiccion"]]
            case = {"id": q["id"], "fixture": q,
                    "automatic_route_diagnostic_only": generar.detect_jurisdiction(q["pregunta"]),
                    "scope_policy": "explicit fixture; K per jurisdiction; unscoped negatives unfiltered",
                    "generation_reuses_actual_saved_top5": True}
            try:
                groups = [{"jurisdiccion": scope, "results": retriever.retrieve(q["pregunta"], k=5, jurisdiccion=scope)} for scope in scopes]
                case.update({"retrieval": groups, "article_metrics": article_metrics(groups, q["fuentes_esperadas"])})
                case["generation"] = generation_from_ranking(q, groups)
                if not case["generation"]["model_invoked"]:
                    raise ValueError("No se invocó modelo: no contar aclaración como respuesta/abstención")
            except Exception as exc:
                case["runtime_error"] = f"{type(exc).__name__}: {exc}"
            case["review"] = {"answer_label": "needs_review", "reviewer": "pending coding-agent inspection"}
            report["cases"].append(case)
            report["index_after"] = retriever.integrity_snapshot()
            if report["index_before"] != report["index_after"]:
                raise RuntimeError("El índice cambió durante el ensayo")
            save(output / f"qwen_{arm}.json", report)
            print(arm, len(report["cases"]), q["id"], case.get("runtime_error", case.get("generation", {}).get("answer_status")), flush=True)
    after = protected_hashes()
    if inputs != after:
        raise RuntimeError("Se modificaron entradas o resultados históricos durante el ensayo")
    for arm, report in reports.items():
        report["protected_inputs_unchanged"] = True
        save(output / f"qwen_{arm}.json", report)


def apply_review(report, reviews):
    if set(reviews) != {c["id"] for c in report["cases"]}:
        raise ValueError("Revisión incompleta o ajena")
    for case in report["cases"]:
        item = reviews[case["id"]]
        if item.get("answer_label") not in LABELS or item.get("passage_coverage_k3") not in {"full", "partial", "none"}:
            raise ValueError(f"Etiquetas de revisión inválidas: {case['id']}")
        if item.get("factual_correctness") not in {"full", "partial", "incorrect", "uncertain", "not_applicable"}:
            raise ValueError("Falta evaluación factual separada")
        if item.get("citation_support") not in {"full", "partial", "none", "missing", "uncertain", "not_applicable"}:
            raise ValueError("Falta evaluación semántica de citas")
        if item["answer_label"] == "supported" and (item["factual_correctness"] != "full" or item["citation_support"] != "full"):
            raise ValueError("supported requiere hechos completos y citas que los apoyen")
        if case["fixture"]["respondible"] and item["answer_label"] == "abstained_correctly":
            raise ValueError("Una positiva no es abstención correcta del corpus")
        if not case["fixture"]["respondible"]:
            if item["answer_label"] in {"supported", "abstained_incorrectly"}:
                raise ValueError("Etiqueta positiva aplicada a una negativa")
            if type(item.get("unsupported_factual_answer")) is not bool:
                raise ValueError("Las negativas requieren separar falta de abstención de invención factual")
            if item["answer_label"] == "abstained_correctly" and item["unsupported_factual_answer"]:
                raise ValueError("Una abstención correcta no contiene afirmaciones factuales no apoyadas")
        generation = case.get("generation", {})
        if item.get("original_response_sha256") != hashlib.sha256((generation.get("original_response") or "").encode()).hexdigest():
            raise ValueError("La revisión pertenece a otra respuesta")
        records = {r["chunk_id"]: r for r in generation.get("retrieval_records", [])}
        for evidence in item.get("evidence", []):
            if (evidence["chunk_id"] not in records or not evidence["quote"]
                    or evidence["quote"] not in records[evidence["chunk_id"]]["text"]):
                raise ValueError(f"La cita no está en el contexto enviado: {case['id']}")
        if not item.get("justification") or not item.get("reviewer"):
            raise ValueError("Falta justificación/atribución")
        if item["answer_label"] == "supported" and len(case["fixture"].get("fuentes_esperadas", [])) == 2:
            evidenced = {records[e["chunk_id"]]["source_article_id"] for e in item.get("evidence", [])}
            if not set(case["fixture"]["fuentes_esperadas"]).issubset(evidenced):
                raise ValueError("Comparación supported sin citas de ambos artículos esperados")
        case["review"] = item


def aggregate(cases):
    positives = [c for c in cases if c["fixture"]["respondible"]]
    negatives = [c for c in cases if not c["fixture"]["respondible"]]
    def rate(items, predicate):
        return {"count": sum(bool(predicate(c)) for c in items), "denominator": len(items),
                "rate": sum(bool(predicate(c)) for c in items) / len(items) if items else None}
    recall = {}
    comparisons = [c for c in positives if len(c["fixture"].get("fuentes_esperadas", [])) == 2]
    for k in (1, 3, 5):
        numerator = sum(sum(rank is not None and rank <= k for rank in c.get("article_metrics", {}).get("first_rank_per_article", {}).values()) for c in positives)
        denominator = sum(len(c["fixture"].get("fuentes_esperadas", [])) for c in positives)
        recall[f"expected_article_recall_at_{k}"] = {"count": numerator, "denominator": denominator,
                                                    "rate": numerator / denominator if denominator else None}
        recall[f"both_articles_at_{k}"] = rate(comparisons, lambda c: c.get("article_metrics", {}).get(f"hit_at_{k}", False))
    return {**recall, **{f"hit_at_{k}": rate(positives, lambda c: c.get("article_metrics", {}).get(f"hit_at_{k}", False)) for k in (1, 3, 5)},
            "mrr_at_5": {"sum": sum(c.get("article_metrics", {}).get("reciprocal_rank_at_5", 0) for c in positives),
                         "denominator": len(positives),
                         "rate": sum(c.get("article_metrics", {}).get("reciprocal_rank_at_5", 0) for c in positives) / len(positives) if positives else None},
            "full_evidence_at_3": rate(positives, lambda c: c["review"].get("passage_coverage_k3") == "full"),
            "supported_answer": rate(positives, lambda c: c["review"]["answer_label"] == "supported"),
            "factually_complete_answer": rate(positives, lambda c: c["review"].get("factual_correctness") == "full"),
            "citations_semantically_supported": rate(positives, lambda c: c["review"].get("citation_support") == "full"),
            "correct_abstention": rate(negatives, lambda c: c["review"]["answer_label"] == "abstained_correctly"),
            "unsupported_negative_answer": rate(negatives, lambda c: c["review"].get("unsupported_factual_answer", False)),
            "generic_negative_nonanswer": rate(negatives, lambda c: c["review"]["answer_label"] == "partially_supported" and not c["review"].get("unsupported_factual_answer", False)),
            "invented_requested_negative_fact": rate(negatives, lambda c: c["review"].get("invented_requested_fact", False)),
            "exact_model_abstention": rate(negatives, lambda c: (c.get("generation", {}).get("original_response") or "").strip() == generar.ABSTENTION),
            "execution_errors": sum("runtime_error" in c for c in cases),
            "needs_review_labels": sum(c["review"]["answer_label"] == "needs_review" for c in cases),
            "uninspected_cases": sum(c["review"].get("reviewer", "").startswith("pending") for c in cases)}


def paired_outcomes(reports):
    result = {}
    for metric in ("hit_at_3", "passage_k3", "supported_answer", "correct_negative_abstention", "negative_no_unsupported_facts"):
        buckets = {"wins_600_80": [], "regressions_600_80": [], "ties": [], "needs_review": []}
        for a, b in zip(reports[ARMS[0]]["cases"], reports[ARMS[1]]["cases"]):
            positive = a["fixture"]["respondible"]
            if (metric in {"correct_negative_abstention", "negative_no_unsupported_facts"}) == positive:
                continue
            def score(c):
                if metric == "hit_at_3":
                    return int(c.get("article_metrics", {}).get("hit_at_3", False))
                if metric == "passage_k3":
                    return {"none": 0, "partial": 1, "full": 2}.get(c["review"].get("passage_coverage_k3"))
                if c["review"]["answer_label"] == "needs_review":
                    return None
                if metric == "negative_no_unsupported_facts":
                    return int(not c["review"].get("unsupported_factual_answer", False))
                return int(c["review"]["answer_label"] == ("supported" if positive else "abstained_correctly"))
            old, new = score(a), score(b)
            key = ("needs_review" if old is None or new is None else "wins_600_80" if new > old
                   else "regressions_600_80" if new < old else "ties")
            buckets[key].append(a["id"])
        result[metric] = buckets
    return result


def render(output=OUTPUT, review_path=None):
    reports = {a: json.loads((output / f"qwen_{a}.json").read_text()) for a in ARMS}
    review = json.loads(review_path.read_text()) if review_path else None
    for arm, report in reports.items():
        if report["fixture_sha256"] != FIXTURE_HASH:
            raise ValueError("Fixture ajeno")
        if review:
            if review["fixture_sha256"] != FIXTURE_HASH:
                raise ValueError("Review de otro fixture")
            apply_review(report, review[arm])
            report["review_metadata"] = {"path": str(review_path), "sha256": digest(review_path),
                                         "reviewer": review.get("reviewer"), "rubric": review.get("rubric"),
                                         "source_validation": review.get("source_validation")}
        report["execution_summary"] = {
            "case_count": len(report["cases"]),
            "retrieval_scope_queries": sum(len(c.get("retrieval", [])) for c in report["cases"]),
            "model_invocations": sum(c.get("generation", {}).get("model_invoked", False) for c in report["cases"]),
            "runtime_errors": sum("runtime_error" in c for c in report["cases"]),
        }
        report["aggregate"] = aggregate(report["cases"])
        scope = lambda c: c['fixture']['jurisdiccion'] or ('comparativa' if c['fixture'].get('jurisdicciones') else 'sin_filtro')
        report["by_jurisdiction"] = {j: aggregate([c for c in report['cases'] if scope(c) == j]) for j in sorted({scope(c) for c in report['cases']})}
        report["by_type"] = {t: aggregate([c for c in report['cases'] if c['fixture'].get('tipo', 'original') == t]) for t in sorted({c['fixture'].get('tipo', 'original') for c in report['cases']})}
        report["by_jurisdiction_and_type"] = {}
        for c in report["cases"]:
            q = c["fixture"]
            key = f"{q['jurisdiccion'] or ('comparativa' if q.get('jurisdicciones') else 'sin_filtro')}/{q.get('tipo', 'original')}"
            subset = [x for x in report["cases"] if (x["fixture"]["jurisdiccion"] or ('comparativa' if x["fixture"].get('jurisdicciones') else 'sin_filtro')) == key.split('/')[0] and x["fixture"].get('tipo', 'original') == key.split('/')[1]]
            report["by_jurisdiction_and_type"][key] = aggregate(subset)
        save(output / f"qwen_{arm}.json", report)
    lines = ["# Comparación Qwen 600/80 vs 1000/150", "",
             f"Fixture: `{FIXTURE_HASH}`; 38 casos, 32 positivos (dos comparaciones), seis negativos.",
             "Mismo Qwen, Granite, prompt y temperatura 0. Filtros explícitos del fixture; K por jurisdicción. Top-5 real una vez por scope; generación reutiliza sus primeros tres mediante answer_question(). No se cambió Gradio ni los defaults.",
             "Hit exige TODOS los artículos esperados; MRR usa 1/rango mínimo que reúne todos (máximo de primeros rangos locales). Recall cuenta artículos únicos por pregunta (34 pares pregunta/artículo esperados, no 34 artículos distintos del corpus). Negativos fuera de los denominadores de hit, evidencia y respuesta positiva.",
             "La revisión es inspección del agente de código, no validación jurídica independiente. Sin review completa, las tasas semánticas NO deben interpretarse como resultados definitivos.", "",
             "| Métrica | 1000/150 (cantidad/denominador; tasa) | 600/80 (cantidad/denominador; tasa) |", "|---|---|---|"]
    for key in ("hit_at_1", "hit_at_3", "hit_at_5", "mrr_at_5", "expected_article_recall_at_1", "expected_article_recall_at_3", "expected_article_recall_at_5", "both_articles_at_1", "both_articles_at_3", "both_articles_at_5", "full_evidence_at_3", "supported_answer", "factually_complete_answer", "citations_semantically_supported", "correct_abstention", "unsupported_negative_answer", "generic_negative_nonanswer", "invented_requested_negative_fact", "exact_model_abstention"):
        cells = []
        for arm in ARMS:
            m = reports[arm]["aggregate"][key]
            cells.append(f"{m.get('count', m.get('sum'))}/{m['denominator']}; {m['rate']:.4f}")
        lines.append(f"| {key} | {' | '.join(cells)} |")
    lines.extend(["", "Supported es estricto: hechos requeridos completos, sin extensión material ajena y referencias semánticamente pertinentes. Corrección factual y apoyo de citas se evalúan por separado del chequeo de formato.",
                  f"Casos sin inspección: {reports[ARMS[0]]['aggregate']['uninspected_cases']} / {reports[ARMS[1]]['aggregate']['uninspected_cases']}; etiquetas de incertidumbre needs_review: {reports[ARMS[0]]['aggregate']['needs_review_labels']} / {reports[ARMS[1]]['aggregate']['needs_review_labels']}. Una incertidumbre no se presenta como fallo confirmado.",
                  "En negativas, la falta de abstención no implica necesariamente una ubicación/resultado inventado: se separan afirmaciones factuales no apoyadas (incluidas extensiones ajenas) y el hecho individual solicitado inventado."])
    for grouping, title in (("by_jurisdiction", "Jurisdicción"), ("by_type", "Tipo de caso")):
        lines.extend(["", f"## Resultados por {title.lower()}", "",
                      f"| {title} | Hit@3 base→600 | Pasaje completo@3 base→600 | Supported base→600 | Abstención correcta base→600 |",
                      "|---|---|---|---|---|"])
        def cell(metric):
            return f"{metric['count']}/{metric['denominator']}" + (f" ({metric['rate']:.3f})" if metric['rate'] is not None else " (n/a)")
        for key in reports[ARMS[0]][grouping]:
            cells = [" → ".join(cell(reports[a][grouping][key][m]) for a in ARMS) for m in ("hit_at_3", "full_evidence_at_3", "supported_answer", "correct_abstention")]
            lines.append(f"| {key} | {' | '.join(cells)} |")
    lines.extend(["", "## Índices y entorno", ""])
    for arm, report in reports.items():
        lines.extend([f"### {arm}", f"Índice: `{report['index_path']}`; chunks: `{report['chunks_path']}`.",
                      "```json", json.dumps({k: report[k] for k in ("runtime", "fragmentation", "index_verification", "index_before", "index_after", "protected_inputs_unchanged", "execution_summary") if k in report}, ensure_ascii=False, indent=2), "```", ""])
    lines.extend(["## Pares por pregunta", "", "| ID | Hit@1/3/5 y RR: base → 600 | Pasaje K3: base → 600 | Hechos: base → 600 | Citas semánticas: base → 600 | Respuesta: base → 600 | Diagnóstico |", "|---|---|---|---|---|---|---|"])
    for a, b in zip(reports[ARMS[0]]["cases"], reports[ARMS[1]]["cases"]):
        if a["id"] != b["id"]:
            raise ValueError("Casos no pareados")
        metrics = lambda c: ('/'.join(str(int(c.get('article_metrics', {}).get(f'hit_at_{k}', False))) for k in (1, 3, 5)) + f"; {c.get('article_metrics', {}).get('reciprocal_rank_at_5', 0):.3f}") if c['fixture']['respondible'] else 'n/a (negativa)'
        lines.append(f"| {a['id']} | {metrics(a)} → {metrics(b)} | {a['review'].get('passage_coverage_k3', 'pending')} → {b['review'].get('passage_coverage_k3', 'pending')} | {a['review'].get('factual_correctness', 'pending')} → {b['review'].get('factual_correctness', 'pending')} | {a['review'].get('citation_support', 'pending')} → {b['review'].get('citation_support', 'pending')} | {a['review']['answer_label']} → {b['review']['answer_label']} | {b['review'].get('paired_observation', 'Pendiente')} |")
    outcomes = paired_outcomes(reports)
    save(output / "resultados_pareados.json", outcomes)
    lines.extend(["", "## Victorias, regresiones y empates de 600/80", "",
                  "Pasaje compara none < partial < full. Respuesta supported usa un indicador binario estricto; etiquetas intermedias siguen detalladas por caso.", "",
                  "| Indicador | Victorias | Regresiones | Empates | Pendientes |", "|---|---:|---:|---:|---:|"])
    for metric, buckets in outcomes.items():
        lines.append(f"| {metric} | {len(buckets['wins_600_80'])} | {len(buckets['regressions_600_80'])} | {len(buckets['ties'])} | {len(buckets['needs_review'])} |")
    lines.extend(["", "Listas de IDs en `resultados_pareados.json`. Agregados por jurisdicción, tipo y ambos en los JSON de cada brazo."])
    if review:
        lines.extend(["", "## Diagnóstico y conclusión", "", *review.get("conclusions", []), "", "## Ejecución y verificación", "", *review.get("verification", [])])
    lines.extend(["", "Los JSON conservan textos íntegros, fuentes/páginas, distancias, recall por artículo, diagnósticos y denominadores por jurisdicción/tipo. Las distancias no son confianza ni probabilidades.", ""])
    (output / "comparacion_qwen_600_80_vs_1000_150.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ejecutar", action="store_true")
    parser.add_argument("--salida", type=Path, default=OUTPUT)
    parser.add_argument("--review", type=Path)
    args = parser.parse_args()
    if args.ejecutar:
        execute(args.salida)
    render(args.salida, args.review)


if __name__ == "__main__":
    main()
