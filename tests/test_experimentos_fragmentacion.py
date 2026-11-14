"""Laboratorio aislado: contratos offline, sin embeddings ni puertos reales."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from importlib import import_module
from scripts import experimentos_fragmentacion as lab

ui = import_module("scripts.05_interfaz_gradio")


def result():
    """Fabrica una respuesta sin llamada al modelo para probar la presentación."""
    return {"answer": "Respuesta", "source_map": [], "context_sent": "Contexto literal\n" * 1000,
            "citation_check": None, "model_invoked": False}


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Aísla entradas e índices experimentales de los artefactos baseline."""
    inputs = tmp_path / "procesados"
    inputs.mkdir()
    for jurisdiction in lab.fragmentar.JURISDICTIONS:
        (inputs / f"{jurisdiction}_articulos.jsonl").write_text('{"texto":"artículo"}\n')
    baseline = inputs / "chunks.jsonl"
    baseline.write_text("baseline intacto")
    root = tmp_path / "experimentos"
    monkeypatch.setattr(lab, "INPUT_DIR", inputs)
    monkeypatch.setattr(lab, "EXPERIMENT_ROOT", root)
    return inputs, root, baseline


@pytest.mark.parametrize("size,overlap", [(299, 50), (2001, 0), (500, -1), (500, 500),
                                           (500, 501), (500.5, 80), (True, 0), (500, 1.5)])
def test_invalid_before_io(monkeypatch, size, overlap):
    read = Mock(side_effect=AssertionError("No I/O"))
    monkeypatch.setattr(Path, "read_bytes", read)
    with pytest.raises(ValueError):
        lab.prepare_experiment(size, overlap)
    read.assert_not_called()


def test_identity_content_parameters_and_code(workspace, monkeypatch):
    inputs, root, baseline = workspace
    first = lab.configuration(500, 80)
    assert first == lab.configuration(500, 80)
    assert first != lab.configuration(600, 80)
    assert first != lab.configuration(500, 90)
    assert Path(first["chunks_path"]).is_relative_to(root)
    (inputs / "pba_articulos.jsonl").write_text("otro contenido")
    assert first != lab.configuration(500, 80)
    changed = lab.configuration(500, 80)
    monkeypatch.setattr(lab, "version", lambda _: "otra versión")
    assert changed != lab.configuration(500, 80)
    assert not root.exists() and baseline.read_text() == "baseline intacto"


def test_model_change_creates_a_distinct_experiment_identity(workspace, monkeypatch):
    current = lab.configuration(500, 80)
    monkeypatch.setattr(lab.indexar, "DEFAULT_MODEL", "bge-m3")
    assert lab.configuration(500, 80) != current


def fake_pipeline(monkeypatch):
    """Intercepta fragmentación e indexación para verificar efectos sin I/O externo."""
    def split(inputs, target, **kwargs):
        target.parent.mkdir(parents=True)
        target.write_text("chunks experimentales")
        target.with_name("reporte_fragmentacion.json").write_text("{}")
    def index(chunks, directory, **kwargs):
        directory.mkdir()
    split_mock = Mock(side_effect=split)
    index_mock = Mock(side_effect=index)
    monkeypatch.setattr(lab.fragmentar, "build_chunks", split_mock)
    monkeypatch.setattr(lab.indexar, "run_index", index_mock)
    monkeypatch.setattr(lab.indexar, "read_chunks", Mock())
    monkeypatch.setattr(lab, "SemanticRetriever", Mock(return_value=SimpleNamespace(count=12)))
    return split_mock, index_mock


def test_prepare_isolation_and_reuse(workspace, monkeypatch):
    """Exige reutilización del mismo experimento sin tocar el índice original."""
    inputs, root, baseline = workspace
    before = {path: path.read_bytes() for path in inputs.iterdir()}
    split, index = fake_pipeline(monkeypatch)
    active, status = lab.prepare_experiment(1000, 150)
    assert "Listo" in status and "12 chunks" in status
    assert active["chunks_path"] != str(baseline)
    split.assert_called_once_with(inputs, Path(active["chunks_path"]), chunk_size=1000, chunk_overlap=150)
    index.assert_called_once_with(Path(active["chunks_path"]), Path(active["index_dir"]),
                                  model=lab.indexar.DEFAULT_MODEL, rebuild=False)
    again, status = lab.prepare_experiment(1000, 150)
    assert again == active and "Reutilizado" in status
    assert split.call_count == index.call_count == 1
    assert {path: path.read_bytes() for path in inputs.iterdir()} == before


