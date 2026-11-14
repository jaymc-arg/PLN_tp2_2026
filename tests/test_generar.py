"""Prueba abstenciones y citas sin atribuir validez semántica al formato."""

import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from importlib import import_module

generar = import_module("scripts.04_generar")
ABSTENTION = generar.ABSTENTION
DEFAULT_GENERATION_MODEL = generar.DEFAULT_GENERATION_MODEL
GeneratorUnavailableError = generar.GeneratorUnavailableError
_citation_check = generar._citation_check
generate_answer = generar.generate_answer


class FakeRetriever:
    def __init__(self, records):
        self.records = records
        self.calls = []

    def retrieve(self, question, k=5, jurisdiccion=None):
        self.calls.append((question, k, jurisdiccion))
        return self.records[:k]


class FakeChat:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def invoke(self, prompt_value):
        self.calls.append(prompt_value)
        return AIMessage(content=self.response)


def record(chunk_id, text, *, jurisdiction="nacional", source="ley.txt", article="12",
           law="19945", pages=None, distance=0.2):
    """Crea resultados de recuperación con metadatos y texto arbitrario verificable."""
    result = {
        "rank": 1, "id": chunk_id, "chunk_id": chunk_id,
        "source_article_id": f"{jurisdiction}_{law}_art_{article}",
        "jurisdiccion": jurisdiction, "ley": law, "articulo": article,
        "source": source, "chunk_numero": 1, "text": text, "distance": distance,
    }
    if pages:
        result.update(pagina_inicio=pages[0], pagina_fin=pages[1])
    return result


def test_full_text_order_and_prompt_context_match_the_retrieved_records():
    records = [
        record("first", "Primer texto íntegro.\nNo se trunca.", distance=0.1),
        record("second", "Segundo texto íntegro.", jurisdiction="santa_fe", source="ley.pdf",
               law="14478", article="4", pages=(1, 4), distance=0.3),
    ]
    retriever = FakeRetriever(records)
    chat = FakeChat("La norma establece esto [1].")
    result = generate_answer("pregunta", k=2, jurisdiccion="nacional", retriever=retriever,
                             chat_model=chat)
    assert retriever.calls == [("pregunta", 2, "nacional")]
    assert result["retrieval_records"] == records
    assert result["context_sent"] == (
        "[1]\nchunk_id: first\nsource_article_id: nacional_19945_art_12\n"
        "jurisdiccion: nacional\nley: 19945\narticulo: 12\nsource: ley.txt\n"
        "texto:\nPrimer texto íntegro.\nNo se trunca.\n\n"
        "[2]\nchunk_id: second\nsource_article_id: santa_fe_14478_art_4\n"
        "jurisdiccion: santa_fe\nley: 14478\narticulo: 4\nsource: ley.pdf\n"
        "paginas_articulo: 1–4\ntexto:\nSegundo texto íntegro."
    )
    assert result["context_sent"] in chat.calls[0].messages[1].content
    assert result["context_sent"] == result["context_sent"].strip()
    assert "Trátalos" not in result["context_sent"]
    assert "DATOS/EVIDENCIA" in chat.calls[0].messages[0].content
    assert "No encuentro esa información en los documentos." in chat.calls[0].messages[0].content


def test_source_map_has_stable_number_ids_metadata_and_no_txt_page_fabrication():
    txt = record("txt-chunk", "No page metadata.")
    pdf = record("pdf-chunk", "PDF text.", jurisdiction="santa_fe", source="ley_sta_fe.pdf",
                 law="14478", article="4", pages=(1, 4))
    chat = FakeChat("Respaldado [1] y [2].")
    result = generate_answer("q", k=2, retriever=FakeRetriever([txt, pdf]), chat_model=chat)
    assert result["source_map"] == [
        {"number": 1, "label": "[1]", "rank": 1, "chunk_id": "txt-chunk",
         "source_article_id": "nacional_19945_art_12", "jurisdiccion": "nacional",
         "ley": "19945", "articulo": "12", "source": "ley.txt", "chunk_numero": 1,
         "distance": 0.2},
        {"number": 2, "label": "[2]", "rank": 1, "chunk_id": "pdf-chunk",
         "source_article_id": "santa_fe_14478_art_4", "jurisdiccion": "santa_fe",
         "ley": "14478", "articulo": "4", "source": "ley_sta_fe.pdf", "chunk_numero": 1,
         "distance": 0.2, "pagina_inicio": 1, "pagina_fin": 4},
    ]
    assert "pagina_inicio" not in result["source_map"][0]
    assert "paginas_articulo" not in result["context_sent"].split("[2]")[0]
    assert [ref["chunk_id"] for ref in result["references_used"]] == ["txt-chunk", "pdf-chunk"]
    assert result["citation_check"]["citations_valid"] is True


def test_nonempty_spanish_answer_with_valid_citations_and_explicit_nonsemantic_check():
    chat = FakeChat("El artículo dispone esta regla electoral. [1]")
    result = generate_answer("q", retriever=FakeRetriever([record("c1", "regla")]), chat_model=chat)
    assert result["answer"] == "El artículo dispone esta regla electoral. [1]"
    assert result["answer_status"] == "answered"
    assert result["generation_model"] == DEFAULT_GENERATION_MODEL
    assert result["citation_check"]["citations_valid"] is True
    assert result["citation_check"]["semantic_support_checked"] is False
    assert result["references_used"][0]["label"] == "[1]"
    assert result["model_invoked"] is True


