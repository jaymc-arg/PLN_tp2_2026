"""Recuperación semántica de solo lectura desde el índice persistente Chroma."""
from __future__ import annotations

import argparse
import json
import hashlib
import sys
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

if __package__ in {None, ""}:  # supports `python scripts/03_recuperar.py` and `python -m scripts.03_recuperar`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from importlib import import_module

detect_jurisdiction = import_module("scripts.03_bis_detectar_jurisdiccion").detect_jurisdiction
_indexar = import_module("scripts.02_indexar")
COLLECTION = _indexar.COLLECTION
DEFAULT_INDEX = _indexar.DEFAULT_INDEX
DEFAULT_MODEL = _indexar.DEFAULT_MODEL
DEFAULT_INPUT = _indexar.DEFAULT_INPUT
MANIFEST = _indexar.MANIFEST
IndexConfigurationError = _indexar.IndexConfigurationError
make_signature = _indexar.make_signature
read_chunks = _indexar.read_chunks

JURISDICCIONES = ("nacional", "pba", "santa_fe")


def build_evidence_context(results: list[dict[str, Any]]) -> str:
    """Arma evidencia literal numerada en el orden exacto de recuperación.

    El generador reutiliza este contexto, sin seleccionar ni reordenar chunks.
    """
    blocks = []
    for number, result in enumerate(results, 1):
        lines = [f"[{number}]", f"chunk_id: {result['chunk_id']}",
                 f"source_article_id: {result['source_article_id']}",
                 f"jurisdiccion: {result['jurisdiccion']}", f"ley: {result['ley']}",
                 f"articulo: {result['articulo']}", f"source: {result['source']}"]
        if "pagina_inicio" in result:
            lines.append(f"paginas_articulo: {result['pagina_inicio']}–{result['pagina_fin']}")
        lines.extend(["texto:", result["text"]])
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


class RetrievalIndexError(RuntimeError):
    """El índice persistido falta, está vacío o no corresponde al corpus/modelo."""


def build_result(rank: int, chunk_id: str, metadata: dict[str, Any], text: str,
                 distance: float | None) -> dict[str, Any]:
    """Normaliza un resultado de Chroma sin perder texto ni procedencia.

    La distancia es una medida de vecindad interna al índice, no confianza
    probabilística ni prueba de que el fragmento responda la pregunta.
    """
    result = {
        "rank": rank,
        "id": chunk_id,
        "chunk_id": chunk_id,
        "source_article_id": metadata.get("source_article_id"),
        "jurisdiccion": metadata.get("jurisdiccion"),
        "ley": metadata.get("ley"),
        "articulo": metadata.get("articulo"),
        "source": metadata.get("source"),
        "chunk_numero": metadata.get("chunk_numero"),
        "text": text,
        "distance": distance,
        "distance_kind": "Chroma native distance; lower means closer, not probability/confidence",
    }
    for field in ("pagina_inicio", "pagina_fin", "libro", "titulo", "capitulo"):
        if field in metadata and metadata[field] is not None:
            result[field] = metadata[field]
    return result


