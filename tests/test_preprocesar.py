"""Protege la fidelidad del corpus: ninguna extracción debe perder texto legal."""

import hashlib
import json
from pathlib import Path
import re

import pytest

from importlib import import_module

preprocesar = import_module("scripts.00_preprocesar")
SOURCES = preprocesar.SOURCES
annotations = preprocesar.annotations
load_source = preprocesar.load_source
normalize = preprocesar.normalize
parse_lines = preprocesar.parse_lines
run = preprocesar.run

ROOT = Path(__file__).resolve().parents[1]
HASHES = {
    "ley_nacional.txt": "b7e7d75ad921d086c9cd87ffb3621f716784afc7c81d105ff04433f99d6c4b93",
    # Fuente al iniciar TP2-RAG-02: el usuario ya había retirado la segunda rúbrica 151.
    "ley_pba.txt": "3c11d299e4830bc12281e514b15f87fca81e148b9470f1f250da8e5d958fae31",
    "ley_sta_fe.pdf": "2d2447623105b707a286a57b8853385cd9f8fe6f70cd504b4881a2fb3c08f4bb",
}


def parse(text):
    """Crea una fuente sintética sin páginas para aislar reglas de segmentación."""
    return parse_lines([(line, None) for line in text.splitlines()], "test", "1", "fixture.txt")


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    """Procesa las fuentes reales una sola vez por módulo y expone sus auditorías."""
    out = tmp_path_factory.mktemp("procesados")
    report = run(ROOT / "datos", out)
    records = {
        j: [json.loads(line) for line in (out / f"{j}_articulos.jsonl").read_text().splitlines()]
        for j, _, _ in SOURCES
    }
    return records, report, out


def test_headings_references_subsections_and_duplicates():
    records, audit = parse("""Prefacio conservado.
CAPÍTULO I
PRUEBAS
ARTÍCULO 1°.- Texto y referencia al artículo 2.
a) Primera excepción.
b) Segunda excepción.
Remisión envuelta al
artículo 172.
Art. 2 bis.- (Texto según Ley 10) Otro texto.
Artículo 2 ter: Más texto.
ARTICULO 2 ter.- Duplicado real.
Artículo s/n (Artículo 2 Ley 23).- Sin número.
""")
    assert [r["articulo"] for r in records] == ["1", "2 bis", "2 ter", "2 ter", "s/n"]
    assert records[3]["id"].endswith("__2")
    assert "b) Segunda excepción." in records[0]["texto"]
    assert records[0]["capitulo"] == "CAPÍTULO I\nPRUEBAS"
    assert records[1]["notas"][0]["texto"] == "(Texto según Ley 10)"
    assert audit["cantidad_duplicados"] == 1
    assert audit["segmentos_fuera_articulos"][0]["texto"] == "Prefacio conservado."


@pytest.mark.parametrize("opening,closing", [('“', '”'), ('"', '"'), ('«', '»')])
def test_quoted_headings_do_not_create_records(opening, closing):
    records, _ = parse(f"""Artículo 1.- Principal.
{opening}ARTÍCULO 99.- Transcripción:
Artículo 2.- Interior de cita.
Fin de cita.{closing}
Artículo 2.- Principal siguiente.
""")
    assert [r["articulo"] for r in records] == ["1", "2"]
    assert "Interior de cita" in records[0]["texto"]
    assert "Interior de cita" not in records[0]["texto_principal"]


def test_unclosed_quote_is_preserved_and_reported():
    records, audit = parse('Artículo 1.- Texto.\n“ARTÍCULO 2.- Cita abierta\nArtículo 3.- Ambiguo')
    assert "Artículo 3.- Ambiguo" in records[0]["texto"]
    assert any("sin cierre" in w["motivo"] for w in audit["advertencias"])
    assert audit["conservacion_contenido_no_blanco"]


def test_notes_preserve_nested_parentheses_and_ambiguous_formatting():
    text = "Artículo 1.- Principal (con excepción).\n(Texto según Ley 2 (B.O. 3))\nb) INCISO DEROGADO POR LEY 4 Texto anterior.\n(*) Lo subrayado fue observado."
    notes, principal = annotations(text)
    assert len(notes) == 3
    assert "(con excepción)" in principal
    assert any(n["tipo"] == "pasaje_marcado_derogado" for n in notes)
    assert "no puede aislarse" in notes[-1]["advertencia"]
    for n in notes:
        assert text[n["inicio"]:n["fin"]] == n["texto"]


def test_cross_page_and_trailing_content():
    records, audit = parse_lines([
        ("ARTÍCULO 4.- Definiciones:", 1), ("a. Uno", 1),
        ("b. Dos", 2), ("ARTÍCULO 5.- Fin.", 2),
        ("DADA EN LA SALA DE SESIONES: firma", 2),
    ], "sf", "1", "test.pdf")
    assert records[0]["pagina_inicio"] == 1 and records[0]["pagina_fin"] == 2
    assert records[0]["texto"].endswith("b. Dos")
    assert "firma" not in records[-1]["texto"]
    assert "firma" in audit["segmentos_fuera_articulos"][-1]["texto"]


