"""Crea chunks de recuperación sin alterar los registros completos del corpus."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import statistics

from langchain_text_splitters import RecursiveCharacterTextSplitter

ROOT = Path(__file__).resolve().parent.parent
JURISDICTIONS = ("nacional", "pba", "santa_fe")
REPEAL = re.compile(r"^\(Artículo derogado\b[^)]*\)$", re.I)
LIST_ITEM = re.compile(r"^(?:(?:[a-záéíóúñ]|\d+|[ivxlcdm]+)[.)]|[-•])\s", re.I)


def indexable_text(record: dict) -> str:
    """Vista de búsqueda: line-wrap PDF reparado, texto legal sin paráfrasis."""
    principal = record.get("texto_principal", "").strip()
    if principal and len(principal) > len(record.get("articulo", "")) + 24:
        return normalize_visual_wraps(principal)

    repeal_notes = [n["texto"] for n in record.get("notas", [])
                    if n.get("tipo") == "nota_editorial" and REPEAL.fullmatch(n["texto"].strip())]
    if repeal_notes:
        # Explicita que es una descripción de índice derivada de una nota fuente,
        # sin afirmar vigencia ni ampliar su contenido.
        return f"Artículo {record['articulo']} — nota de derogación en la fuente: {repeal_notes[0]}"
    return normalize_visual_wraps(principal)


def normalize_visual_wraps(text: str) -> str:
    """Une wraps visuales; deja párrafos y líneas de lista reconocibles intactos."""
    output: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            if output and output[-1] != "":
                output.append("")
            continue
        if not output or output[-1] == "" or LIST_ITEM.match(line):
            output.append(line)
        else:
            output[-1] += " " + line
    return "\n".join(output).strip()


def build_chunks(input_dir: Path, output_path: Path, *, chunk_size: int = 1000,
                 chunk_overlap: int = 150) -> tuple[list[dict], dict]:
    if chunk_size <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("Se requiere chunk_size > 0 y 0 <= chunk_overlap < chunk_size")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap,
        length_function=len, add_start_index=True,
    )
    chunks: list[dict] = []
    skipped = []
    for jurisdiction in JURISDICTIONS:
        path = input_dir / f"{jurisdiction}_articulos.jsonl"
        with path.open(encoding="utf-8") as stream:
            for line_no, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                article = json.loads(line)
                view = indexable_text(article)
                if not view:
                    skipped.append({"source_article_id": article["id"], "motivo": "vista indexable vacía"})
                    continue
                for number, doc in enumerate(splitter.create_documents([view]), 1):
                    metadata = {
                        "source_article_id": article["id"],
                        "jurisdiccion": article["jurisdiccion"],
                        "ley": article["ley"],
                        "articulo": article["articulo"],
                        "source": article["source"],
                        "libro": article.get("libro"),
                        "titulo": article.get("titulo"),
                        "capitulo": article.get("capitulo"),
                        "pagina_inicio": article.get("pagina_inicio"),
                        "pagina_fin": article.get("pagina_fin"),
                        "chunk_numero": number,
                        "inicio_vista": doc.metadata["start_index"],
                        "vista": ("nota_explicita_derogacion" if view.startswith(f"Artículo {article['articulo']} — nota de derogación en la fuente:")
                                  else "texto_principal_normalizado" if view != article.get("texto_principal", "").strip()
                                  else "texto_principal"),
                    }
                    chunks.append({"id": f"{article['id']}__chunk_{number:04d}",
                                   "texto": doc.page_content, **metadata})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as stream:
        for chunk in chunks:
            stream.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    report = summarize(chunks, skipped, chunk_size, chunk_overlap)
    report_path = output_path.with_name("reporte_fragmentacion.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for jurisdiction, stats in report["jurisdicciones"].items():
        print(f"{jurisdiction}: {stats['chunks']} chunks; longitudes min/mediana/max "
              f"{stats['min']}/{stats['mediana']}/{stats['max']}")
    print(f"total: {report['total_chunks']} chunks; omitidos {len(skipped)}")
    return chunks, report


def summarize(chunks: list[dict], skipped: list[dict], chunk_size: int, chunk_overlap: int) -> dict:
    grouped: dict[str, list[int]] = defaultdict(list)
    for chunk in chunks:
        grouped[chunk["jurisdiccion"]].append(len(chunk["texto"]))
    jurisdictions = {}
    oversized = []
    for jurisdiction in JURISDICTIONS:
        lengths = grouped[jurisdiction]
        jurisdictions[jurisdiction] = {
            "chunks": len(lengths),
            "min": min(lengths) if lengths else 0,
            "mediana": statistics.median(lengths) if lengths else 0,
            "max": max(lengths) if lengths else 0,
        }
    for chunk in chunks:
        if len(chunk["texto"]) > chunk_size:
            oversized.append({"id": chunk["id"], "longitud": len(chunk["texto"])})
    return {"chunk_size_caracteres": chunk_size, "chunk_overlap_caracteres": chunk_overlap,
            "longitud": "caracteres Python del texto del chunk; splitter recursivo",
            "total_chunks": len(chunks), "jurisdicciones": jurisdictions,
            "chunks_mayores_que_chunk_size": oversized, "registros_sin_vista": skipped,
            "limitaciones": [
                "Los chunks heredan rango de páginas del artículo completo; no se asignan páginas internas sin mapeo validado.",
                "Las longitudes no implican calidad de recuperación; embeddings y evaluación están fuera de alcance.",
                "Las descripciones de artículos derogados sólo repiten la nota explícita de la fuente y no afirman vigencia.",
            ]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=ROOT / "datos/procesados")
    parser.add_argument("--salida", type=Path, default=ROOT / "datos/procesados/chunks.jsonl")
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--chunk-overlap", type=int, default=150)
    args = parser.parse_args()
    build_chunks(args.entrada, args.salida, chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