def test_incompatible_existing_not_overwritten(workspace, monkeypatch):
    split, index = fake_pipeline(monkeypatch)
    active, _ = lab.prepare_experiment(500, 80)
    chunks = Path(active["chunks_path"])
    before = chunks.read_bytes()
    monkeypatch.setattr(lab, "SemanticRetriever", Mock(side_effect=ValueError("Firma incompatible")))
    with pytest.raises(ValueError, match="Firma incompatible"):
        lab.prepare_experiment(500, 80)
    assert chunks.read_bytes() == before and split.call_count == index.call_count == 1


def test_failed_index_can_retry_without_resplitting(workspace, monkeypatch):
    split, index = fake_pipeline(monkeypatch)
    index.side_effect = ConnectionError("Ollama no disponible")
    with pytest.raises(ConnectionError):
        lab.prepare_experiment(500, 80)
    index.side_effect = lambda chunks, directory, **kw: directory.mkdir()
    _, status = lab.prepare_experiment(500, 80)
    assert "Listo" in status and split.call_count == 1


def test_aborted_artifacts_fail_without_rewriting(workspace, monkeypatch):
    split, index = fake_pipeline(monkeypatch)
    active = lab.configuration(500, 80)
    directory = Path(active["index_dir"])
    directory.mkdir(parents=True)
    with pytest.raises(ValueError, match="sin chunks"):
        lab.prepare_experiment(500, 80)
    assert directory.exists()
    split.assert_not_called()
    index.assert_not_called()


def test_symlink_rejected(workspace, monkeypatch, tmp_path):
    split, index = fake_pipeline(monkeypatch)
    active = lab.configuration(500, 80)
    directory = Path(active["chunks_path"]).parent
    directory.parent.mkdir()
    elsewhere = tmp_path / "baseline"
    elsewhere.mkdir()
    directory.symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(ValueError, match="enlaces"):
        lab.prepare_experiment(500, 80)
    split.assert_not_called()
    index.assert_not_called()
    assert not list(elsewhere.iterdir())


def test_controls_only_clear_state_no_pipeline(monkeypatch):
    prepare = Mock(side_effect=AssertionError("Not clicked"))
    monkeypatch.setattr(ui, "prepare_experiment", prepare)
    for mode in (ui.ORIGINAL, ui.EXPERIMENTAL):
        cleared = ui.invalidate_configuration(mode)
        assert cleared[0] is None and cleared[2:] == ("",) * 5
    prepare.assert_not_called()


def test_prepare_status_and_visible_failure(monkeypatch):
    monkeypatch.setattr(ui, "prepare_experiment", Mock(side_effect=ConnectionError("Falta modelo")))
    updates = list(ui.preparar(ui.EXPERIMENTAL, 500, 80))
    assert "Construyendo" in updates[0][1]
    assert updates[-1][0] is None and "Falta modelo" in updates[-1][1]
    assert "baseline no se modificó" in updates[-1][1]
    assert updates[-1][2:] == ("",) * 5


@pytest.mark.parametrize("k", [1, 3, 5])
@pytest.mark.parametrize("jurisdiction,route", list(ui.ROUTING_OPTIONS.items()))
def test_experimental_routing_and_k(workspace, monkeypatch, k, jurisdiction, route):
    active = lab.configuration(500, 80)
    backend = Mock(return_value=result())
    monkeypatch.setattr(ui.generar, "answer_question", backend)
    ui.consultar("Pregunta", k, jurisdiction, ui.EXPERIMENTAL, 500, 80, active)
    backend.assert_called_once_with("Pregunta", k=k, **route,
                                    index_dir=Path(active["index_dir"]), chunks_path=Path(active["chunks_path"]))


def test_experimental_forwarding_and_unapplied_block(workspace, monkeypatch):
    active = lab.configuration(500, 80)
    backend = Mock(return_value=result())
    monkeypatch.setattr(ui.generar, "answer_question", backend)
    output = ui.consultar("Pregunta", 5, "Santa Fe", ui.EXPERIMENTAL, 500, 80, active)
    backend.assert_called_once_with("Pregunta", k=5, jurisdiccion="santa_fe",
                                    index_dir=Path(active["index_dir"]), chunks_path=Path(active["chunks_path"]))
    assert "500/80" in output[1] and output[3] == result()["context_sent"]
    backend.reset_mock()
    for state, size in ((None, 500), (active, 600)):
        output = ui.consultar("Pregunta", 3, "Automática", ui.EXPERIMENTAL, size, 80, state)
        assert "no preparada o modificada" in output[0]
    backend.assert_not_called()
    ui.consultar("Pregunta", active=active)  # volver al original no utiliza el experimental
    assert backend.call_args.kwargs["index_dir"] == ui.indexar.DEFAULT_INDEX
