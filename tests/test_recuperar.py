import hashlib
import json
from pathlib import Path

import pytest

from scripts.indexar import COLLECTION, DEFAULT_MODEL, MANIFEST, IndexConfigurationError, make_signature
from scripts.recuperar import RetrievalIndexError, SemanticRetriever, build_result, retrieve
from scripts.evaluar_recuperacion import (
    article_metrics, aggregate_metrics, build_evidence_context, evaluate,
    make_distance_svg, validate_manual_review,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "evalucacion/preguntas.json"
FIXTURE_SHA256 = "5b0c0f545671a2a34ea68de096c10c6fb22914bb7b3410011c19df9f40d3de4e"


def chunk(chunk_id="a__chunk_0001", *, jurisdiction="nacional", pages=None):
    row = {"id": chunk_id, "texto": "Texto íntegro del fragmento.\nSegunda línea completa.",
           "source_article_id": "a", "jurisdiccion": jurisdiction, "ley": "19945",
           "articulo": "12", "source": "ley.txt", "chunk_numero": 1,
           "titulo": "Título I", "capitulo": "Capítulo II"}
    if pages:
        row.update(pagina_inicio=pages[0], pagina_fin=pages[1])
    return row


def prepared_index(tmp_path, rows=None):
    rows = rows or [chunk()]
    chunks_path = tmp_path / "chunks.jsonl"
    chunks_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    import scripts.indexar as indexar
    _, digest = indexar.read_chunks(chunks_path)
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    signature = make_signature(digest, DEFAULT_MODEL)
    (index_dir / MANIFEST).write_text(json.dumps(signature), encoding="utf-8")
    return chunks_path, index_dir, signature


class FakeEmbeddings:
    def __init__(self):
        self.queries = []

    def embed_query(self, question):
        self.queries.append(question)
        return [0.25, 0.75]


class FakeCollection:
    def __init__(self, owner):
        self.owner = owner
        self.calls = []

    def query(self, **kwargs):
        self.calls.append(kwargs)
        selected = self.owner.rows
        if "where" in kwargs:
            selected = [r for r in selected if r["jurisdiccion"] == kwargs["where"]["jurisdiccion"]]
        selected = selected[:kwargs["n_results"]]
        return {"ids": [[r["id"] for r in selected]],
                "documents": [[r["texto"] for r in selected]],
                "metadatas": [[{k: v for k, v in r.items() if k not in {"id", "texto"} and v is not None}
                               for r in selected]],
                "distances": [[r["distance"] for r in selected]]}


class FakeStore:
    rows = []
    last = None
    fail_collection = False

    def __init__(self, *, collection_name, embedding_function, persist_directory,
                 create_collection_if_not_exists):
        assert collection_name == COLLECTION
        assert create_collection_if_not_exists is False
        self._collection = FakeCollection(self)
        FakeStore.last = self
        if self.fail_collection:
            raise RuntimeError("missing collection")

    def get(self, *, include):
        return {"ids": [r["id"] for r in self.rows],
                "metadatas": [{k: v for k, v in r.items() if k not in {"id", "texto"} and v is not None}
                              for r in self.rows]}


@pytest.fixture
def fake_index(tmp_path):
    rows = [
        {**chunk("n1", jurisdiction="nacional"), "distance": 0.11},
        {**chunk("p1", jurisdiction="pba"), "distance": 0.22},
        {**chunk("s1", jurisdiction="santa_fe", pages=(1, 4)), "distance": 0.33},
    ]
    chunks_path, index_dir, signature = prepared_index(tmp_path, rows)
    FakeStore.rows = rows
    FakeStore.fail_collection = False
    embeddings = FakeEmbeddings()
    retriever = SemanticRetriever(index_dir=index_dir, chunks_path=chunks_path,
                                  embeddings=embeddings, vector_store_class=FakeStore)
    return retriever, embeddings, FakeStore.last, index_dir, chunks_path, signature


def test_retrieval_returns_exact_order_full_text_ids_distances_and_provenance(fake_index):
    retriever, embeddings, store, *_ = fake_index
    results = retriever.retrieve("pregunta original", k=3)
    assert [r["rank"] for r in results] == [1, 2, 3]
    assert [r["chunk_id"] for r in results] == ["n1", "p1", "s1"]
    assert [r["distance"] for r in results] == [0.11, 0.22, 0.33]
    assert all(r["text"] == chunk(r["chunk_id"], jurisdiction=r["jurisdiccion"],
                                   pages=(1, 4) if r["chunk_id"] == "s1" else None)["texto"] for r in results)
    assert results[0]["source_article_id"] == "a"
    assert results[0]["source"] == "ley.txt" and results[0]["chunk_numero"] == 1
    assert "pagina_inicio" not in results[0] and "pagina_fin" not in results[0]
    assert (results[2]["pagina_inicio"], results[2]["pagina_fin"]) == (1, 4)
    assert results[0]["titulo"] == "Título I" and results[0]["capitulo"] == "Capítulo II"
    assert "not probability" in results[0]["distance_kind"]
    assert embeddings.queries == ["pregunta original"]
    assert store._collection.calls[-1]["n_results"] == 3
    assert "where" not in store._collection.calls[-1]


def test_public_function_reuses_an_open_retriever_and_validates_before_open(fake_index):
    retriever, embeddings, _, *_ = fake_index
    result = retrieve("consulta", k=1, retriever=retriever)
    assert result[0]["chunk_id"] == "n1"
    assert embeddings.queries == ["consulta"]
    with pytest.raises(ValueError, match="question"):
        retrieve("  ")


def test_jurisdiction_is_applied_in_chroma_query_and_no_filter_is_implicit(fake_index):
    retriever, _, store, *_ = fake_index
    filtered = retriever.retrieve("filtro", k=2, jurisdiccion="pba")
    assert [r["jurisdiccion"] for r in filtered] == ["pba"]
    assert store._collection.calls[-1]["where"] == {"jurisdiccion": "pba"}
    retriever.retrieve("sin filtro", k=2)
    assert "where" not in store._collection.calls[-1]


def test_invalid_inputs_and_empty_results(fake_index):
    retriever, embeddings, store, *_ = fake_index
    for question in ("", " \n ", None):
        with pytest.raises(ValueError, match="question"):
            retriever.retrieve(question)
    for k in (0, -1, True, 1.5):
        with pytest.raises(ValueError, match="k"):
            retriever.retrieve("q", k=k)
    with pytest.raises(ValueError, match="jurisdiccion"):
        retriever.retrieve("q", jurisdiccion="otra")
    assert embeddings.queries == []
    store.rows = []
    assert retriever.retrieve("sin vecinos") == []


def test_missing_incompatible_and_empty_index_are_rejected_without_mutation(tmp_path):
    chunks_path, index_dir, signature = prepared_index(tmp_path)
    missing = tmp_path / "missing"
    with pytest.raises(RetrievalIndexError, match="Falta el índice"):
        SemanticRetriever(index_dir=missing, chunks_path=chunks_path,
                          embeddings=FakeEmbeddings(), vector_store_class=FakeStore)
    assert not missing.exists()
    empty_directory = tmp_path / "directory-without-manifest"
    empty_directory.mkdir()
    with pytest.raises(RetrievalIndexError, match="Falta el índice"):
        SemanticRetriever(index_dir=empty_directory, chunks_path=chunks_path,
                          embeddings=FakeEmbeddings(), vector_store_class=FakeStore)
    assert list(empty_directory.iterdir()) == []
    manifest_path = index_dir / MANIFEST
    before = manifest_path.read_bytes()
    original_chunks = chunks_path.read_bytes()
    bad = {**signature, "embedding_model": "wrong-model"}
    manifest_path.write_text(json.dumps(bad))
    after_bad = manifest_path.read_bytes()
    FakeStore.last = None
    with pytest.raises(IndexConfigurationError, match="Firma incompatible"):
        SemanticRetriever(index_dir=index_dir, chunks_path=chunks_path,
                          embeddings=FakeEmbeddings(), vector_store_class=FakeStore)
    assert manifest_path.read_bytes() == after_bad and FakeStore.last is None
    manifest_path.write_bytes(before)
    chunks_path.write_text(original_chunks.decode().replace("Texto íntegro", "Texto alterado"), encoding="utf-8")
    FakeStore.last = None
    with pytest.raises(IndexConfigurationError, match="Firma incompatible"):
        SemanticRetriever(index_dir=index_dir, chunks_path=chunks_path,
                          embeddings=FakeEmbeddings(), vector_store_class=FakeStore)
    assert manifest_path.read_bytes() == before and FakeStore.last is None
    chunks_path.write_bytes(original_chunks)
    FakeStore.rows = []
    with pytest.raises(RetrievalIndexError, match="vacía"):
        SemanticRetriever(index_dir=index_dir, chunks_path=chunks_path,
                          embeddings=FakeEmbeddings(), vector_store_class=FakeStore)
    assert manifest_path.read_bytes() == before


def test_missing_chroma_collection_is_rejected_without_creating_one(tmp_path):
    chunks_path, index_dir, _ = prepared_index(tmp_path)
    FakeStore.fail_collection = True
    before = (index_dir / MANIFEST).read_bytes()
    with pytest.raises(RetrievalIndexError, match="No existe o no se puede leer"):
        SemanticRetriever(index_dir=index_dir, chunks_path=chunks_path,
                          embeddings=FakeEmbeddings(), vector_store_class=FakeStore)
    assert (index_dir / MANIFEST).read_bytes() == before
    FakeStore.fail_collection = False


def test_article_metrics_handle_miss_duplicate_chunks_and_negatives():
    results = [
        {"rank": 1, "source_article_id": "unrelated"},
        {"rank": 2, "source_article_id": "expected"},
        {"rank": 3, "source_article_id": "expected"},
    ]
    hit = article_metrics(results, ["expected"])
    assert (hit["hit_at_1"], hit["hit_at_3"], hit["hit_at_5"]) == (False, True, True)
    assert hit["reciprocal_rank_at_5"] == 0.5
    miss = article_metrics(results[:1], ["absent"])
    assert miss["first_expected_rank"] is None and miss["reciprocal_rank_at_5"] == 0
    aggregate = aggregate_metrics([{"unfiltered": {"article_metrics": hit}},
                                   {"unfiltered": {"article_metrics": miss}}], "unfiltered")
    assert aggregate["positive_question_denominator"] == 2
    assert aggregate["mrr_at_5"] == 0.25


def test_full_text_evidence_context_order_and_page_numbers():
    txt = build_result(1, "txt-1", {"source_article_id": "a", "jurisdiccion": "nacional",
                       "ley": "19945", "articulo": "12", "source": "ley.txt", "chunk_numero": 1},
                       "Exact text\nnot shortened.", 0.1)
    pdf = build_result(2, "pdf-2", {"source_article_id": "b", "jurisdiccion": "santa_fe",
                       "ley": "14478", "articulo": "4", "source": "ley.pdf", "chunk_numero": 2,
                       "pagina_inicio": 1, "pagina_fin": 4}, "PDF complete body.", 0.2)
    text = build_evidence_context([txt, pdf])
    assert text.index("[1]") < text.index("[2]")
    assert "chunk_id: txt-1" in text and "source_article_id: a" in text
    assert "Exact text\nnot shortened." in text
    assert "paginas_articulo" not in text.split("[2]")[0]
    assert "paginas_articulo: 1–4" in text
    assert text.index("PDF complete body.") > text.index("[2]")


def test_fixture_hash_and_manual_quote_verification():
    raw = FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FIXTURE_SHA256
    questions = json.loads(raw)["preguntas"]
    positives = [q for q in questions if q["respondible"]]
    results = [{"chunk_id": "actual", "text": "The source says the exception is optional."}]
    mapping = {(q["id"], mode): results for q in positives
               for mode in ("unfiltered", "jurisdiction_filtered")}
    mapping.update({(q["id"], "unfiltered"): [] for q in questions if not q["respondible"]})
    review = {"fixed_positive": {q["id"]: {
                 mode: {"reviewed_top3_chunk_ids": ["actual"],
                        "top3_passage_coverage": "partial", "evidence": [
                     {"chunk_id": "actual", "quote": "the exception is optional"}]}
                 for mode in ("unfiltered", "jurisdiction_filtered")} for q in positives},
             "negative": {q["id"]: {"can_substantiate_requested_fact": False, "explanation": "not results data",
                                    "reviewed_top3_chunk_ids": []}
                          for q in questions if not q["respondible"]},
             "k_comparison": {"question_id": positives[0]["id"],
                               "k1_coverage": "partial", "k3_coverage": "partial"}}
    validate_manual_review(review, questions, mapping)
    review["fixed_positive"][positives[0]["id"]]["unfiltered"]["evidence"][0]["quote"] = "invented quotation"
    with pytest.raises(ValueError, match="no coteja"):
        validate_manual_review(review, questions, mapping)


def test_svg_uses_native_values_and_labels():
    results = [{"rank": 1, "chunk_id": "exact-id-1", "distance": 0.123456},
               {"rank": 2, "chunk_id": "exact-id-2", "distance": 0.654321}]
    svg = make_distance_svg(results, "Pregunta & prueba")
    assert "Pregunta &amp; prueba" in svg
    assert "exact-id-1" in svg and "exact-id-2" in svg
    assert "0.123456" in svg and "0.654321" in svg
    assert "smaller is closer; not a probability" in svg


class FakeEvaluationRetriever:
    def __init__(self):
        self.calls = []
        self.rank = [{"rank": 1, "id": "a__chunk_0001", "chunk_id": "a__chunk_0001",
                      "source_article_id": "nacional_19945_art_12", "jurisdiccion": "nacional",
                      "ley": "19945", "articulo": "12", "source": "ley_nacional.txt",
                      "chunk_numero": 1, "text": "Expected evidence full text.", "distance": 0.12}]

    def integrity_snapshot(self):
        return {"count": 828, "ids_sha256": "unchanged", "manifest_sha256": "same", "ids_match_chunks": True}

    def retrieve(self, question, k=5, jurisdiccion=None):
        self.calls.append((question, k, jurisdiccion))
        return [dict(self.rank[0], rank=rank) for rank in range(1, min(k, 1) + 1)]


def test_evaluator_queries_each_filter_once_and_keeps_paraphrase_separate(tmp_path):
    fixture_copy = tmp_path / "questions.json"
    fixture_copy.write_bytes(FIXTURE.read_bytes())
    digest_before = hashlib.sha256(fixture_copy.read_bytes()).hexdigest()
    fake = FakeEvaluationRetriever()
    report_path = tmp_path / "report.json"
    markdown_path = tmp_path / "report.md"
    plot_path = tmp_path / "plot.svg"
    report = evaluate(fixture_copy, report_path=report_path, markdown_path=markdown_path,
                      plot_path=plot_path, review_path=tmp_path / "missing-review.json", retriever=fake)
    assert len(fake.calls) == 9  # 3 x (unfiltered + filtered), 2 negatives, 1 paraphrase.
    assert all(k == 5 for _, k, _ in fake.calls)
    assert report["question_count"] == 5 and len(report["positive_questions"]) == 3
    assert len(report["negative_questions"]) == 2
    assert report["aggregate_positive_metrics"]["unfiltered"]["positive_question_denominator"] == 3
    assert report["k_comparison"]["k1"]["results"] == report["k_comparison"]["k3"]["results"][:1]
    assert report["numbered_evidence_context"]["source_chunk_ids"] == [r["chunk_id"] for r in report["k_comparison"]["k3"]["results"]]
    assert "Expected evidence full text." in report["numbered_evidence_context"]["text"]
    assert report["paraphrase_trial"]["question"] not in [q["question"] for q in report["positive_questions"]]
    assert len(report["paraphrase_trial"]["results"]) == 1
    assert report["distance_plot"]["distances"] == [0.12]
    for row in report["positive_questions"]:
        assert row["unfiltered"]["results"][0]["text"] == "Expected evidence full text."
        assert row["jurisdiction_filtered"]["results"][0]["chunk_id"] == "a__chunk_0001"
    assert len(report["negative_questions"][0]["results"]) == 1
    assert hashlib.sha256(fixture_copy.read_bytes()).hexdigest() == digest_before
    assert report_path.exists() and markdown_path.exists() and plot_path.exists()
    assert report["index_integrity"]["unchanged"] is True
