"""Preprocesamiento conservador del corpus local; no determina vigencia jurídica."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

SOURCES = (
    ("nacional", "19945", "ley_nacional.txt"),
    ("pba", "5109", "ley_pba.txt"),
    ("santa_fe", "14478", "ley_sta_fe.pdf"),
)
ARTICLE = re.compile(
    r"^(?:art[íi]culo|art\.)\s+(?P<num>\d+[°º]?\s*(?:(?:bis|ter|qu[áa]ter|quinquies|sexies|septies|octies|nonies)\b)?|s/n)"
    r"\s*(?=[.\-:—–(])", re.I,
)
STRUCTURE = re.compile(r"^(LIBRO|T[ÍI]TULO|CAP[ÍI]TULO)\s+[IVXLCDM]+\.?$", re.I)
REFERENCE = re.compile(r"\b(?:ley(?:es)?|decreto(?:-ley)?)[ \t]+(?:nacional[ \t]+)?(?:N[°º.]*[ \t]*)?\d[\d./-]*", re.I)
EDITORIAL = re.compile(
    r"^(?:texto seg[úu]n|art[íi]culo (?:sustituido|incorporado|derogado)|"
    r"(?:inciso|p[áa]rrafo|segundo|[úu]ltimo|expresi[óo]n|t[íi]tulo|cap[íi]tulo)\b.*"
    r"(?:derogad|sustituid|incorporad|modificad)|vigencia:)", re.I,
)


def normalize(text: str) -> str:
    """Sólo espacios horizontales y extremos de línea; no corrige palabras ni guiones."""
    return "\n".join(re.sub(r"[^\S\n]+", " ", line).strip() for line in text.splitlines())


def load_source(path: Path):
    removed = []
    if path.suffix == ".pdf":
        from langchain_community.document_loaders import PyPDFLoader
        docs = PyPDFLoader(str(path)).load()
        pages = [d.page_content for d in docs]
        if not pages or any(not p.strip() for p in pages):
            raise ValueError(f"{path}: página vacía; revisar extracción antes de continuar")
    else:
        pages = [path.read_bytes().decode("utf-8")]
    lines = []
    for page, text in enumerate(pages, 1):
        for number, raw in enumerate(text.splitlines(), 1):
            clean = normalize(raw)
            # Sólo las dos primeras líneas: el loader trae aquí encabezado y pie.
            layout = path.suffix == ".pdf" and number <= 2 and (
                clean == "Texto original de la Ley N° 14478" or clean == f"Página {page}"
            )
            if layout:
                removed.append({"pagina": page, "linea_extraida": number, "texto": raw})
            else:
                lines.append((clean, page if path.suffix == ".pdf" else None))
    return lines, {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "caracteres_leidos": sum(map(len, pages)),
        "paginas_leidas": len(pages) if path.suffix == ".pdf" else None,
        "codificacion": "UTF-8" if path.suffix == ".txt" else "texto PDF directo (sin OCR)",
        "layout_eliminado": removed,
        "errores_extraccion": [],
    }


def annotations(text: str, *, amendment: bool = False):
    """Índices relativos a texto. Etiquetas describen marcas, no fuerza legal."""
    spans = []
    # Paréntesis balanceados, incluidos los de notas con paréntesis internos.
    stack = []
    for i, c in enumerate(text):
        if c == "(":
            stack.append(i)
        elif c == ")" and stack:
            start = stack.pop()
            if not stack and EDITORIAL.search(text[start + 1:i]):
                spans.append((start, i + 1, "nota_editorial"))
    for match in re.finditer(r"(?m)^(?:\([*#]\)|\*|#).+", text):
        end = match.end()
        # Transcripción anunciada: mantenerla unida a su nota introductoria.
        if "transcribe a continuación" in match.group():
            opening = text.find("“", end)
            closing = text.find("”", opening + 1) if opening >= 0 else -1
            if closing >= 0:
                end = closing + 1
        spans.append((match.start(), end, "nota_editorial"))
    for match in re.finditer(r"(?mi)^.*\bINCISO DEROGADO POR LEY[^\n]*", text):
        spans.append((match.start(), match.end(), "pasaje_marcado_derogado"))
    # Citas de artículos de otras normas introducidas por comillas, sin cambiar su texto.
    for match in re.finditer(r'(?mi)^[“«"](?:ART[ÍI]CULO|Art\.)\s+\d+', text):
        closing = {"“": "”", "«": "»", '"': '"'}[text[match.start()]]
        end = text.find(closing, match.end())
        if end >= 0:
            kind = "texto_modificatorio" if amendment else "transcripcion_citada"
            spans.append((match.start(), end + 1, kind))
    notes = []
    for start, end, kind in sorted(spans, key=lambda s: (s[0], -s[1])):
        if notes and start < notes[-1]["fin"]:
            continue
        passage = text[start:end]
        warning = None
        if re.search(r"observad|subrayad", passage, re.I):
            warning = "Revisar alcance de la observación; no se determina vigencia."
            if re.search(r"subrayad", passage, re.I):
                warning += " TXT no conserva subrayado: no puede aislarse el pasaje afectado."
        notes.append({"tipo": kind, "inicio": start, "fin": end, "texto": passage,
                      "advertencia": warning})
    principal = text
    for note in reversed(notes):
        # Las notas también localizan texto modificatorio sustantivo: éste no se resta.
        if note["tipo"] != "texto_modificatorio":
            principal = principal[:note["inicio"]] + principal[note["fin"]:]
    return notes, principal.strip()


def parse_lines(lines, jurisdiction: str, law: str, source: str):
    """Particiona cada línea sin descartar texto; conserva orden y rangos del flujo limpio."""
    stream = "\n".join(line for line, _ in lines)
    entries = []
    offset = 0
    quote_pair = None
    quote_depth = 0
    trailing = False
    for line, page in lines:
        kind, number = None, None
        if quote_pair is None:
            m = ARTICLE.match(line)
            # En este corpus las rúbricas empiezan en mayúscula; una remisión
            # envuelta como «artículo 172.» en p. 45 del PDF no es una rúbrica.
            if m and line[0].isupper() and not trailing:
                kind = "articulo"
                number = re.sub(r"\s+", " ", m["num"].replace("°", "").replace("º", "").strip()).lower()
            elif STRUCTURE.fullmatch(line) and not trailing:
                kind = "estructura"
            elif line.startswith("DADA EN LA SALA DE SESIONES"):
                kind, trailing = "no_clasificado", True
        if kind:
            entries.append({"tipo": kind, "inicio": offset, "articulo": number})
        # Sólo citas que empiezan en una línea: las comillas de palabras no cambian estado.
        if quote_pair is None and line.startswith(("“", "«", '"')):
            quote_pair = {"“": ("“", "”"), "«": ("«", "»"), '"': ('"', '"')}[line[0]]
        if quote_pair is not None:
            opening, closing = quote_pair
            if opening == closing:
                quote_depth = (quote_depth + line.count(opening)) % 2
            else:
                quote_depth += line.count(opening) - line.count(closing)
            if quote_depth <= 0:
                quote_pair, quote_depth = None, 0
        offset += len(line) + 1
    if not entries or entries[0]["inicio"]:
        entries.insert(0, {"tipo": "no_clasificado", "inicio": 0, "articulo": None})
    records, outside, warnings = [], [], []
    counts = Counter()
    context = {"libro": None, "titulo": None, "capitulo": None}
    for i, entry in enumerate(entries):
        start = entry["inicio"]
        end = entries[i + 1]["inicio"] if i + 1 < len(entries) else len(stream)
        text = stream[start:end].strip()
        # Las páginas se calculan sobre el texto no vacío, no sobre separadores.
        positions = []
        pos = 0
        for line, page in lines:
            if line and start <= pos < end:
                positions.append(page)
            pos += len(line) + 1
        location = {"inicio": start, "fin": end,
                    "pagina_inicio": positions[0] if positions else None,
                    "pagina_fin": positions[-1] if positions else None}
        if entry["tipo"] != "articulo":
            outside.append({"tipo": entry["tipo"], "texto": text, **location})
            if entry["tipo"] == "estructura":
                first = text.splitlines()[0].upper()
                key = "libro" if first.startswith("LIBRO") else "titulo" if first.startswith(("TÍTULO", "TITULO")) else "capitulo"
                context[key] = text
                if key == "libro":
                    context["titulo"] = context["capitulo"] = None
                elif key == "titulo":
                    context["capitulo"] = None
            continue
        number = entry["articulo"]
        counts[number] += 1
        slug = number.replace(" ", "_").replace("/", "_")
        rid = f"{jurisdiction}_{law}_art_{slug}"
        if counts[number] > 1:
            rid += f"__{counts[number]}"
            warnings.append({"id": rid, "motivo": f"Número duplicado {number}; conservado sin decidir precedencia."})
        # Casos verificados de la fuente, no inferencia de vigencia por comillas.
        amendment = (jurisdiction, law, source) == ("santa_fe", "14478", "ley_sta_fe.pdf") and number in {
            "285", "286", "287", "288", "289", "290",
        }
        notes, principal = annotations(text, amendment=amendment)
        refs = list(dict.fromkeys(m.group() for m in REFERENCE.finditer(text)))
        for note in notes:
            if note["advertencia"]:
                warnings.append({"id": rid, "motivo": note["advertencia"]})
        records.append({"id": rid, "jurisdiccion": jurisdiction, "ley": law,
                        "articulo": number, **context, "texto": text,
                        "texto_principal": principal, "notas": notes,
                        "referencias_externas": refs, "source": source, **location})
    if quote_pair is not None:
        warnings.append({"id": None, "motivo": "Cita sin cierre detectado; revisar límites preservados."})
    if any(s["tipo"] == "no_clasificado" and s["texto"] for s in outside):
        warnings.append({"id": None, "motivo": "Contenido no clasificado conservado íntegramente en segmentos_fuera_articulos."})
    # Control de conservación independiente de la cantidad de artículos esperada.
    segments = sorted([*records, *outside], key=lambda s: s["inicio"])
    compact = lambda s: re.sub(r"\s+", "", s)
    if compact("".join(s["texto"] for s in segments)) != compact(stream):
        raise ValueError(f"{source}: pérdida de contenido durante la partición")
    return records, {
        "caracteres_limpios": len(stream), "articulos": len(records),
        "numeros_duplicados": {n: c for n, c in counts.items() if c > 1},
        "cantidad_duplicados": sum(c - 1 for c in counts.values()),
        "anotaciones": sum(len(r["notas"]) for r in records),
        "referencias": sum(len(r["referencias_externas"]) for r in records),
        "advertencias": warnings, "segmentos_fuera_articulos": outside,
        "conservacion_contenido_no_blanco": True,
    }


def run(root: Path, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    report = {"version_esquema": 1, "fuentes": {}}
    for jurisdiction, law, filename in SOURCES:
        path = root / filename
        lines, audit = load_source(path)
        records, parsed = parse_lines(lines, jurisdiction, law, filename)
        audit.update(parsed)
        report["fuentes"][filename] = audit
        with (output / f"{jurisdiction}_articulos.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"{jurisdiction}: {len(records)} artículos; {len(audit['advertencias'])} advertencias")
    (output / "reporte_preprocesamiento.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=Path(__file__).parent / "datos")
    parser.add_argument("--salida", type=Path, default=Path(__file__).parent / "datos/procesados")
    args = parser.parse_args()
    run(args.entrada, args.salida)
