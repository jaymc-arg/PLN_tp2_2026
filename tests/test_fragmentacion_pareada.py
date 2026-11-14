"""Contratos offline del ensayo; no son medidas de desempeño del modelo."""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import Mock

from langchain_core.messages import AIMessage
import pytest

from scripts import evaluar_fragmentacion_pareada as paired


def row(article, jurisdiction, rank=1):
    return {"chunk_id": f"{article}-{rank}", "source_article_id": article,
            "rank": rank, "jurisdiccion": jurisdiction, "source": "test.txt",
            "articulo": "1", "ley": "test", "text": f"Evidencia literal de {article}", "distance": 0.1}


def test_frozen_fixture_and_reject_changed_bytes_before_queries(tmp_path):
    questions = paired.validate_fixture()
    assert len(questions) == 38 and sum(q["respondible"] for q in questions) == 32
    assert sum(bool(q.get("jurisdicciones")) for q in questions) == 2
    changed = tmp_path / "fixture.json"
    changed.write_bytes(paired.FIXTURE.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="SHA-256"):
        paired.validate_fixture(changed)


def test_comparison_requires_both_articles_and_deduplicates_for_recall():
    groups = [{"jurisdiccion": "nacional", "results": [row("a", "nacional"), row("a", "nacional", 2)]},
              {"jurisdiccion": "santa_fe", "results": [row("other", "santa_fe"), row("other", "santa_fe", 2), row("other", "santa_fe", 3), row("b", "santa_fe", 4)]}]
    result = paired.article_metrics(groups, ["a", "b"])
    assert not result["hit_at_1"] and not result["hit_at_3"] and result["hit_at_5"]
    assert result["expected_article_recall_at_3"] == 0.5
    assert result["first_complete_rank"] == 4 and result["reciprocal_rank_at_5"] == 0.25
    groups[1]["results"].pop()
    assert paired.article_metrics(groups, ["a", "b"])["reciprocal_rank_at_5"] == 0
    assert paired.article_metrics(groups, [])['expected_article_recall_at_5'] is None


def test_denominators_positive_vs_negative_and_comparison_not_double_counted():
    cases = [{"fixture": {"respondible": True, "fuentes_esperadas": ["a"]}, "article_metrics": {"hit_at_1": True, "hit_at_3": True, "hit_at_5": True, "reciprocal_rank_at_5": 1, "first_rank_per_article": {"a": 1}},
              "review": {"answer_label": "supported", "passage_coverage_k3": "full"}},
             {"fixture": {"respondible": True, "fuentes_esperadas": ["b", "c"]}, "article_metrics": {"hit_at_5": True, "reciprocal_rank_at_5": 0.25, "first_rank_per_article": {"b": 1, "c": 4}},
              "review": {"answer_label": "abstained_incorrectly", "passage_coverage_k3": "none"}},
             {"fixture": {"respondible": False}, "review": {"answer_label": "abstained_correctly", "unsupported_factual_answer": False}},
             {"fixture": {"respondible": False}, "review": {"answer_label": "unsupported", "unsupported_factual_answer": True}}]
    metrics = paired.aggregate(cases)
    assert metrics['hit_at_1'] == {'count': 1, 'denominator': 2, 'rate': 0.5}
    assert metrics['mrr_at_5']['rate'] == 0.625
    assert metrics['correct_abstention'] == {'count': 1, 'denominator': 2, 'rate': 0.5}
    assert metrics['unsupported_negative_answer']['rate'] == 0.5
    assert metrics['expected_article_recall_at_1'] == {'count': 2, 'denominator': 3, 'rate': 2 / 3}
    assert metrics['both_articles_at_3'] == {'count': 0, 'denominator': 1, 'rate': 0.0}
    assert metrics['both_articles_at_5'] == {'count': 1, 'denominator': 1, 'rate': 1.0}


def test_generic_negative_nonanswer_is_not_automatically_a_factual_hallucination():
    case = {"fixture": {"respondible": False},
            "review": {"answer_label": "partially_supported", "unsupported_factual_answer": False}}
    result = paired.aggregate([case])
    assert result['correct_abstention']['count'] == 0
    assert result['unsupported_negative_answer']['count'] == 0
    assert result['generic_negative_nonanswer']['count'] == 1


def test_explicit_comparison_uses_exact_cached_top3_with_global_citations():
    question = next(q for q in paired.validate_fixture() if q['id'] == 'comparativa_nacional_santa_fe_bup')
    # El detector sin override es ambiguo: no se altera ni se cambia la pregunta.
    assert paired.generar.detect_jurisdiction(question['pregunta'])['status'] == 'ambiguous'
    groups = [{"jurisdiccion": j, "results": [row(article, j, i) for i in range(1, 6)]}
              for j, article in zip(question['jurisdicciones'], question['fuentes_esperadas'])]
    before = deepcopy(groups)
    chat = SimpleNamespace(invoke=Mock(return_value=AIMessage(content='Respuesta [1] [4].')))
    result = paired.generation_from_ranking(question, groups, chat_model=chat)
    assert groups == before
    assert result['model_invoked'] and result['jurisdiction_source'] == 'manual'
    assert result['routing_status'] == 'comparative'
    assert len(result['source_map']) == 6
    assert [x['number'] for x in result['source_map']] == list(range(1, 7))
    assert result['context_sent'] == paired.recuperar.build_evidence_context(result['retrieval_records'])
    assert chat.invoke.call_count == 1


