"""Deterministic, conservative routing rules for the three indexed jurisdictions.

Rules are intentionally corpus-specific; signals describe text matches, not legal advice.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

JURISDICCIONES = ("nacional", "pba", "santa_fe")


def normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


def _matches(text: str, phrases: tuple[str, ...]) -> list[str]:
    found = []
    for phrase in phrases:
        normalized = normalize(phrase)
        if re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", text):
            found.append(phrase)
    return found


# Alias y geografía para cada jurisdicción. Se usan para detectar la jurisdicción de la consulta.
ALIASES = {
    "nacional": ("codigo electoral nacional", "ley 19945", "ley 19 945", "ley nacional 19945", "ley n 19945", "ley n 19 945", "ley no 19945", "ley no 19 945", "ley nacional", "ley de la nacion", "legislacion nacional", "normativa nacional"),
    "pba": ("ley electoral bonaerense", "norma electoral bonaerense", "ley provincial bonaerense", "legislacion provincial bonaerense", "ley 5109", "ley 5 109", "ley n 5109", "ley n 5 109", "ley no 5109", "ley no 5 109", "ley bonaerense", "ley de pba"),
    "santa_fe": ("ley 14478", "ley 14 478", "ley n 14478", "ley n 14 478", "ley no 14478", "ley no 14 478", "codigo electoral de santa fe", "ley electoral de santa fe", "ley provincial santafesina", "legislacion provincial santafesina", "normativa provincial santafesina", "ley electoral santafesina", "ley provincial de santa fe", "legislacion provincial de santa fe", "ley santafesina", "ley de santa fe", "ley de la provincia de santa fe"),
}
GEOGRAPHY = {
    "nacional": ("argentina", "nacion", "nacional", "nacionales"),
    "pba": ("pba", "provincia de buenos aires", "provincia de buenos aires", "buenos aires", "bonaerense"),
    "santa_fe": ("santa fe", "provincia de santa fe", "santafesino", "santafesina", "santafesinos", "rosario"),
}
UNSUPPORTED = ("caba", "ciudad autonoma de buenos aires", "capital federal", "cordoba", "cordoba", "mendoza", "entre rios", "neuquen", "chubut", "tucuman", "salta", "jujuy", "san juan", "san luis", "la pampa", "rio negro", "misiones", "corrientes", "formosa", "chaco", "catamarca", "santiago del estero", "tierra del fuego")
COMPARE = ("comparar", "compara", "comparacion", "comparaciones", "diferencia", "diferencias", "distinguir", "distinguen", "se distinguen", "versus", " frente a ", "comparativamente")


def detect_jurisdiction(question: str) -> dict[str, Any]:
    """Return an auditable routing decision without I/O or model/index access."""
    if not isinstance(question, str):
        raise TypeError("question debe ser texto")
    text = normalize(question)
    padded = f" {text} "
    signals: dict[str, Any] = {"normalized_query": text, "law": [], "scope": [], "geography": [], "unsupported_geography": [], "comparison": []}
    law = {j: _matches(text, phrases) for j, phrases in ALIASES.items()}
    # A bare province name inside an alias is geography, not a named law.
    law["pba"] = [p for p in law["pba"] if p not in ("provincia de buenos aires",)]
    for j, hits in law.items():
        if hits:
            signals["law"].append({"jurisdiction": j, "matched_phrases": hits})
    geo = {j: _matches(text, phrases) for j, phrases in GEOGRAPHY.items()}
    for j, hits in geo.items():
        if hits:
            signals["geography"].append({"jurisdiction": j, "matched_phrases": sorted(set(hits))})
    unsupported = _matches(text, UNSUPPORTED)
    if unsupported:
        signals["unsupported_geography"] = unsupported
    compares = _matches(text, COMPARE)
    signals["comparison"] = compares

    presidential = _matches(text, ("presidente", "presidencial", "presidencia de la nacion", "presidente y vicepresidente"))
    national_legs = _matches(text, ("diputados nacionales", "senadores nacionales", "congreso nacional", "legisladores nacionales"))
    governor = _matches(text, ("gobernador", "gobernadora", "gobernacion"))
    provincial_legs = _matches(text, ("diputados provinciales", "legislatura provincial", "legislatura", "legisladores provinciales", "senadores provinciales", "elecciones legislativas provinciales", "eleccion legislativa provincial"))
    provincial_election = _matches(text, ("eleccion provincial", "elecciones provinciales", "comicios provinciales"))
    national_scope = _matches(text, ("eleccion nacional", "elecciones nacionales", "reglas nacionales", "normas nacionales", "legislacion nacional", "eleccion presidencial"))
    explicit_national = bool(presidential or national_legs or national_scope)
    signals["scope"] = ([{"jurisdiction": "nacional", "matched_phrases": presidential + national_legs + national_scope}] if explicit_national else [])

    explicit_laws = {j for j, hits in law.items() if hits}
    # Election of a provincial governor/legislature requires a supported province.
    if governor or provincial_legs or provincial_election:
        candidates = {j for j in ("pba", "santa_fe") if geo[j]}
        if len(candidates) == 1:
            j = next(iter(candidates))
            signals["scope"].append({"jurisdiction": j, "matched_phrases": governor + provincial_legs + provincial_election})
            explicit_laws.add(j)
        elif len(candidates) > 1:
            explicit_laws.update(candidates)
        elif len(explicit_laws) == 1:
            signals["scope"].append({"jurisdiction": next(iter(explicit_laws)), "matched_phrases": governor + provincial_legs + provincial_election})
        elif not explicit_national:
            return _decision("ambiguous", [], signals, "La consulta menciona una elección provincial, pero no indica de qué provincia.", "¿De qué provincia querés consultar la elección?")

    if compares:
        selected = [j for j in JURISDICCIONES if j in explicit_laws or geo[j] or (j == "nacional" and explicit_national)]
        if len(selected) >= 2 and not unsupported:
            return _decision("comparative", selected, signals, "Se detectó una comparación explícita entre jurisdicciones del corpus.", None)

    if unsupported:
        return _decision("unsupported", [], signals, "La jurisdicción mencionada no está cubierta por este corpus.", None)

    strong = set(explicit_laws)
    if explicit_national:
        strong.add("nacional")
    if len(strong) > 1:
        return _decision("ambiguous", [], signals, "La consulta combina señales normativas de jurisdicciones distintas.", "¿Qué jurisdicción querés priorizar, o querés comparar ambas?")
    if len(strong) == 1:
        chosen = next(iter(strong))
        return _decision("identified", [chosen], signals, f"La referencia normativa o el alcance electoral identifica {chosen}.", None)

    provincial_geo = {j for j in ("pba", "santa_fe") if geo[j]}
    if len(provincial_geo) > 1:
        return _decision("ambiguous", [], signals, "Se mencionan varias provincias sin una comparación normativa explícita.", "¿Qué jurisdicción querés consultar, o querés comparar ambas?")
    if provincial_geo:
        # General voting or voting obligation cannot identify which election's rules apply.
        return _decision("ambiguous", [], signals, "La provincia aparece como ubicación, pero no queda claro qué elección o legislación rige la consulta.", "¿Consultás por una elección nacional o por la elección provincial?")
    if geo["nacional"]:
        return _decision("ambiguous", [], signals, "La mención de Argentina o de un ámbito geográfico no determina por sí sola la norma aplicable.", "¿Te referís a una elección presidencial/nacional o a una elección provincial?")
    return _decision("unspecified", [], signals, "No se detectó una jurisdicción normativa suficiente.", "¿Sobre qué jurisdicción querés consultar: Nación, PBA o Santa Fe?")


def _decision(status: str, jurisdictions: list[str], signals: dict[str, Any], reason: str, clarification: str | None) -> dict[str, Any]:
    return {"status": status, "jurisdictions": jurisdictions, "signals": signals, "reason": reason,
            "clarification_question": clarification}
