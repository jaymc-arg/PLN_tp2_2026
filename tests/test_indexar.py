import json
from pathlib import Path

import pytest
from langchain_core.documents import Document

from indexar import (
    COLLECTION, DEFAULT_MODEL, IndexConfigurationError, chunk_metadata,
    make_signature, prepare_index_dir, read_chunks, run_index, to_documents,
)

ROOT = Path(__file__).resolve().parents[1]
CHUNKS = ROOT / "datos/procesados/chunks.jsonl"


def test_real_chunk_input_is_valid_unique_and_hashable():
    rows, digest = read_chunks(CHUNKS)
    assert len(rows) == 828
    assert len({row["id"] for row in rows}) == len(rows)
    assert len(digest) == 64
    docs, ids = to_documents(rows[:2])
    assert all(isinstance(doc, Document) for doc in docs)
    assert [doc.page_content for doc in docs] == [row["texto"] for row in rows[:2]]
    assert ids == [row["id"] for row in rows[:2]]


def test_metadata_required_fields_and_null_pages_are_omitted():
    rows, _ = read_chunks(CHUNKS)
    txt = next(row for row in rows if row["jurisdiccion"] == "pba")
    sf = next(row for row in rows if row["jurisdiccion"] == "santa_fe")
    txt_metadata = chunk_metadata(txt)
    sf_metadata = chunk_metadata(sf)
    required = {"source_article_id", "jurisdiccion", "ley", "articulo", "source", "chunk_numero"}
    assert required <= txt_metadata.keys() and required <= sf_metadata.keys()
    assert "pagina_inicio" not in txt_metadata and "pagina_fin" not in txt_metadata
    assert isinstance(sf_metadata["pagina_inicio"], int) and isinstance(sf_metadata["pagina_fin"], int)
    assert sf_metadata["pagina_inicio"] <= sf_metadata["pagina_fin"]
    assert "titulo" in sf_metadata and isinstance(sf_metadata["titulo"], str)


def test_metadata_rejects_non_scalar_values_and_incomplete_page_range():
    base = {"id": "x", "source_article_id": "a", "jurisdiccion": "nacional",
            "ley": "1", "articulo": "1", "source": "a.txt", "chunk_numero": 1}
    with pytest.raises(ValueError, match="no escalar"):
        chunk_metadata({**base, "titulo": ["not scalar"]})
    with pytest.raises(ValueError, match="Rango PDF incompleto"):
        chunk_metadata({**base, "pagina_inicio": 1})


def test_configuration_signature_detects_model_and_corpus_changes(tmp_path):
    first = make_signature("a" * 64, DEFAULT_MODEL)
    path = tmp_path / "index"
    prepare_index_dir(path, first, rebuild=False)
    assert json.loads((path / "index_manifest.json").read_text()) == first
    with pytest.raises(IndexConfigurationError, match="incompatible"):
        prepare_index_dir(path, make_signature("a" * 64, "other-model"), rebuild=False)
    with pytest.raises(IndexConfigurationError, match="incompatible"):
        prepare_index_dir(path, make_signature("b" * 64, DEFAULT_MODEL), rebuild=False)
    prepare_index_dir(path, make_signature("a" * 64, "other-model"), rebuild=True)
    assert json.loads((path / "index_manifest.json").read_text())["embedding_model"] == "other-model"


def test_rebuild_refuses_unmanaged_directory_and_protected_paths(tmp_path):
    unmanaged = tmp_path / "unmanaged"
    unmanaged.mkdir()
    (unmanaged / "valuable.txt").write_text("keep")
    with pytest.raises(IndexConfigurationError, match="manifest válido"):
        prepare_index_dir(unmanaged, make_signature("x", DEFAULT_MODEL), rebuild=True)
    assert (unmanaged / "valuable.txt").read_text() == "keep"
    with pytest.raises(ValueError, match="insegura"):
        prepare_index_dir(ROOT, make_signature("x", DEFAULT_MODEL), rebuild=True)


class FakeEmbeddings:
    def embed_query(self, text):
        return [0.1, 0.2, 0.3]


