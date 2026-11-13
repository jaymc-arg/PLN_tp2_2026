"""Pruebas offline; no miden desempeño del RAG real."""
import importlib
from unittest.mock import Mock

import pytest

from scripts import evaluar_recuperacion, generar, interfaz_gradio as ui, recuperar


def result():
    return {
        "answer": "Respuesta [1] [2]", "routing_status": "comparative",
        "jurisdiction_source": "automatic", "jurisdictions": ["pba", "santa_fe"],
        "applied_filter": ["pba", "santa_fe"], "routing_reason": "Comparación explícita",
        "source_map": [
            {"number": 1, "chunk_id": "a", "ley": "5109", "articulo": "13",
             "jurisdiccion": "pba", "source": "original.txt", "distance": 0.0},
            {"number": 2, "chunk_id": "b", "ley": "14478", "articulo": "4",
             "jurisdiccion": "santa_fe", "source": "original.pdf", "pagina_inicio": 1,
             "pagina_fin": 4},
        ],
        "context_sent": "[1]\n<texto> & **literal**\n\n[2]\n" + "texto\n" * 2000,
        "model_invoked": True,
        "citation_check": {"citations_valid": False, "citations_missing": True,
                           "citations_invalid": True,
                           "invalid_references": [{"token": "[9]"}],
                           "malformed_references": [{"token": "[x]"}]},
    }


@pytest.mark.parametrize("k", [1, 3, 5])
@pytest.mark.parametrize("mode,kwargs", [
    ("Automática", {}), ("Nación", {"jurisdiccion": "nacional"}),
    ("Provincia de Buenos Aires", {"jurisdiccion": "pba"}),
    ("Santa Fe", {"jurisdiccion": "santa_fe"}),
    ("Sin filtro (exploratoria)", {"sin_filtro": True}),
])
def test_forward_once(monkeypatch, k, mode, kwargs):
    backend = Mock(return_value=result())
    monkeypatch.setattr(generar, "answer_question", backend)
    assert ui.consultar("Pregunta", k, mode)[0] == "Respuesta [1] [2]"
    backend.assert_called_once_with("Pregunta", k=k, **kwargs)


@pytest.mark.parametrize("question", ["", " \n\t", None])
def test_empty_no_backend(monkeypatch, question):
    backend = Mock()
    monkeypatch.setattr(generar, "answer_question", backend)
    assert "no vacía" in ui.consultar(question)[0]
    backend.assert_not_called()


def test_format_full_context_sources_and_warnings():
    data = result()
    answer, route, sources, context, citations = ui.format_result(data)
    assert context == data["context_sent"]
    assert sources.index("[1]") < sources.index("[2]")
    assert "Páginas" not in sources.split("[2]")[0]
    assert "Páginas del artículo: 1–4" in sources
    assert "Distancia nativa: 0.0" in sources
    assert "Distancia nativa" not in sources.split("[2]")[1]
    assert "pba" in route and "santa_fe" in route and "automática" in route
    assert "faltantes: True" in citations and "inválidas: True" in citations
    assert "[9]" in citations and "[x]" in citations and "NO verifica" in citations


@pytest.mark.parametrize("question,status", [
    ("¿Cómo se vota en PBA?", "ambiguous"),
    ("¿Cómo se vota?", "unspecified"),
    ("¿Cómo se vota en Córdoba?", "unsupported"),
])
def test_unresolved_uses_real_router_without_backend(monkeypatch, question, status):
    retriever = Mock(side_effect=AssertionError("No retrieval"))
    chat = Mock(side_effect=AssertionError("No model"))
    monkeypatch.setattr(generar, "SemanticRetriever", retriever)
    monkeypatch.setattr(generar, "ChatOllama", chat)
    data = generar.answer_question(question)
    assert data["routing_status"] == status
    output = ui.consultar(question)
    assert data["answer"] in output[0]
    if data.get("clarification_question"):
        assert data["clarification_question"] in output[0]
    assert "Sin fuentes" in output[2] and output[3] == ""
    assert "No aplica" in output[4]
    retriever.assert_not_called()
    chat.assert_not_called()


@pytest.mark.parametrize("error", [
    recuperar.RetrievalIndexError("Falta índice"),
    recuperar.IndexConfigurationError("Firma incompatible"),
    generar.GeneratorUnavailableError("Falta modelo"),
    ConnectionError("Ollama no disponible"), ValueError("Índice corrupto"),
])
def test_runtime_errors_clear_outputs(monkeypatch, error):
    monkeypatch.setattr(generar, "answer_question", Mock(side_effect=error))
    output = ui.consultar("Pregunta")
    assert str(error) in output[0]
    assert "No se reconstruyó" in output[0]
    assert output[2:4] == ("", "")


def test_import_has_no_side_effects(monkeypatch):
    launch = Mock(side_effect=AssertionError("No server"))
    backend = Mock(side_effect=AssertionError("No query"))
    monkeypatch.setattr(ui.gr.Blocks, "launch", launch)
    monkeypatch.setattr(generar, "answer_question", backend)
    importlib.reload(ui)
    launch.assert_not_called()
    backend.assert_not_called()


def test_page_builds_and_launches_only_locally(monkeypatch):
    launch = Mock()
    backend = Mock(side_effect=AssertionError("No query while building"))
    monkeypatch.setattr(ui.gr.Blocks, "launch", launch)
    monkeypatch.setattr(generar, "answer_question", backend)
    ui.main()
    launch.assert_called_once_with(server_name="127.0.0.1", share=False)
    backend.assert_not_called()


def test_context_builder_relocated_exactly():
    assert generar.build_evidence_context is recuperar.build_evidence_context
    assert evaluar_recuperacion.build_evidence_context is recuperar.build_evidence_context
    records = [
        {"chunk_id": "a", "source_article_id": "art-a", "jurisdiccion": "pba",
         "ley": "5109", "articulo": "13", "source": "a.txt", "text": " Texto\ncompleto. "},
        {"chunk_id": "b", "source_article_id": "art-b", "jurisdiccion": "santa_fe",
         "ley": "14478", "articulo": "4", "source": "b.pdf", "text": "Otro\n\ntexto",
         "pagina_inicio": 1, "pagina_fin": 4},
    ]
    expected = ("[1]\nchunk_id: a\nsource_article_id: art-a\njurisdiccion: pba\n"
                "ley: 5109\narticulo: 13\nsource: a.txt\ntexto:\n Texto\ncompleto. \n\n"
                "[2]\nchunk_id: b\nsource_article_id: art-b\njurisdiccion: santa_fe\n"
                "ley: 14478\narticulo: 4\nsource: b.pdf\npaginas_articulo: 1–4\ntexto:\nOtro\n\ntexto")
    assert recuperar.build_evidence_context(records) == expected
    assert recuperar.build_evidence_context([]) == ""
