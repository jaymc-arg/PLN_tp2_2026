"""Indexa chunks JSONL en Chroma persistente con embeddings Ollama locales."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "datos/procesados/chunks.jsonl"
DEFAULT_INDEX = ROOT / ".chroma/electoral_laws"
COLLECTION = "electoral_laws"
DEFAULT_MODEL = "bge-m3"
MANIFEST = "index_manifest.json"
SIGNATURE_VERSION = 1
REQUIRED_FIELDS = (
    "id", "texto", "source_article_id", "jurisdiccion", "ley", "articulo", "source", "chunk_numero",
)
METADATA_FIELDS = (
    "source_article_id", "jurisdiccion", "ley", "articulo", "source", "chunk_numero",
    "libro", "titulo", "capitulo", "pagina_inicio", "pagina_fin", "inicio_vista", "vista",
)


class IndexConfigurationError(RuntimeError):
    """La firma persistida no coincide o el directorio contiene un índice no administrado."""

# Lee los documentos, los verifica y hashea
def read_chunks(path: Path) -> tuple[list[dict[str, Any]], str]:
    raw = path.read_bytes()
    chunks = []
    seen = set()
    for line_number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        chunk = json.loads(line)
        missing = [key for key in REQUIRED_FIELDS if key not in chunk]
        if missing:
            raise ValueError(f"{path}:{line_number}: faltan campos {missing}")
        if not isinstance(chunk["id"], str) or not chunk["id"]:
            raise ValueError(f"{path}:{line_number}: id inválido")
        if chunk["id"] in seen:
            raise ValueError(f"{path}:{line_number}: ID duplicado {chunk['id']}")
        if not isinstance(chunk["texto"], str) or not chunk["texto"].strip():
            raise ValueError(f"{path}:{line_number}: texto vacío")
        seen.add(chunk["id"])
        chunks.append(chunk)
    if not chunks:
        raise ValueError(f"No hay chunks indexables en {path}")
    return chunks, hashlib.sha256(raw).hexdigest()

# Valida la presencia de metadatos obligatorios y que sean escalares; omite explícitamente los valores null.
def chunk_metadata(chunk: dict[str, Any]) -> dict[str, str | int | float | bool]:
    """Chroma admite metadatos escalares; omite explícitamente los valores null."""
    metadata = {}
    for key in METADATA_FIELDS:
        value = chunk.get(key)
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            metadata[key] = value
        else:
            raise ValueError(f"Metadata Chroma no escalar en {chunk.get('id')}: {key}={value!r}")
    for key in ("source_article_id", "jurisdiccion", "ley", "articulo", "source", "chunk_numero"):
        if key not in metadata:
            raise ValueError(f"Metadata obligatoria ausente para {chunk.get('id')}: {key}")
    if "pagina_inicio" in metadata and "pagina_fin" not in metadata:
        raise ValueError(f"Rango PDF incompleto para {chunk.get('id')}")
    if "pagina_fin" in metadata and "pagina_inicio" not in metadata:
        raise ValueError(f"Rango PDF incompleto para {chunk.get('id')}")
    return metadata

# Convierte los chunks en Documentos de LangChain y devuelve la lista de IDs.
def to_documents(chunks: list[dict[str, Any]]) -> tuple[list[Document], list[str]]:
    documents, ids = [], []
    for chunk in chunks:
        ids.append(chunk["id"])
        documents.append(Document(page_content=chunk["texto"], metadata=chunk_metadata(chunk)))
    return documents, ids

# Genera la firma del índice a partir del hash de los chunks y el modelo.
def make_signature(chunks_sha256: str, model: str, collection: str = COLLECTION) -> dict[str, Any]:
    return {"managed_by": "tp2-rag-04", "signature_version": SIGNATURE_VERSION,
            "embedding_model": model, "ollama_base_url": "http://localhost:11434",
            "collection": collection, "chunks_sha256": chunks_sha256}


def prepare_index_dir(index_dir: Path, signature: dict[str, Any], *, rebuild: bool) -> None:
    resolved = index_dir.expanduser().resolve()
    forbidden = {Path(resolved.anchor), ROOT.resolve(), ROOT.resolve().parent,
                 (ROOT / "datos").resolve(), Path.home().resolve()}
    if resolved in forbidden or resolved == ROOT.resolve() / "datos/procesados":
        raise ValueError(f"Ruta de índice insegura: {resolved}")
    manifest_path = resolved / MANIFEST
    if rebuild and resolved.exists():
        if any(resolved.iterdir()):
            # Never recursively remove an unrecognized directory on the strength of a typo.
            try:
                existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise IndexConfigurationError(
                    f"No se reconstruye {resolved}: no contiene un manifest válido de este índice."
                ) from exc
            if existing.get("managed_by") != "tp2-rag-04":
                raise IndexConfigurationError(f"El directorio no pertenece a este indexador: {resolved}")
            shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)
    if any(resolved.iterdir()):
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IndexConfigurationError(
                f"Índice local sin configuración reconocida en {resolved}; revisar o usar --rebuild sólo si es propio."
            ) from exc
        if existing != signature:
            raise IndexConfigurationError(
                "Firma de índice incompatible (modelo, colección o chunks diferentes). "
                "No se reutiliza; ejecutar --rebuild para regenerar sólo este directorio."
            )
    else:
        manifest_path.write_text(json.dumps(signature, indent=2) + "\n", encoding="utf-8")


def software_versions() -> dict[str, str]:
    packages = ("langchain-chroma", "langchain-ollama", "chromadb", "ollama")
    versions = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "no instalado"
    return versions


def run_index(chunks_path: Path = DEFAULT_INPUT, index_dir: Path = DEFAULT_INDEX, *,
              model: str = DEFAULT_MODEL, rebuild: bool = False, smoke_question: str | None = None,
              embeddings: Any = None, vector_store_class: Any = None) -> dict[str, Any]:
    chunks, chunks_hash = read_chunks(chunks_path)
    signature = make_signature(chunks_hash, model)
    documents, ids = to_documents(chunks)
    embeddings = embeddings if embeddings is not None else OllamaEmbeddings(
        model=model, base_url="http://localhost:11434")
    query = smoke_question or "¿Qué excepciones al deber de votar establece el artículo 12?"
    # Verifica servicio/modelo antes de crear la carpeta o manifest del índice.
    query_vector = embeddings.embed_query(query)
    dimensions = len(query_vector) if query_vector is not None else None
    prepare_index_dir(index_dir, signature, rebuild=rebuild)
    vector_store_class = vector_store_class if vector_store_class is not None else Chroma
    store = vector_store_class(collection_name=COLLECTION, embedding_function=embeddings,
                               persist_directory=str(index_dir))
    existing = store.get(include=["metadatas"])
    existing_ids = set(existing.get("ids", []))
    if not existing_ids.issubset(set(ids)):
        raise IndexConfigurationError("El índice contiene IDs ajenos a chunks.jsonl; usar --rebuild.")
    missing_ids = set(ids) - existing_ids
    if missing_ids:
        by_id = dict(zip(ids, documents))
        to_add_ids = [chunk_id for chunk_id in ids if chunk_id in missing_ids]
        store.add_documents([by_id[chunk_id] for chunk_id in to_add_ids], ids=to_add_ids)
    stored = store.get(include=["metadatas"])
    actual_ids = stored.get("ids", [])
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(ids):
        raise RuntimeError(f"Verificación Chroma fallida: esperado {len(ids)} IDs, obtenido {len(actual_ids)}")
    expected_metadata = {chunk_id: document.metadata for chunk_id, document in zip(ids, documents)}
    actual_metadata = dict(zip(actual_ids, stored.get("metadatas", [])))
    if any(actual_metadata.get(chunk_id) != expected_metadata[chunk_id] for chunk_id in ids):
        raise RuntimeError("Verificación Chroma fallida: metadatos almacenados no coinciden con chunks.jsonl")

    # La consulta nativa retorna también los IDs persistidos; se usa el mismo objeto
    # OllamaEmbeddings/modelo que generó los vectores del índice.
    results = store._collection.query(query_embeddings=[query_vector], n_results=min(3, len(ids)),
                                      include=["metadatas", "documents"])
    ranked = []
    for rank, (chunk_id, metadata, text) in enumerate(zip(
            results["ids"][0], results["metadatas"][0], results["documents"][0]), 1):
        ranked.append({"rank": rank, "id": chunk_id, "source_article_id": metadata.get("source_article_id"),
                       "jurisdiccion": metadata.get("jurisdiccion"), "articulo": metadata.get("articulo"),
                       "source": metadata.get("source"), "pagina_inicio": metadata.get("pagina_inicio"),
                       "pagina_fin": metadata.get("pagina_fin"), "excerpt": text[:220].replace("\n", " ")})
    result = {"indexed_count": len(actual_ids), "expected_count": len(ids), "dimensions": dimensions,
              "model": model, "collection": COLLECTION, "index_dir": str(index_dir),
              "smoke_query": query, "ranked": ranked, "versions": software_versions()}
    print(f"Indexados {len(actual_ids)}/{len(ids)} chunks; modelo={model}; dimensión="
          f"{dimensions if dimensions is not None else 'no informada'}; colección={COLLECTION}; ruta={index_dir}")
    print("Inspección semántica (no demuestra corrección de respuestas):")
    for row in ranked:
        page = (f" pp.{row['pagina_inicio']}-{row['pagina_fin']}" if row["pagina_inicio"] is not None else "")
        print(f"{row['rank']}. {row['id']} | {row['source_article_id']} | {row['jurisdiccion']} "
              f"art. {row['articulo']} {row['source']}{page} | {row['excerpt']}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--index-dir", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--rebuild", action="store_true",
                        help="elimina y reconstruye únicamente el directorio de índice local seleccionado")
    parser.add_argument("--smoke-question", default=None)
    args = parser.parse_args()
    try:
        run_index(args.chunks, args.index_dir, model=args.model,
                  rebuild=args.rebuild, smoke_question=args.smoke_question)
    except Exception as exc:
        print(f"Error al indexar: {exc}", file=sys.stderr)
        if "ollama" in str(exc).lower() or "connection" in str(exc).lower():
            print("Compruebe que Ollama esté instalado/en ejecución y que exista el modelo: ollama pull bge-m3",
                  file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
