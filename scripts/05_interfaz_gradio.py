"""Consulta local de solo lectura y laboratorio explícito de índices aislados."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import gradio as gr

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from importlib import import_module

generar = import_module("scripts.04_generar")
indexar = import_module("scripts.02_indexar")
from scripts.experimentos_fragmentacion import configuration, prepare_experiment

ORIGINAL = "Índice original"
EXPERIMENTAL = "Índice experimental"

ROUTING_OPTIONS = {
    "Automática": {},
    "Nación": {"jurisdiccion": "nacional"},
    "Provincia de Buenos Aires": {"jurisdiccion": "pba"},
    "Santa Fe": {"jurisdiccion": "santa_fe"},
    "Sin filtro (exploratoria)": {"sin_filtro": True},
}


def format_result(result: dict[str, Any]) -> tuple[str, str, str, str, str]:
    """Presenta el resultado sin recuperar ni reconstruir el contexto."""
    answer = result["answer"]
    if result.get("clarification_question"):
        answer += "\n\n" + result["clarification_question"]
    source = {"automatic": "automática", "manual": "manual", "unfiltered": "sin filtro"}
    routing = (
        f"Estado: {result.get('routing_status')}\n"
        f"Origen: {source.get(result.get('jurisdiction_source'), result.get('jurisdiction_source'))}\n"
        f"Jurisdicciones detectadas/seleccionadas: {result.get('jurisdictions', [])}\n"
        f"Filtro aplicado: {result.get('applied_filter') or 'sin filtro'}\n"
        f"Motivo: {result.get('routing_reason', '')}"
    )
    sources = []
    for item in result["source_map"]:
        line = (f"[{item['number']}] chunk ID: {item.get('chunk_id')} | "
                f"Ley: {item.get('ley')} | Artículo: {item.get('articulo')} | "
                f"Jurisdicción: {item.get('jurisdiccion')} | Archivo original: {item.get('source')}")
        if item.get("distance") is not None:
            line += f" | Distancia nativa: {item['distance']}"
        if item.get("pagina_inicio") is not None and item.get("pagina_fin") is not None:
            line += f" | Páginas del artículo: {item['pagina_inicio']}–{item['pagina_fin']}"
        sources.append(line)
    sources_text = "\n\n".join(sources) or "Sin fuentes recuperadas."
    sources_text += "\n\nLas distancias no son probabilidades ni puntajes de confianza."
    check = result.get("citation_check")
    if check is None or not result.get("model_invoked"):
        citations = "No aplica: no se invocó el modelo."
    else:
        citations = (
            f"Validez sintáctica: {check['citations_valid']}\n"
            f"Advertencia de citas faltantes: {check['citations_missing']}\n"
            f"Advertencia de citas inválidas: {check['citations_invalid']}\n"
            f"Referencias inexistentes: {json.dumps(check['invalid_references'], ensure_ascii=False)}\n"
            f"Referencias malformadas: {json.dumps(check['malformed_references'], ensure_ascii=False)}"
        )
    citations += "\nLa validez sintáctica NO verifica el apoyo semántico de las afirmaciones."
    return answer, routing, sources_text, result["context_sent"], citations


def consultar(question: str, k: int = 3, jurisdiction: str = "Automática",
              mode: str = ORIGINAL, chunk_size: int = 1000, chunk_overlap: int = 150,
              active: dict[str, Any] | None = None) -> tuple[str, str, str, str, str]:
    if not isinstance(question, str) or not question.strip():
        return "Escribí una pregunta no vacía.", "Sin consulta.", "", "", "No aplica: sin consulta."
    try:
        if k not in (1, 3, 5):
            raise ValueError("K debe ser 1, 3 o 5.")
        paths = {"index_dir": indexar.DEFAULT_INDEX, "chunks_path": indexar.DEFAULT_INPUT}
        description = f"Índice original | parámetros baseline: 1000/150 caracteres | {indexar.DEFAULT_INDEX}"
        if mode == EXPERIMENTAL:
            if active is None or configuration(chunk_size, chunk_overlap) != active:
                raise ValueError("Configuración experimental no preparada o modificada. Pulsá Preparar / reutilizar.")
            paths = {"index_dir": Path(active["index_dir"]), "chunks_path": Path(active["chunks_path"])}
            description = (f"Índice experimental | {active['chunk_size']}/{active['chunk_overlap']} caracteres | "
                           f"{active['index_dir']}")
        elif mode != ORIGINAL:
            raise ValueError("Modo de índice desconocido.")
        result = generar.answer_question(question, k=int(k), **paths, **ROUTING_OPTIONS[jurisdiction])
        answer, routing, sources, context, citations = format_result(result)
        return answer, description + "\n" + routing, sources, context, citations
    except Exception as exc:
        # También incluye errores de conexión/embeddings; nunca reconstruir ni usar fallback.
        return (f"No se pudo completar la consulta ({type(exc).__name__}): {exc}\n"
                "Comprobá el índice compatible previamente construido y Ollama activo con "
                f"{indexar.DEFAULT_MODEL} y {generar.DEFAULT_GENERATION_MODEL}. No se reconstruyó el índice ni se cambió de modelo.",
                "Consulta fallida.", "", "", "No aplica: consulta fallida.")


def invalidate_configuration(mode: str):
    """Cambiar controles solo invalida el estado y limpia resultados; no toca disco."""
    status = ("Índice original seleccionado (consulta de solo lectura)." if mode == ORIGINAL
              else "No preparado: pulsá Preparar / reutilizar para aplicar los valores visibles.")
    return None, status, "", "", "", "", ""


def preparar(mode: str, chunk_size: int, chunk_overlap: int):
    """Dos actualizaciones visibles: construyendo y listo/error. Solo se enlaza al botón."""
    if mode != EXPERIMENTAL:
        yield invalidate_configuration(mode)
        return
    yield None, "Construyendo / validando configuración experimental…", "", "", "", "", ""
    try:
        active, status = prepare_experiment(chunk_size, chunk_overlap)
        yield active, status, "", "", "", "", ""
    except Exception as exc:
        yield (None, f"Error ({type(exc).__name__}): {exc}\n"
               f"Revisá artículos procesados, artefactos y Ollama con {indexar.DEFAULT_MODEL}. "
               "No se borraron índices ni se usó otro modelo; el baseline no se modificó.",
               "", "", "", "", "")


def main() -> None:
    with gr.Blocks(title="Consulta de legislación electoral", analytics_enabled=False) as app:
        gr.Markdown("# Consulta de legislación electoral\n"
                    "Las consultas son de solo lectura. K se aplica **por jurisdicción** en preguntas comparativas. "
                    "Sin filtro es un modo exploratorio. No se verifica vigencia ni apoyo semántico de citas.")
        active = gr.State(None)
        gr.Markdown("## Laboratorio de fragmentación\n"
                    "Medidas en **caracteres, no tokens**. Cambiar valores invalida la preparación; "
                    "solo el botón Preparar divide e indexa. El índice original nunca se reconstruye aquí.")
        mode = gr.Radio([ORIGINAL, EXPERIMENTAL], value=ORIGINAL, label="Modo de índice")
        chunk_size = gr.Number(value=1000, minimum=300, maximum=2000, precision=0,
                               label="chunk_size (caracteres)")
        chunk_overlap = gr.Number(value=150, minimum=0, maximum=1999, precision=0,
                                  label="chunk_overlap (caracteres; menor que chunk_size)")
        prepare = gr.Button("Preparar / reutilizar índice experimental")
        status = gr.Textbox(label="Estado del laboratorio", value="Índice original seleccionado.",
                            lines=4, interactive=False)
        question = gr.Textbox(label="Pregunta", lines=3)
        k = gr.Dropdown(choices=[1, 3, 5], value=3, label="K (fragmentos por jurisdicción)")
        jurisdiction = gr.Dropdown(choices=list(ROUTING_OPTIONS), value="Automática", label="Jurisdicción")
        button = gr.Button("Consultar")
        answer = gr.Textbox(label="Respuesta", lines=6, interactive=False)
        routing = gr.Textbox(label="Enrutamiento", lines=5, interactive=False)
        sources = gr.Textbox(label="Fuentes recuperadas", lines=8, interactive=False)
        context = gr.Textbox(label="Evidencia enviada al modelo", lines=18, max_lines=18, interactive=False)
        citations = gr.Textbox(label="Revisión de citas", lines=6, interactive=False)
        outputs = [answer, routing, sources, context, citations]
        laboratory_outputs = [active, status, *outputs]
        for control in (mode, chunk_size, chunk_overlap):
            control.change(invalidate_configuration, inputs=[mode], outputs=laboratory_outputs,
                           queue=False)
        prepare.click(preparar, inputs=[mode, chunk_size, chunk_overlap], outputs=laboratory_outputs,
                      concurrency_id="laboratorio", concurrency_limit=1)
        button.click(consultar, inputs=[question, k, jurisdiction, mode, chunk_size, chunk_overlap, active],
                     outputs=outputs, concurrency_id="laboratorio", concurrency_limit=1)
    app.launch(server_name="127.0.0.1", share=False)


if __name__ == "__main__":
    main()
