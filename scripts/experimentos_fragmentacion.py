"""Preparación explícita de índices aislados; nunca escribe el baseline."""
from __future__ import annotations

import hashlib
from importlib.metadata import version
import json
from pathlib import Path
from typing import Any

from importlib import import_module

fragmentar = import_module("scripts.01_fragmentar")
indexar = import_module("scripts.02_indexar")
SemanticRetriever = import_module("scripts.03_recuperar").SemanticRetriever

INPUT_DIR = indexar.DEFAULT_INPUT.parent
EXPERIMENT_ROOT = indexar.ROOT / ".chroma/experimentos"


def validate_parameters(chunk_size: int, chunk_overlap: int) -> None:
    """Rechaza valores fraccionarios o fuera del rango admitido por el laboratorio.

    Gradio puede enviar números como float aun cuando visualmente sean enteros.
    """
    # Gradio Number puede entregar enteros como float; no aceptar fracciones ni bool.
    if (isinstance(chunk_size, bool) or isinstance(chunk_overlap, bool)
            or not isinstance(chunk_size, (int, float)) or not isinstance(chunk_overlap, (int, float))
            or not 300 <= chunk_size <= 2000 or not 0 <= chunk_overlap < chunk_size
            or int(chunk_size) != chunk_size or int(chunk_overlap) != chunk_overlap):
        raise ValueError("Usá enteros: 300 ≤ chunk_size ≤ 2000 y 0 ≤ chunk_overlap < chunk_size (caracteres).")


def configuration(chunk_size: int, chunk_overlap: int) -> dict[str, Any]:
    """Identidad por parámetros, modelo, contenido y código/versión del splitter."""
    validate_parameters(chunk_size, chunk_overlap)
    inputs = {
        f"{jurisdiction}_articulos.jsonl": hashlib.sha256(
            (INPUT_DIR / f"{jurisdiction}_articulos.jsonl").read_bytes()).hexdigest()
        for jurisdiction in fragmentar.JURISDICTIONS
    }
    signature = {
        "chunk_size": int(chunk_size), "chunk_overlap": int(chunk_overlap),
        "embedding_model": indexar.DEFAULT_MODEL, "inputs": inputs,
        "splitter_code": hashlib.sha256(Path(fragmentar.__file__).read_bytes()).hexdigest(),
        "splitter_version": version("langchain-text-splitters"),
    }
    identifier = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    directory = EXPERIMENT_ROOT / identifier
    return {"chunk_size": int(chunk_size), "chunk_overlap": int(chunk_overlap),
            "index_dir": str(directory / "indice"), "chunks_path": str(directory / "chunks.jsonl")}


def prepare_experiment(chunk_size: int, chunk_overlap: int) -> tuple[dict[str, Any], str]:
    """Construye o reutiliza un índice aislado sin alterar el baseline.

    La identidad incluye parámetros, corpus, modelo y código del splitter;
    no sobrescribe artefactos incompletos ni sigue enlaces simbólicos.
    """
    active = configuration(chunk_size, chunk_overlap)  # valida antes de cualquier I/O
    chunks_path, index_dir = Path(active["chunks_path"]), Path(active["index_dir"])
    # No seguir enlaces que pudieran redirigir una escritura fuera del experimento.
    directory = chunks_path.parent
    if (directory.resolve() != directory.absolute() or index_dir.resolve() != index_dir.absolute()
            or chunks_path.is_symlink()):
        raise ValueError("Ruta experimental con enlaces simbólicos: no se escribe ni se reutiliza.")
    report = chunks_path.with_name("reporte_fragmentacion.json")
    if report.is_symlink():
        raise ValueError("Reporte experimental con enlace simbólico.")
    if index_dir.exists() and not chunks_path.is_file():
        raise ValueError("Índice experimental sin chunks: revisar artefactos incompletos; no se sobrescriben.")
    reused = False
    if chunks_path.exists():
        indexar.read_chunks(chunks_path)  # rechazar truncados/corruptos sin reescribir
        if not report.is_file():
            raise ValueError("Falta reporte_fragmentacion.json; revisar preparación interrumpida, sin sobrescritura automática.")
        json.loads(report.read_text(encoding="utf-8"))
        if index_dir.exists():
            # Una configuración existente incompatible falla; nunca se reconstruye.
            retriever = SemanticRetriever(index_dir=index_dir, chunks_path=chunks_path,
                                          model=indexar.DEFAULT_MODEL)
            reused = True
    else:
        fragmentar.build_chunks(INPUT_DIR, chunks_path, chunk_size=int(chunk_size),
                                chunk_overlap=int(chunk_overlap))
    if configuration(chunk_size, chunk_overlap) != active:
        raise ValueError("Los artículos cambiaron durante la preparación; volver a preparar la nueva configuración.")
    if not reused:
        indexar.run_index(chunks_path, index_dir, model=indexar.DEFAULT_MODEL, rebuild=False)
        retriever = SemanticRetriever(index_dir=index_dir, chunks_path=chunks_path,
                                      model=indexar.DEFAULT_MODEL)
    status = (f"{'Reutilizado' if reused else 'Listo'}: {chunk_size}/{chunk_overlap} caracteres; "
              f"{retriever.count} chunks.\nÍndice: {index_dir}\nChunks: {chunks_path}")
    return active, status