class FakeCollection:
    def __init__(self, owner):
        self.owner = owner

    def query(self, *, query_embeddings, n_results, include):
        selected = list(self.owner.records.items())[:n_results]
        return {
            "ids": [[key for key, _ in selected]],
            "metadatas": [[value["metadata"] for _, value in selected]],
            "documents": [[value["text"] for _, value in selected]],
        }


class FakeChroma:
    instances = {}

    def __init__(self, *, collection_name, embedding_function, persist_directory):
        self.key = (persist_directory, collection_name)
        self.records = self.instances.setdefault(self.key, {})
        self._collection = FakeCollection(self)

    def get(self, *, include):
        ids = list(self.records)
        result = {"ids": ids}
        if "metadatas" in include:
            result["metadatas"] = [self.records[key]["metadata"] for key in ids]
        return result

    def add_documents(self, documents, *, ids):
        for doc_id, doc in zip(ids, documents):
            self.records[doc_id] = {"text": doc.page_content, "metadata": doc.metadata}


def write_chunks(path):
    records = [
        {"id": "art-1__chunk_0001", "texto": "evidencia primera", "source_article_id": "art-1",
         "jurisdiccion": "nacional", "ley": "19945", "articulo": "1", "source": "ley.txt",
         "chunk_numero": 1, "pagina_inicio": None, "pagina_fin": None},
        {"id": "art-2__chunk_0001", "texto": "evidencia segunda", "source_article_id": "art-2",
         "jurisdiccion": "pba", "ley": "5109", "articulo": "2", "source": "ley.txt",
         "chunk_numero": 1, "pagina_inicio": None, "pagina_fin": None},
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in records))
    return records


def test_index_contract_idempotence_rebuild_and_smoke_metadata(tmp_path, capsys):
    chunks_path = tmp_path / "chunks.jsonl"
    expected = write_chunks(chunks_path)
    index_dir = tmp_path / "selected-index"
    embeddings = FakeEmbeddings()
    kwargs = dict(chunks_path=chunks_path, index_dir=index_dir, embeddings=embeddings,
                  vector_store_class=FakeChroma, smoke_question="test")
    first = run_index(**kwargs)
    second = run_index(**kwargs)
    assert first["indexed_count"] == second["indexed_count"] == 2
    assert first["expected_count"] == second["expected_count"] == 2
    assert first["dimensions"] == 3
    assert len(FakeChroma.instances[(str(index_dir), COLLECTION)]) == 2
    assert [row["id"] for row in first["ranked"]] == [row["id"] for row in second["ranked"]]
    assert first["ranked"][0]["source_article_id"] == expected[0]["source_article_id"]
    assert "no demuestra corrección" in capsys.readouterr().out

    write_chunks(chunks_path)
    chunks_path.write_bytes(chunks_path.read_bytes() + b"\n")
    with pytest.raises(IndexConfigurationError, match="incompatible"): 
        run_index(**kwargs)
    run_index(**kwargs, rebuild=True)
    assert len(FakeChroma.instances[(str(index_dir), COLLECTION)]) == 2


def test_evaluation_fixture_has_three_grounded_positives_and_two_absent_negatives():
    path = ROOT / "evalucacion/preguntas.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    questions = data["preguntas"]
    assert len(questions) == 5
    positives = [q for q in questions if q["respondible"]]
    negatives = [q for q in questions if not q["respondible"]]
    assert len(positives) == 3 and len(negatives) == 2
    assert {q["jurisdiccion"] for q in positives} == {"nacional", "pba", "santa_fe"}
    corpus_ids = set()
    for filename in ("nacional_articulos.jsonl", "pba_articulos.jsonl", "santa_fe_articulos.jsonl"):
        corpus_ids.update(json.loads(line)["id"] for line in (ROOT / "datos/procesados" / filename).read_text().splitlines())
    assert all(q["fuentes_esperadas"] and set(q["fuentes_esperadas"]) <= corpus_ids for q in positives)
    assert all(not q["fuentes_esperadas"] for q in negatives)
    assert len({q["id"] for q in questions}) == 5
