# PLN_tp2_2026 — preprocesamiento del corpus electoral

**Uso:** un estudiante de legislación electoral necesita localizar y comparar disposiciones de Argentina, Buenos Aires y Santa Fe con su procedencia, para preparar consultas documentales verificables (no asesoramiento jurídico).

## Corpus y procedencia

Los originales se mantienen **sin mover ni modificar** en `datos/`:

| Archivo | Norma | Comprobación realizada por el agente |
|---|---|---|
| `ley_nacional.txt` | Código Electoral Nacional, Ley 19.945 | UTF-8; art. 12 completo y sus excepciones cotejados con el TXT |
| `ley_pba.txt` | Ley 5.109 | UTF-8; arts. 2, 3 y 13 cotejados con el TXT; incluye notas editoriales y numeración duplicada |
| `ley_sta_fe.pdf` | Ley 14.478 | 70 páginas con texto directo, sin OCR; página 1 renderizada y cotejada visualmente, definición del art. 4 seguida hasta p. 4 |

`datos/fuentes.csv` registra lo comprobable dentro de cada archivo y una pregunta respondible por documento. **URL oficial, fecha de descarga y permiso de redistribución no están verificados**: se señalan como desconocidos. Deben verificarse antes de publicar el corpus; esta etapa no acredita autenticidad externa, vigencia ni cumplimiento del requisito final de redistribución. El TXT nacional ya había sido recortado manualmente por el usuario; el programa no elimina otra introducción.

## Instalación y ejecución local

Requiere Python **3.12** y `uv` (verificación realizada con uv 0.5.4). Desde la raíz:

```bash
uv sync
uv run python preprocesar.py
uv run python fragmentar.py
uv run pytest -q
uv run python preprocesar.py
```

La última ejecución permite comparar los archivos; la prueba de determinismo también genera una segunda salida y compara sus bytes, incluido el reporte. No hay marcas de tiempo volátiles ni llamadas a servicios externos durante el procesamiento. `uv.lock` fija las dependencias; `requirements.txt` incluye ejecución y pruebas y se exporta con:

```bash
uv export --format requirements-txt --no-hashes --output-file requirements.txt
```

Alternativa de rutas, sin modificar los originales:

```bash
uv run python preprocesar.py --entrada datos --salida /tmp/tp2-procesados
```

El PDF se extrae con `langchain-community` / `PyPDFLoader` y `pypdf`; los TXT se decodifican como UTF-8 estricto. Las versiones exactas están en el lock y en `requirements.txt`. Un archivo ausente, UTF-8 inválido o página PDF sin texto detiene la ejecución: no se sustituye ni se aplica OCR automáticamente.

## Proceso y salidas

`originales locales → lectura → limpieza de espacios/layout → artículos y anotaciones → JSONL + auditoría`

- `preprocesar.py`: procesador y CLI; `tests/test_preprocesar.py`: fixtures sintéticos y corpus real.
- `datos/procesados/{nacional,pba,santa_fe}_articulos.jsonl`: un registro por artículo en orden de aparición.
- `datos/procesados/chunks.jsonl`: vista recuperable por artículo, dividida con `RecursiveCharacterTextSplitter` (1000 caracteres, solapamiento 150); ejecutable por separado con `uv run python fragmentar.py`.
- `datos/procesados/reporte_fragmentacion.json`: conteos y longitudes observadas de chunks.
- `datos/procesados/reporte_preprocesamiento.json`: SHA-256 originales, caracteres leídos/limpios, páginas, conteos, duplicados, notas, referencias, advertencias y contenido fuera de artículos.
- `evalucacion/validacion_preprocesamiento.md`: cotejos y limitaciones de esta etapa, **no** evaluación de respuestas RAG.

### Esquema y fidelidad

Cada registro contiene `id`, `jurisdiccion`, `ley`, `articulo`, `libro`, `titulo`, `capitulo`, `texto`, `notas`, `referencias_externas`, `pagina_inicio`, `pagina_fin` y `source` (nombre original). Las rúbricas estructurales completas se guardan como contexto. Las páginas PDF son originales, **1-based**; para TXT son `null`.

Ampliaciones al esquema solicitado:

- `texto` conserva íntegramente el artículo, incluida su rúbrica y las notas; no equivale a «norma vigente».
- `texto_principal` omite los pasajes editoriales anotados, pero conserva los de tipo `texto_modificatorio`: en Santa Fe 285–290, la cita es el reemplazo dispuesto por el propio artículo y también queda localizada en `notas`. Es una vista auxiliar, **no una consolidación jurídica**. No debe enviarse solo al futuro RAG cuando haya advertencias.
- Cada nota guarda `tipo`, `texto`, offsets relativos `inicio`/`fin` y eventual `advertencia`. Se distinguen marcas editoriales, pasajes marcados como derogados y transcripciones citadas; no se decide su fuerza legal.
- Los offsets de cada registro y segmento fuera de artículos son intervalos `[inicio, fin)` en el flujo de texto limpio, **no offsets del archivo original**. `texto` elimina espacios externos del intervalo.
- IDs como `pba_5109_art_151__2` conservan ocurrencias repetidas; `s/n` y sufijos latinos se mantienen sin renumerar.
- Prefacios, rúbricas, firmas y decreto final santafesino quedan íntegros en `segmentos_fuera_articulos` del reporte, con ubicación y tipo. No se descartan ni se incluyen como artículos ficticios.

Se colapsan espacios horizontales y se limpian extremos de línea. Sólo se quitan el encabezado repetitivo y la marca de página en las dos primeras líneas extraídas del PDF; cada eliminación queda registrada con texto original y página en `layout_eliminado`. Se conservan saltos de línea y guiones: no se adivinan reparaciones ni se corrigen erratas. Cada carácter no blanco extraído debe aparecer en la partición artículo/estructura/no clasificado; el código y las pruebas comprueban esa conservación.

## Validaciones y límites

Resultado actual: **208 artículos nacionales, 155 bonaerenses y 296 santafesinos**. Advertencias: **1 / 4 / 1**, respectivamente; detalle en el reporte. Las pruebas cubren campos y JSONL, IDs, orden, conservación, páginas, artículos multipágina, `bis`/otros sufijos, referencias internas, citas, notas, duplicados, los cinco casos reales solicitados, SHA-256 y determinismo.

Limitaciones preservadas, no resueltas por interpretación:

- Art. 13 PBA: la modificación observada se conserva en una nota que incluye su transcripción, separada de la vista principal. Art. 25 PBA: la nota remite a subrayado que el TXT no conserva; no puede identificarse exactamente el tramo observado.
- En TP2-RAG-03 se restauró desde el historial la segunda aparición del artículo 151 de PBA y su nota, idénticas a la fuente previa; ambos registros se conservan con IDs diferenciados.
- El parser se ajusta a estas fuentes: reconoce rúbricas con mayúscula inicial, número/sufijo y separador. Una remisión en minúsculas partida en p. 45 del PDF no se convierte en artículo. No es un parser universal de leyes.
- Las referencias externas son menciones literales detectadas, no el contenido de esas leyes ni una lista exhaustiva de relaciones jurídicas. No se reconstruyen formatos perdidos, tachados o subrayados del TXT.
- Los textos fuera de artículos se conservan para revisión. La igualdad de contenido extraído no garantiza por sí sola fidelidad visual de cada página; se hicieron cotejos representativos, no revisión exhaustiva.

La estructura **artículo primero** mantiene excepciones, incisos, anotaciones y procedencia juntos, incluso entre páginas. `RecursiveCharacterTextSplitter` subdivide cada vista por separado; el tamaño y solapamiento son caracteres, no tokens. Las citas sustantivas marcadas `texto_modificatorio` de Santa Fe 285–290 se mantienen en la vista; notas históricas/editoriales como la propuesta observada de PBA 13 no se indexan como texto principal. Los artículos con únicamente nota explícita de derogación reciben una descripción de índice literal derivada de esa nota, sin afirmación independiente de vigencia. El reporte no mide calidad de recuperación; embeddings y recuperación quedan fuera de esta etapa.

## Alcance pendiente

Esto implementa únicamente TP2-RAG-01. Faltan embeddings locales, Chroma, generación con Ollama, Gradio, cinco pruebas RAG (tres respondibles y dos ausentes), reproducción integral en un directorio fresco, documentación final de asistencia de IA y demo/video. El notebook `trabajo_integrador_2_rag.ipynb` referido en la tarea no está presente en este checkout.

El agente implementó y ejecutó estas validaciones; no se afirma que el estudiante las haya revisado personalmente, grabado una demo o enviado la entrega. La declaración final de asistencia debe completar cuándo, modelos utilizados y qué verificó personalmente el estudiante.