@pytest.mark.parametrize('kwargs', [
    {'jurisdicciones': ['nacional']}, {'jurisdicciones': ['nacional', 'nacional']},
    {'jurisdicciones': ['nacional', 'unknown']},
    {'jurisdicciones': ['nacional', 'pba'], 'sin_filtro': True},
    {'jurisdicciones': ['nacional', 'pba'], 'jurisdiccion': 'pba'},
])
def test_invalid_explicit_comparisons_do_not_query(kwargs):
    retriever = SimpleNamespace(retrieve=Mock(side_effect=AssertionError('No query')))
    with pytest.raises(ValueError):
        paired.generar.answer_question('Pregunta', retriever=retriever, **kwargs)
    retriever.retrieve.assert_not_called()


def test_unscoped_negative_is_unfiltered_not_a_clarification(monkeypatch):
    q = next(q for q in paired.validate_fixture() if q['id'] == 'ausente_escuela_asignada')
    spy = Mock(return_value={})
    monkeypatch.setattr(paired.generar, 'answer_question', spy)
    paired.generation_from_ranking(q, [{'jurisdiccion': None, 'results': []}])
    assert spy.call_args.kwargs['sin_filtro'] is True
    assert 'jurisdiccion' not in spy.call_args.kwargs


def test_safe_resume_only_missing_ids_complete_reuse_and_corrupt_rejection(tmp_path, monkeypatch):
    chunks = [{'id': f'a{i}', 'texto': f'texto {i}', 'source_article_id': f'a{i}',
               'jurisdiccion': 'nacional', 'ley': '1', 'articulo': str(i), 'source': 'a.txt',
               'chunk_numero': 1} for i in (1, 2)]
    chunks_path = tmp_path / 'chunks.jsonl'
    chunks_path.write_text(''.join(json.dumps(c) + '\n' for c in chunks))
    index_dir = tmp_path / 'index'; index_dir.mkdir()
    signature = paired.indexar.make_signature(paired.digest(chunks_path), paired.indexar.DEFAULT_MODEL)
    manifest = index_dir / paired.indexar.MANIFEST; manifest.write_text(json.dumps(signature))
    before_manifest = manifest.read_bytes()
    expected = {c['id']: (c['texto'], paired.indexar.chunk_metadata(c)) for c in chunks}
    state = {'a1': expected['a1']}
    kept = state['a1']
    def get(*, include, limit=None):
        ids = list(state)[:limit]
        return {'ids': ids, 'documents': [state[i][0] for i in ids],
                'metadatas': [state[i][1] for i in ids], 'embeddings': [[0.1, 0.2] for _ in ids]}
    store = SimpleNamespace(get=get, _collection=SimpleNamespace(configuration={'hnsw': {'space': 'l2'}}))
    monkeypatch.setattr(paired.recuperar, 'Chroma', lambda **kw: store)
    monkeypatch.setattr(paired.recuperar, 'SemanticRetriever', lambda **kw: SimpleNamespace(store=store, count=len(state)))
    written = []
    def resume(*args, **kwargs):
        assert kwargs['rebuild'] is False
        for i, record in expected.items():
            if i not in state:
                state[i] = record; written.append(i)
    index = Mock(side_effect=resume)
    monkeypatch.setattr(paired.indexar, 'run_index', index)
    with pytest.raises(ValueError, match='baseline'):
        paired.verify_or_resume(chunks_path, index_dir)
    assert index.call_count == 0
    _, metadata = paired.verify_or_resume(chunks_path, index_dir, allow_resume=True)
    assert written == ['a2'] and state['a1'] is kept and metadata['missing_ids_completed'] == 1
    paired.verify_or_resume(chunks_path, index_dir, allow_resume=True)
    assert index.call_count == 1 and manifest.read_bytes() == before_manifest
    state['a1'] = ('corrupt', kept[1])
    with pytest.raises(ValueError, match='incompatibles'):
        paired.verify_or_resume(chunks_path, index_dir, allow_resume=True)
    assert index.call_count == 1 and manifest.read_bytes() == before_manifest


def test_paired_passage_score_independent_of_uncertain_response_label():
    base = {'id': 'q', 'fixture': {'respondible': True},
            'article_metrics': {'hit_at_3': True},
            'review': {'passage_coverage_k3': 'full', 'answer_label': 'needs_review'}}
    challenger = deepcopy(base)
    challenger['review']['answer_label'] = 'supported'
    result = paired.paired_outcomes({'1000_150': {'cases': [base]}, '600_80': {'cases': [challenger]}})
    assert result['passage_k3']['ties'] == ['q']
    assert result['supported_answer']['needs_review'] == ['q']
    assert result['correct_negative_abstention']['ties'] == []


def test_review_checks_actual_context_and_response_hash():
    import hashlib
    c = {'id': 'q', 'fixture': {'respondible': True}, 'generation': {'original_response': 'A [1]', 'retrieval_records': [row('a', 'nacional')]}}
    report = {'cases': [c]}
    review = {'q': {'answer_label': 'supported', 'passage_coverage_k3': 'full',
                    'factual_correctness': 'full', 'citation_support': 'full',
                    'original_response_sha256': hashlib.sha256(b'A [1]').hexdigest(),
                    'evidence': [{'chunk_id': 'a-1', 'quote': 'literal de a'}],
                    'reviewer': 'coding-agent inspection, not independent legal verification',
                    'justification': 'Prueba sintética.'}}
    paired.apply_review(report, review)
    review['q']['evidence'][0]['quote'] = 'invented'
    with pytest.raises(ValueError, match='contexto'):
        paired.apply_review(report, review)
