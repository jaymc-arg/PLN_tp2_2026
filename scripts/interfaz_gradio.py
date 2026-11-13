"""Interfaz local de consulta: no construye ni modifica el índice."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import gradio as gr

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import generar

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


def consultar(question: str, k: int = 3, jurisdiction: str = "Automática") -> tuple[str, str, str, str, str]:
    if not isinstance(question, str) or not question.strip():
        return "Escribí una pregunta no vacía.", "Sin consulta.", "", "", "No aplica: sin consulta."
    try:
        if k not in (1, 3, 5):
            raise ValueError("K debe ser 1, 3 o 5.")
        result = generar.answer_question(question, k=int(k), **ROUTING_OPTIONS[jurisdiction])
        return format_result(result)
    except Exception as exc:
        # También incluye errores de conexión/embeddings; nunca reconstruir ni usar fallback.
        return (f"No se pudo completar la consulta ({type(exc).__name__}): {exc}\n"
                "Comprobá el índice compatible previamente construido y Ollama activo con "
                "bge-m3 y granite4:latest. No se reconstruyó el índice ni se cambió de modelo.",
                "Consulta fallida.", "", "", "No aplica: consulta fallida.")


def main() -> None:
    with gr.Blocks(title="Consulta de legislación electoral", analytics_enabled=False) as app:
        gr.Markdown("# Consulta de legislación electoral\n"
                    "Solo lectura. K se aplica **por jurisdicción** en preguntas comparativas. "
                    "Sin filtro es un modo exploratorio. No se verifica vigencia ni apoyo semántico de citas.")
        question = gr.Textbox(label="Pregunta", lines=3)
        k = gr.Dropdown(choices=[1, 3, 5], value=3, label="K (fragmentos por jurisdicción)")
        jurisdiction = gr.Dropdown(choices=list(ROUTING_OPTIONS), value="Automática", label="Jurisdicción")
        button = gr.Button("Consultar")
        answer = gr.Textbox(label="Respuesta", lines=6, interactive=False)
        routing = gr.Textbox(label="Enrutamiento", lines=5, interactive=False)
        sources = gr.Textbox(label="Fuentes recuperadas", lines=8, interactive=False)
        context = gr.Textbox(label="Evidencia enviada al modelo", lines=18, max_lines=18, interactive=False)
        citations = gr.Textbox(label="Revisión de citas", lines=6, interactive=False)
        button.click(consultar, inputs=[question, k, jurisdiction],
                     outputs=[answer, routing, sources, context, citations])
    app.launch(server_name="127.0.0.1", share=False)


if __name__ == "__main__":
    main()