class SemanticRetriever:
    """Recuperador reutilizable de solo lectura: nunca reindexa ni borra datos."""

    def __init__(self, *, index_dir: Path = DEFAULT_INDEX, chunks_path: Path = DEFAULT_INPUT,
                 model: str = DEFAULT_MODEL, embeddings: Any = None,
                 vector_store_class: Any = None):
        """Abre solo un índice compatible con el JSONL y modelo solicitados.

        Rechaza manifests o IDs distintos; recuperar nunca corrige el índice
        ni reingesta documentos silenciosamente.
        """
        self.index_dir = Path(index_dir).expanduser().resolve()
        self.chunks_path = Path(chunks_path).expanduser().resolve()
        self.model = model
        try:
            _, chunks_hash = read_chunks(self.chunks_path)
        except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            raise RetrievalIndexError(f"No se pueden validar los chunks de referencia: {exc}") from exc
        expected_signature = make_signature(chunks_hash, model)
        manifest_path = self.index_dir / MANIFEST
        if not self.index_dir.is_dir() or not manifest_path.is_file():
            raise RetrievalIndexError(f"Falta el índice o su manifest: {self.index_dir}")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RetrievalIndexError(f"Manifest inválido: {manifest_path}") from exc
        if manifest != expected_signature:
            raise IndexConfigurationError(
                "Firma incompatible: índice, modelo o chunks no corresponden a esta consulta. "
                "La recuperación es read-only; no se reconstruyó el índice."
            )

        chunks, _ = read_chunks(self.chunks_path)
        expected_ids = {chunk["id"] for chunk in chunks}
        self.embeddings = embeddings or OllamaEmbeddings(
            model=model, base_url=expected_signature["ollama_base_url"])
        store_factory = vector_store_class or Chroma
        try:
            self.store = store_factory(
                collection_name=COLLECTION,
                embedding_function=self.embeddings,
                persist_directory=str(self.index_dir),
                create_collection_if_not_exists=False,
            )
            persisted = self.store.get(include=["metadatas"])
        except Exception as exc:
            raise RetrievalIndexError(f"No existe o no se puede leer la colección {COLLECTION}: {exc}") from exc
        stored_ids = persisted.get("ids", [])
        if not stored_ids:
            raise RetrievalIndexError(f"La colección {COLLECTION} está vacía")
        if len(stored_ids) != len(set(stored_ids)) or set(stored_ids) != expected_ids:
            raise RetrievalIndexError(
                f"IDs del índice incompatibles: esperados {len(expected_ids)}, obtenidos {len(stored_ids)}; "
                "no se modificó el índice."
            )
        self.count = len(stored_ids)
        self._expected_ids = expected_ids

    def integrity_snapshot(self) -> dict[str, Any]:
        """Resume IDs y manifest para detectar alteraciones antes/después de evaluar."""
        current = self.store.get(include=[]).get("ids", [])
        manifest_bytes = (self.index_dir / MANIFEST).read_bytes()
        return {"count": len(current),
                "ids_sha256": hashlib.sha256("\n".join(sorted(current)).encode("utf-8")).hexdigest(),
                "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "ids_match_chunks": len(current) == len(set(current)) and set(current) == self._expected_ids}

    def retrieve(self, question: str, k: int = 5,
                 jurisdiccion: str | None = None) -> list[dict[str, Any]]:
        """Calcula el embedding de la pregunta y consulta Chroma con filtro opcional.

        K limita vecinos devueltos, no garantiza relevancia: la validación del
        contenido recuperado corresponde a la evaluación y al generador.
        """
        _validate_request(question, k, jurisdiccion)
        vector = self.embeddings.embed_query(question)
        kwargs = {"query_embeddings": [vector], "n_results": k,
                  "include": ["documents", "metadatas", "distances"]}
        if jurisdiccion is not None:
            kwargs["where"] = {"jurisdiccion": jurisdiccion}
        raw = self.store._collection.query(**kwargs)
        ids = raw.get("ids", [[]])[0]
        texts = raw.get("documents", [[]])[0]
        metadatas = raw.get("metadatas", [[]])[0]
        distances = raw.get("distances", [[]])
        distances = distances[0] if distances and distances[0] is not None else []
        results = []
        for pos, (chunk_id, text, metadata) in enumerate(zip(ids, texts, metadatas), 1):
            distance = distances[pos - 1] if pos <= len(distances) else None
            results.append(build_result(pos, chunk_id, metadata or {}, text, distance))
        return results


def _validate_request(question: str, k: int, jurisdiccion: str | None) -> None:
    """Rechaza preguntas vacías, K no positivo y jurisdicciones fuera del corpus."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question debe ser una cadena no vacía")
    if type(k) is not int or k <= 0:
        raise ValueError("k debe ser un entero positivo")
    if jurisdiccion is not None and jurisdiccion not in JURISDICCIONES:
        raise ValueError(f"jurisdiccion debe ser una de {JURISDICCIONES} o None")


def retrieve(question: str, k: int = 5, jurisdiccion: str | None = None, *,
             index_dir: Path = DEFAULT_INDEX, chunks_path: Path = DEFAULT_INPUT,
             model: str = DEFAULT_MODEL, retriever: SemanticRetriever | None = None) -> list[dict[str, Any]]:
    """Devuelve hasta K vecinos con texto íntegro y procedencia del índice local."""
    _validate_request(question, k, jurisdiccion)
    active_retriever = retriever or SemanticRetriever(index_dir=index_dir, chunks_path=chunks_path, model=model)
    return active_retriever.retrieve(question, k=k, jurisdiccion=jurisdiccion)


def main() -> int:
    """CLI de recuperación: decide jurisdicción antes de acceder a Chroma.

    Si la pregunta es ambigua pide aclaración, salvo selección manual o búsqueda
    sin filtro solicitada explícitamente.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pregunta", required=True)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--jurisdiccion", choices=JURISDICCIONES)
    parser.add_argument("--sin-filtro", action="store_true", help="desactiva explícitamente el enrutamiento automático")
    parser.add_argument("--index-dir", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()
    if args.jurisdiccion and args.sin_filtro:
        parser.error("--jurisdiccion y --sin-filtro son incompatibles")
    decision = detect_jurisdiction(args.pregunta)
    if args.jurisdiccion:
        jurisdictions, status, source = [args.jurisdiccion], "identified", "manual"
    elif args.sin_filtro:
        jurisdictions, status, source = [None], "unfiltered", "unfiltered"
    elif decision["status"] in {"identified", "comparative"}:
        jurisdictions, status, source = decision["jurisdictions"], decision["status"], "automatic"
    else:
        print(f"Enrutamiento: {decision['status']} | {decision['reason']}\n"
              f"Pregunta de aclaración: {decision['clarification_question'] or 'La jurisdicción no está cubierta por el corpus.'}\n"
              "No se realizó recuperación.")
        return 0
    try:
        retriever = SemanticRetriever(index_dir=args.index_dir, chunks_path=args.chunks, model=args.model)
        grouped = {j: retriever.retrieve(args.pregunta, k=args.k, jurisdiccion=j) for j in jurisdictions}
    except (ValueError, RetrievalIndexError, IndexConfigurationError) as exc:
        parser.error(str(exc))
    filter_text = ", ".join(j or "sin filtro" for j in jurisdictions)
    reason = (f"Jurisdicción seleccionada manualmente: {args.jurisdiccion}."
              if source == "manual" else decision["reason"])
    print(f"Enrutamiento: {status} | fuente={source} | jurisdicciones={jurisdictions}\n"
          f"Justificación: {reason} | alcance={filter_text} | k={args.k} por jurisdicción")
    for jurisdiction, results in grouped.items():
        print(f"\n{jurisdiction or 'sin filtro'}: {len(results)} resultados; k={args.k}; "
              "distancia nativa Chroma (menor=vecino más cercano, no probabilidad)")
        for result in results:
            page = (f" pp. {result['pagina_inicio']}–{result['pagina_fin']}"
                    if "pagina_inicio" in result and "pagina_fin" in result else "")
            print(f"{result['rank']}. {result['chunk_id']} | {result['jurisdiccion']} | "
                  f"Ley {result['ley']}, art. {result['articulo']} | {result['source']}{page} | "
                  f"distance={result['distance']}")
            print(f"   {result['text'][:350].replace(chr(10), ' ')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
