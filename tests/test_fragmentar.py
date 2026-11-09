import hashlib
import json
from pathlib import Path

import pytest

from scripts.fragmentar import build_chunks, indexable_text, normalize_visual_wraps
from scripts.preprocesar import run

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def chunk_corpus(tmp_path_factory):
    out = tmp_path_factory.mktemp("chunks")
    run(ROOT / "datos", out)
    chunks, report = build_chunks(out, out / "chunks.jsonl")
    articles = {j: [json.loads(line) for line in (out / f"{j}_articulos.jsonl").read_text().splitlines()]
                for j in ("nacional", "pba", "santa_fe")}
    return chunks, report, articles, out


def test_source151_restored_with_stable_distinct_records():
    original = Path("datos/ley_pba.txt").read_bytes()
    assert hashlib.sha256(original).hexdigest() == "3c11d299e4830bc12281e514b15f87fca81e148b9470f1f250da8e5d958fae31"
    text = original.decode("utf-8")
    assert text.count("ARTÍCULO 151.-") == 2
    assert "ARTÍCULO 151.- (*) Comuníquese al Poder Ejecutivo." in text


def test_visual_wrap_normalization_preserves_paragraphs_and_lists():
    raw = "Una frase cortada\npor el layout.\n\na) inciso uno\ncontinúa.\n2) segundo"
    assert normalize_visual_wraps(raw) == "Una frase cortada por el layout.\n\na) inciso uno continúa.\n2) segundo"


def test_repeal_annotation_gets_nonempty_explicit_index_description(chunk_corpus):
    chunks, _, articles, _ = chunk_corpus
    art19 = next(r for r in articles["nacional"] if r["articulo"] == "19")
    source_note = art19["notas"][0]["texto"]
    expected = f"Artículo 19 — nota de derogación en la fuente: {source_note}"
    assert indexable_text(art19) == expected
    found = [c for c in chunks if c["source_article_id"] == art19["id"]]
    assert len(found) == 1
    assert found[0]["texto"] == expected
    assert found[0]["vista"] == "nota_explicita_derogacion"
    assert "Artículo 19. -" not in found[0]["texto"]


def test_chunks_are_traceable_and_never_mix_articles(chunk_corpus):
    chunks, report, articles, _ = chunk_corpus
    ids = [c["id"] for c in chunks]
    assert len(ids) == len(set(ids))
    article_by_id = {r["id"]: r for records in articles.values() for r in records}
    assert all(c["source_article_id"] in article_by_id for c in chunks)
    assert all(c["texto"] in indexable_text(article_by_id[c["source_article_id"]]) for c in chunks)
    # start_index permite comprobar que el splitter no pierde caracteres sustantivos.
    by_article = {}
    for c in chunks:
        by_article.setdefault(c["source_article_id"], []).append(c)
    for article_id, article_chunks in by_article.items():
        view = indexable_text(article_by_id[article_id])
        covered = [False] * len(view)
        for c in article_chunks:
            start = c["inicio_vista"]
            assert view[start:start + len(c["texto"])] == c["texto"]
            covered[start:start + len(c["texto"])] = [True] * len(c["texto"])
        assert all(char.isspace() or covered[i] for i, char in enumerate(view))
    for c in chunks:
        a = article_by_id[c["source_article_id"]]
        for key in ("jurisdiccion", "ley", "articulo", "source", "libro", "titulo", "capitulo", "pagina_inicio", "pagina_fin"):
            assert c[key] == a.get(key)
        assert c["id"].startswith(c["source_article_id"] + "__chunk_")
        assert c["pagina_inicio"] == a["pagina_inicio"] and c["pagina_fin"] == a["pagina_fin"]
    assert report["total_chunks"] == len(chunks)
    assert report["registros_sin_vista"] == []
    assert [report["jurisdicciones"][j]["chunks"] for j in ("nacional", "pba", "santa_fe")] == [289, 175, 364]
    assert report["chunk_size_caracteres"] == 1000 and report["chunk_overlap_caracteres"] == 150


def test_index_view_preserves_amendments_not_observed_pba_history(chunk_corpus):
    chunks, _, articles, _ = chunk_corpus
    sf285 = next(r for r in articles["santa_fe"] if r["articulo"] == "285")
    assert sf285["notas"][0]["tipo"] == "texto_modificatorio"
    assert normalize_visual_wraps(sf285["notas"][0]["texto"]) in indexable_text(sf285)
    pba13 = next(r for r in articles["pba"] if r["articulo"] == "13")
    observed = next(n["texto"] for n in pba13["notas"] if "observada" in n["texto"])
    assert "cien (100)" in observed
    assert "cien (100)" not in indexable_text(pba13)
    assert "noventa y dos (92)" in indexable_text(pba13)
    pba13_chunks = [c["texto"] for c in chunks if c["source_article_id"] == pba13["id"]]
    assert all("cien (100)" not in text for text in pba13_chunks)


def test_chunking_deterministic_and_parameters_valid(chunk_corpus, tmp_path):
    _, _, _, source_dir = chunk_corpus
    first = (source_dir / "chunks.jsonl").read_bytes()
    first_report = (source_dir / "reporte_fragmentacion.json").read_bytes()
    build_chunks(source_dir, tmp_path / "chunks.jsonl")
    assert first == (tmp_path / "chunks.jsonl").read_bytes()
    assert first_report == (tmp_path / "reporte_fragmentacion.json").read_bytes()
    with pytest.raises(ValueError):
        build_chunks(source_dir, tmp_path / "bad.jsonl", chunk_size=10, chunk_overlap=10)


def test_pba_articles_13_and_151_chunk_ids_are_distinct(chunk_corpus):
    chunks, _, _, _ = chunk_corpus
    pba151 = [c for c in chunks if c["source_article_id"].startswith("pba_5109_art_151")]
    assert {c["source_article_id"] for c in pba151} == {"pba_5109_art_151", "pba_5109_art_151__2"}
    assert all(c["jurisdiccion"] == "pba" for c in pba151)