@pytest.mark.parametrize("jurisdiction,law,filename", SOURCES)
def test_real_schema_order_fidelity_and_original_hash(corpus, jurisdiction, law, filename):
    data, report, _ = corpus
    records = data[jurisdiction]
    required = {"id", "jurisdiccion", "ley", "articulo", "titulo", "capitulo", "texto", "notas", "referencias_externas", "pagina_inicio", "pagina_fin", "source"}
    assert len({r["id"] for r in records}) == len(records)
    assert all(required <= r.keys() and r["texto"].strip() for r in records)
    assert [r["inicio"] for r in records] == sorted(r["inicio"] for r in records)
    assert all(r["ley"] == law and r["source"] == filename for r in records)
    path = ROOT / "datos" / filename
    assert hashlib.sha256(path.read_bytes()).hexdigest() == HASHES[filename]
    assert report["fuentes"][filename]["sha256"] == HASHES[filename]
    lines, extraction = load_source(path)
    stream = "\n".join(line for line, _ in lines)
    segments = records + report["fuentes"][filename]["segmentos_fuera_articulos"]
    segments.sort(key=lambda s: s["inicio"])
    compact = lambda s: re.sub(r"\s+", "", s)
    assert compact("".join(s["texto"] for s in segments)) == compact(stream)
    for segment in segments:
        assert stream[segment["inicio"]:segment["fin"]].strip() == segment["texto"]
    if filename.endswith(".pdf"):
        assert extraction["paginas_leidas"] == 70
        assert len(extraction["layout_eliminado"]) == 140
        assert all(1 <= r["pagina_inicio"] <= r["pagina_fin"] <= 70 for r in records)
        assert all("Texto original de la Ley" not in r["texto"] for r in records)
    else:
        assert all(r["pagina_inicio"] is None and r["pagina_fin"] is None for r in records)


def article(corpus, jurisdiction, number):
    """Recupera un artículo del corpus de prueba por número y jurisdicción."""
    return next(r for r in corpus[0][jurisdiction] if r["articulo"] == number)


def test_real_national_12_full_source_and_exceptions(corpus):
    source = normalize((ROOT / "datos/ley_nacional.txt").read_text())
    expected = source.split("Artículo 12. -", 1)[1].split("Artículo 13.-", 1)[0].strip()
    record = article(corpus, "nacional", "12")
    assert record["texto"] == "Artículo 12. - " + expected
    for marker in ["a)", "b)", "c)", "d)", "quinientos (500)", "diez (10)", "carácter optativo"]:
        assert marker in record["texto_principal"]


def test_real_pba_2_3_and_13(corpus):
    source = normalize((ROOT / "datos/ley_pba.txt").read_text())
    r2 = article(corpus, "pba", "2")
    assert r2["texto"] == source[source.index("ARTÍCULO 2°.-"):source.index("ARTÍCULO 3:")].strip()
    assert "Ley 11.700" in r2["referencias_externas"]
    r3 = article(corpus, "pba", "3")
    assert any("INCISO DEROGADO POR LEY 11.833" in n["texto"] for n in r3["notas"])
    assert "INCISO DEROGADO" not in r3["texto_principal"]
    r13 = article(corpus, "pba", "13")
    assert r13["texto"] == source[source.index("ARTÍCULO 13.-"):source.index("ARTÍCULO 13 bis.-")].strip()
    for wording in ["noventa y dos (92)", "cuarenta y seis (46)"]:
        assert wording in r13["texto_principal"]
    for wording in ["cien (100)", "cincuenta (50)"]:
        assert wording in r13["texto"] and wording in r13["notas"][0]["texto"]
        assert wording not in r13["texto_principal"]
    assert r13["notas"][0]["tipo"] == "nota_editorial"
    assert "“ARTÍCULO 26.-" in r13["notas"][0]["texto"]
    assert all(n["tipo"] != "texto_modificatorio" for n in r13["notas"])
    assert r13["notas"][0]["advertencia"]
    assert len([r for r in corpus[0]["pba"] if r["articulo"] == "13"]) == 1


def test_real_sf_4_definitions_and_duplicates(corpus):
    r4 = article(corpus, "santa_fe", "4")
    assert (r4["pagina_inicio"], r4["pagina_fin"]) == (1, 4)
    for marker in ["a. agrupación política", "b. autoridad de mesa", "r. escrutinio provisorio", "ah. sección electoral", "al. voto recurrido"]:
        assert marker in r4["texto"]
    lines, _ = load_source(ROOT / "datos/ley_sta_fe.pdf")
    stream = "\n".join(l for l, _ in lines)
    assert r4["texto"] == stream[stream.index("ARTÍCULO 4.-"):stream.index("CAPÍTULO II")].strip()
    assert len([r for r in corpus[0]["santa_fe"] if r["articulo"] == "172"]) == 1
    assert "artículo 172." in article(corpus, "santa_fe", "173")["texto"]
    duplicates = [r for r in corpus[0]["pba"] if r["articulo"] == "151"]
    assert [r["id"] for r in duplicates] == ["pba_5109_art_151", "pba_5109_art_151__2"]
    assert [len(corpus[0][j]) for j, _, _ in SOURCES] == [208, 155, 296]


