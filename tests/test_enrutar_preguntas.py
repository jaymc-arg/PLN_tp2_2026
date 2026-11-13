import pytest
from langchain_core.messages import AIMessage

from importlib import import_module

generator_module = import_module("scripts.04_generar")
answer_question = generator_module.answer_question
generate_answer = generator_module.generate_answer


def row(jurisdiction, idx):
    law = {"nacional": "19945", "pba": "5109", "santa_fe": "14478"}[jurisdiction]
    article = {"nacional": "12", "pba": "13", "santa_fe": "4"}[jurisdiction]
    result = {"rank": idx, "chunk_id": f"{jurisdiction}-{idx}", "source_article_id": f"{jurisdiction}_{law}_art_{article}",
              "jurisdiccion": jurisdiction, "ley": law, "articulo": article,
              "source": f"{jurisdiction}.txt", "chunk_numero": idx, "text": f"Texto completo {jurisdiction} {idx}.", "distance": 0.2}
    if jurisdiction == "santa_fe":
        result.update(pagina_inicio=21, pagina_fin=22)
    return result


class FakeRetriever:
    def __init__(self):
        self.calls = []

    def retrieve(self, question, k=5, jurisdiccion=None):
        self.calls.append((question, k, jurisdiccion))
        j = jurisdiccion or "nacional"
        return [row(j, n) for n in range(1, k + 1)]


class FakeChat:
    def __init__(self, content="Respuesta comparativa [1] [2]."):
        self.content = content
        self.calls = []

    def invoke(self, prompt):
        self.calls.append(prompt)
        return AIMessage(content=self.content)


@pytest.mark.parametrize("q,j", [("¿Qué fija la Ley 5.109?", "pba"), ("¿Cómo define la Ley 14.478 la mesa?", "santa_fe"),
                                  ("¿Qué dispone el Código Electoral Nacional?", "nacional")])
def test_identified_route_filters_once(q, j):
    retriever, chat = FakeRetriever(), FakeChat("La norma establece esto [1].")
    result = answer_question(q, k=1, retriever=retriever, chat_model=chat)
    assert retriever.calls == [(q, 1, j)]
    assert result["jurisdiction_source"] == "automatic"
    assert result["applied_filter"] == j
    assert result["model_invoked"] is True


@pytest.mark.parametrize("q,status", [("¿Cómo se vota en PBA?", "ambiguous"), ("¿A qué hora se vota?", "unspecified"),
                                       ("¿Cómo se vota en CABA?", "unsupported")])
def test_unresolved_route_does_not_retrieve_or_invoke_model(q, status):
    class Forbidden:
        def retrieve(self, *args, **kwargs):
            raise AssertionError("must not retrieve")
    class ForbiddenChat:
        def invoke(self, *_):
            raise AssertionError("must not invoke model")
    result = answer_question(q, retriever=Forbidden(), chat_model=ForbiddenChat())
    assert result["routing_status"] == status
    assert result["retrieval_records"] == []
    assert result["model_invoked"] is False
    assert result["answer_status"] != "no_evidence"


def test_manual_override_wins_and_invalid_or_conflicting_options_fail_before_retrieval():
    q = "¿Cómo se vota presidente en PBA?"
    retriever, chat = FakeRetriever(), FakeChat("Respuesta [1].")
    result = answer_question(q, jurisdiccion="pba", retriever=retriever, chat_model=chat)
    assert retriever.calls == [(q, 3, "pba")]
    assert result["jurisdiction_source"] == "manual" and result["jurisdictions"] == ["pba"]
    with pytest.raises(ValueError, match="jurisdiccion"):
        answer_question(q, jurisdiccion="caba", retriever=FakeRetriever())
    with pytest.raises(ValueError, match="incompatibles"):
        answer_question(q, jurisdiccion="pba", sin_filtro=True, retriever=FakeRetriever())


def test_unfiltered_opt_out_preserves_exploratory_path_and_is_labeled():
    q = "¿Cómo se vota en PBA?"
    retriever, chat = FakeRetriever(), FakeChat("Respuesta [1].")
    result = answer_question(q, sin_filtro=True, retriever=retriever, chat_model=chat)
    assert retriever.calls == [(q, 3, None)]
    assert result["routing_status"] == "unfiltered"
    assert result["jurisdiction_source"] == "unfiltered"
    assert result["applied_filter"] is None


def test_comparison_runs_independent_top_k_queries_and_reuses_exact_evidence_with_valid_citations():
    q = "¿Qué diferencias hay entre la Ley 5.109 y la Ley 14.478?"
    retriever, chat = FakeRetriever(), FakeChat()
    result = answer_question(q, k=2, retriever=retriever, chat_model=chat)
    assert retriever.calls == [(q, 2, "pba"), (q, 2, "santa_fe")]
    assert len(result["retrieval_records"]) == 4
    assert [r["chunk_id"] for r in result["retrieval_records"]] == ["pba-1", "pba-2", "santa_fe-1", "santa_fe-2"]
    assert [m["number"] for m in result["source_map"]] == [1, 2, 3, 4]
    assert "Texto completo pba 1." in result["context_sent"] and "Texto completo santa_fe 2." in result["context_sent"]
    assert result["citation_check"]["citations_valid"] is True
    assert result["source_map"][0]["number"] == 1 and "pagina_inicio" not in result["source_map"][0]
    assert result["source_map"][2]["number"] == 3
    assert result["source_map"][2]["pagina_inicio"] == 21 and result["source_map"][2]["pagina_fin"] == 22
    assert "paginas_articulo: 21–22" in result["context_sent"]
    assert result["per_jurisdiction_retrievals"]["pba"][0]["distance"] == 0.2
    assert result["applied_filter"] == ["pba", "santa_fe"]


def test_comparative_duplicate_source_ids_are_rejected():
    class Duplicating(FakeRetriever):
        def retrieve(self, question, k=5, jurisdiccion=None):
            self.calls.append((question, k, jurisdiccion))
            return [row("pba", 1)]
    with pytest.raises(ValueError, match="IDs duplicados"):
        answer_question("Comparar la Ley 5.109 con la Ley 14.478", retriever=Duplicating(), chat_model=FakeChat())


def test_answer_question_does_not_call_deprecated_generator(monkeypatch):
    generator_module = import_module("scripts.04_generar")
    def forbidden(*args, **kwargs):
        raise AssertionError("new routed flow must not use deprecated generate_answer")
    monkeypatch.setattr(generator_module, "generate_answer", forbidden)
    q = "¿Qué establece el Código Electoral Nacional sobre el voto?"
    result = answer_question(q, retriever=FakeRetriever(), chat_model=FakeChat("Respuesta [1]."))
    assert result["routing_status"] == "identified"
    assert result["model_invoked"] is True


def test_legacy_generate_answer_is_deprecated_and_explicitly_bypasses_routing():
    q = "¿Cómo se vota en PBA?"
    retriever, chat = FakeRetriever(), FakeChat("Respuesta [1].")
    with pytest.warns(DeprecationWarning, match="use answer_question"):
        result = generate_answer(q, retriever=retriever, chat_model=chat)
    assert retriever.calls == [(q, 3, None)]
    assert result["routing_status"] == "deprecated_bypass"
