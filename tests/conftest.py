"""Datos sintéticos temporales para contratos de los evaluadores históricos.

No son una copia histórica de preguntas.json ni evidencia del ensayo de 38 casos.
"""
import json

import pytest


@pytest.fixture
def five_case_protocol_fixture(tmp_path):
    questions = []
    for i in range(5):
        questions.append({
            "id": "nacional_respondible_deber_votar" if i == 0 else f"synthetic_{i}",
            "respondible": i < 3,
            "jurisdiccion": "nacional" if i < 3 else None,
            "pregunta": f"Pregunta sintética de contrato {i}",
            "fuentes_esperadas": ["nacional_19945_art_12"] if i < 3 else [],
            "respuesta_referencia": "Referencia sintética; no usar como resultado real.",
        })
    path = tmp_path / "synthetic-contract-fixture.json"
    path.write_text(json.dumps({"preguntas": questions}), encoding="utf-8")
    return path