@pytest.mark.parametrize("number,pages", [
    ("285", (67, 67)), ("286", (67, 67)), ("287", (67, 67)),
    ("288", (67, 68)), ("289", (68, 68)), ("290", (68, 68)),
])
def test_real_sf_amendment_wording_is_substantive(corpus, number, pages):
    record = article(corpus, "santa_fe", number)
    assert record["id"] == f"santa_fe_14478_art_{number}"
    assert record["source"] == "ley_sta_fe.pdf"
    assert (record["pagina_inicio"], record["pagina_fin"]) == pages
    assert record["texto_principal"] == record["texto"]
    assert len(record["notas"]) == 1
    note = record["notas"][0]
    assert note["tipo"] == "texto_modificatorio"
    assert note["texto"].startswith('"ARTÍCULO ') and note["texto"].endswith('"')
    assert record["texto"][note["inicio"]:note["fin"]] == note["texto"]
    assert note["texto"] in record["texto_principal"]
    records = corpus[0]["santa_fe"]
    assert [r["articulo"] for r in records[-12:]] == list(map(str, range(285, 297)))
    assert all(len([r for r in records if r["articulo"] == n]) == 1 for n in ["2", "7", "8", "9", "12"])


def test_restored_pba_151_occurrences_match_source(corpus):
    records = [r for r in corpus[0]["pba"] if r["articulo"] == "151"]
    assert [r["id"] for r in records] == ["pba_5109_art_151", "pba_5109_art_151__2"]
    assert records[0]["texto"].startswith("ARTÍCULO 151.- (Texto según Ley N° 13.082)")
    assert records[1]["texto"] == "ARTÍCULO 151.- (*) Comuníquese al Poder Ejecutivo.\n\n(*) Para el presente artículo se respetó la numeración según el texto ordenado por decreto 997/1993 anterior a la modificación introducida por Ley 13082."
    assert records[1]["notas"][0]["texto"].startswith("(*) Para el presente artículo")


def test_unique_structural_headings_are_metadata(corpus):
    chapter = article(corpus, "santa_fe", "40")
    assert chapter["capitulo"].startswith("CAPÍTULO ÚNICO")
    book_iv = next(r for r in corpus[0]["santa_fe"] if r["articulo"] == "239")
    assert book_iv["libro"].startswith("LIBRO IV")
    assert book_iv["titulo"] == "TÍTULO ÚNICO"
    assert book_iv["capitulo"].startswith("CAPÍTULO I")


def test_real_pba_26_is_distinct_and_unchanged(corpus):
    records = [r for r in corpus[0]["pba"] if r["articulo"] == "26"]
    assert len(records) == 1
    record = records[0]
    assert record["id"] == "pba_5109_art_26"
    assert record["texto_principal"] == record["texto"]
    assert record["notas"] == []
    assert hashlib.sha256(record["texto"].encode()).hexdigest() == "d52ac64fd1a0b05619548a91f4b7a0b01827d8e5a0adb1b5dc1724c6a5b3f767"
    source = normalize((ROOT / "datos/ley_pba.txt").read_text())
    assert record["texto"] == source[source.index("\nARTÍCULO 26.-"):source.index("\nARTÍCULO 27.-")].strip()


def test_amendment_classification_requires_verified_enclosing_source():
    lines = [('ARTÍCULO 285.- Modifícase otra ley:', 67),
             ('"ARTÍCULO 2.- Reemplazo completo."', 67)]
    for jurisdiction, law, source in [("pba", "5109", "ley_pba.txt"),
                                      ("santa_fe", "14478", "otra_fuente.pdf")]:
        records, _ = parse_lines(lines, jurisdiction, law, source)
        assert records[0]["notas"][0]["tipo"] == "transcripcion_citada"
        assert "Reemplazo completo" not in records[0]["texto_principal"]


def test_deterministic_all_outputs(corpus, tmp_path):
    """Evita que el mismo corpus produzca IDs o auditorías diferentes entre corridas."""
    run(ROOT / "datos", tmp_path)
    for first in corpus[2].iterdir():
        assert first.read_bytes() == (tmp_path / first.name).read_bytes()


def test_invalid_utf8_and_missing_input_fail(tmp_path):
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"\xff")
    with pytest.raises(UnicodeDecodeError):
        load_source(bad)
    with pytest.raises(FileNotFoundError):
        load_source(tmp_path / "missing.txt")