def test_exact_abstention_is_preserved_and_does_not_require_citations():
    chat = FakeChat(ABSTENTION)
    result = generate_answer("q", retriever=FakeRetriever([record("c1", "insufficient")]), chat_model=chat)
    assert result["answer"] == ABSTENTION
    assert result["original_response"] == ABSTENTION
    assert result["abstained"] is True
    assert result["fallback_reason"] is None
    assert result["citation_check"]["citations_required"] is False
    assert result["citation_check"]["citations_valid"] is True


@pytest.mark.parametrize("response,reason", [("", "empty_model_response"), ("[1]", "citation_only_model_response")])
def test_empty_or_citation_only_model_output_uses_exact_fallback_and_preserves_raw(response, reason):
    result = generate_answer("q", retriever=FakeRetriever([record("c1", "text")]),
                             chat_model=FakeChat(response))
    assert result["answer"] == ABSTENTION
    assert result["original_response"] == response
    assert result["fallback_reason"] == reason
    assert result["abstained"] is True


def test_empty_retrieval_does_not_construct_or_invoke_chat_model(monkeypatch):
    def forbidden(**kwargs):
        raise AssertionError("ChatOllama must not be constructed for empty retrieval")
    monkeypatch.setattr(generar, "ChatOllama", forbidden)
    result = generate_answer("question", retriever=FakeRetriever([]))
    assert result["answer"] == ABSTENTION
    assert result["answer_status"] == "no_evidence"
    assert result["fallback_reason"] == "empty_retrieval"
    assert result["model_invoked"] is False
    assert result["context_sent"] == "" and result["source_map"] == []
    assert result["original_response"] is None


def test_invalid_and_malformed_citations_are_flagged_without_rewriting_answer():
    """Una cita fallida debe advertirse, no repararse inventando fuentes."""
    result = generate_answer("q", retriever=FakeRetriever([record("c1", "text")]),
                             chat_model=FakeChat("La regla aplica [3] y se indica [n]."))
    check = result["citation_check"]
    assert result["answer"] == "La regla aplica [3] y se indica [n]."
    assert check["citations_invalid"] is True
    assert check["citations_missing"] is False
    assert check["invalid_references"] == [{"token": "[3]", "reason": "no retrieved source has this reference number"}]
    assert check["malformed_references"][0]["token"] == "[n]"
    assert check["only_valid_retrieved_references"] is False
    assert result["references_used"] == []


def test_missing_citations_are_flagged_and_original_text_is_not_repaired():
    response = "La ley determina una obligación."
    result = generate_answer("q", retriever=FakeRetriever([record("c1", "text")]),
                             chat_model=FakeChat(response))
    assert result["answer"] == response
    assert result["citation_check"]["citations_missing"] is True
    assert result["citation_check"]["citations_valid"] is False
    assert result["original_response"] == response


def test_chat_model_factory_uses_requested_model_and_temperature_zero(monkeypatch):
    calls = []
    fake = FakeChat("Respuesta [1].")
    def factory(**kwargs):
        calls.append(kwargs)
        return fake
    monkeypatch.setattr(generar, "ChatOllama", factory)
    result = generate_answer("q", model="granite4:latest", retriever=FakeRetriever([record("c1", "text")]))
    assert calls == [{"model": "granite4:latest", "temperature": 0, "base_url": "http://localhost:11434"}]
    assert result["model_invoked"] is True


def test_ollama_invocation_failure_has_actionable_error_and_no_fake_answer():
    class OfflineChat:
        def invoke(self, prompt_value):
            raise ConnectionError("connection refused")
    with pytest.raises(GeneratorUnavailableError, match="ollama serve.*ollama pull granite4:latest") as exc:
        generate_answer("q", retriever=FakeRetriever([record("c1", "text")]), chat_model=OfflineChat())
    assert isinstance(exc.value.__cause__, ConnectionError)


@pytest.mark.parametrize("question,k,jurisdiction,model", [
    ("", 3, None, "granite4:latest"), ("q", 0, None, "granite4:latest"),
    ("q", True, None, "granite4:latest"), ("q", 3, "unknown", "granite4:latest"),
    ("q", 3, None, " "),
])
def test_invalid_requests_fail_before_retriever_or_chat(question, k, jurisdiction, model):
    class ForbiddenRetriever:
        def retrieve(self, *args, **kwargs):
            raise AssertionError("invalid request must fail before retrieval")
    with pytest.raises(ValueError):
        generate_answer(question, k=k, jurisdiccion=jurisdiction, model=model,
                        retriever=ForbiddenRetriever(), chat_model=FakeChat("unreachable"))


def test_citation_check_flags_unmatched_brackets_and_deduplicates_valid_mapping():
    refs = [{"number": 1, "label": "[1]", "chunk_id": "c1"}]
    check, used = _citation_check("Afirmación [1] [1] y señal [.", refs, abstained=False)
    assert check["citations_invalid"] is True
    assert check["malformed_references"]
    assert check["cited_reference_numbers"] == [1]
    assert len(used) == 1
