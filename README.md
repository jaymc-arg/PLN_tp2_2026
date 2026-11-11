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
uv run python scripts/preprocesar.py
uv run python scripts/fragmentar.py
uv run pytest -q
uv run python scripts/preprocesar.py
```

La última ejecución permite comparar los archivos; la prueba de determinismo también genera una segunda salida y compara sus bytes, incluido el reporte. No hay marcas de tiempo volátiles ni llamadas a servicios externos durante el procesamiento. `uv.lock` fija las dependencias; `requirements.txt` incluye ejecución y pruebas y se exporta con:

```bash
uv export --format requirements-txt --no-hashes --output-file requirements.txt
```

Alternativa de rutas, sin modificar los originales:

```bash
uv run python scripts/preprocesar.py --entrada datos --salida /tmp/tp2-procesados
```

El PDF se extrae con `langchain-community` / `PyPDFLoader` y `pypdf`; los TXT se decodifican como UTF-8 estricto. Las versiones exactas están en el lock y en `requirements.txt`. Un archivo ausente, UTF-8 inválido o página PDF sin texto detiene la ejecución: no se sustituye ni se aplica OCR automáticamente.

## Proceso y salidas

`originales locales → lectura → limpieza de espacios/layout → artículos y anotaciones → JSONL + auditoría`

- `scripts/`: ejecutables (`preprocesar.py`, `fragmentar.py`, `indexar.py`, `recuperar.py`, `evaluar_recuperacion.py`); sus rutas predeterminadas se resuelven respecto a la raíz del repositorio. `tests/`: pruebas del pipeline y retrieval.
- `datos/procesados/{nacional,pba,santa_fe}_articulos.jsonl`: un registro por artículo en orden de aparición.
- `datos/procesados/chunks.jsonl`: vista recuperable por artículo, dividida con `RecursiveCharacterTextSplitter` (1000 caracteres, solapamiento 150); ejecutable por separado con `uv run python scripts/fragmentar.py`.
- `datos/procesados/reporte_fragmentacion.json`: conteos y longitudes observadas de chunks.
- `evalucacion/preguntas.json`: cinco preguntas de evaluación fijadas manualmente antes de probar retrieval: tres respondibles con una fuente por jurisdicción y dos ausentes del corpus.
- `scripts/indexar.py`: indexación local Ollama + Chroma; `tests/test_indexar.py`: validación de metadatos, firmas y contrato de indexación con dobles de prueba (no sustituye una prueba del servicio real).
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

## Índice vectorial local (TP2-RAG-04)

Requiere Ollama instalado desde [ollama.com](https://ollama.com/) y su servicio local activo. En una terminal:

```bash
# Iniciar sólo si el servicio Ollama no está corriendo ya:
ollama serve
ollama pull bge-m3
ollama list
uv sync
uv run python scripts/preprocesar.py
uv run python scripts/fragmentar.py
uv run python scripts/indexar.py
```

`scripts/indexar.py` lee los chunks ya generados, crea `Document` de LangChain, usa `OllamaEmbeddings(model="bge-m3", base_url="http://localhost:11434")` y persiste una colección `electoral_laws` bajo `.chroma/electoral_laws/` (ruta ignorada por Git). Al terminar verifica los IDs/cantidad, informa dimensión sólo si el embedding la devuelve y muestra una inspección semántica de hasta tres fragmentos. Esa consulta sirve para inspeccionar la conexión y el ranking, **no acredita que la respuesta a una pregunta sea correcta**. Las preguntas fijas se evalúan por separado en `evalucacion/` mediante retrieval read-only.

La firma local contiene versión de esquema, nombre de colección, modelo y SHA-256 exacto de `chunks.jsonl`. Una repetición con la misma firma es idempotente (IDs estables y upsert); cambio de modelo o chunks detiene el uso y pide regenerar explícitamente:

```bash
uv run python scripts/indexar.py --rebuild
```

`--rebuild` elimina sólo el directorio de índice seleccionado, y se niega a borrar carpetas sin un manifest propio reconocido. También se puede seleccionar ruta/modelo mediante `--index-dir` y `--model`; no se debe cambiar el modelo si se pretende reutilizar el índice. Índice y embeddings se ejecutan localmente; no se consulta un proveedor remoto. Versiones verificadas en este entorno: Ollama `0.40.15`; modelo `bge-m3:latest` (ID `790764642607`, dimensión devuelta 1024); `langchain-chroma 0.2.6`, `langchain-ollama 0.3.10`, `chromadb 1.5.9`, cliente Python `ollama 0.6.3`. En la indexación observada hubo 828/828 IDs únicos y persistidos.

El TXT/PDF no se modifica: el indexador sólo lee `chunks.jsonl`. La conversión omite campos `null` (en particular páginas para TXT) en metadatos Chroma y mantiene rango completo de páginas del artículo PDF, no páginas inventadas por chunk. La app no mide precisión de retrieval ni genera respuestas.

## Recuperación semántica y evaluación (TP2-RAG-05)

Con el índice existente y Ollama activo, consulta sin filtro o restringe en Chroma por jurisdicción:

```bash
uv run python scripts/recuperar.py --pregunta "¿Qué excepciones al deber de votar establece el Código Electoral Nacional?" --k 5
uv run python scripts/recuperar.py --pregunta "¿Cómo define Santa Fe la autoridad de mesa?" --jurisdiccion santa_fe --k 5
uv run python scripts/evaluar_recuperacion.py
```

`--k` debe ser positivo; `--jurisdiccion` acepta `nacional`, `pba`, `santa_fe` y, si se omite, no se aplica filtro. La capa valida modelo/corpus/manifiesto y abre la colección con creación deshabilitada: no llama al indexador, no agrega ni re-embebe documentos. Distancia nativa Chroma menor significa vecino más cercano, **no** probabilidad de respuesta correcta. El API y el JSON conservan texto completo, ID, fuente, artículo y páginas PDF disponibles; TXT no recibe páginas inventadas. Los resultados negativos también tienen vecinos; retrieval no decide abstención.

La ejecución evaluó una vez cada combinación requerida con k=5. `evalucacion/reporte_recuperacion.json` guarda los rankings completos, métricas por artículo, inspecciones manuales de pasajes realizadas por el agente (pendientes de verificación personal del estudiante), paráfrasis, comparación k=1/k=3, un preview numerado con texto íntegro e integridad del índice. `validacion_recuperacion.md` resume la evidencia; `distancias_recuperacion.svg` grafica distancias reales del top-3. En esta corrida, sin filtro y filtrada, Hit@1/3/5 fueron **0.667** y MRR@5 **0.667** (denominador: tres positivas; las negativas se excluyen). La cobertura de pasaje top-3, inspeccionada manualmente por el agente, fue nacional **parcial**, PBA **sí**, Santa Fe **no** en ambos modos. El índice/article hit no equivale a evidencia completa: el chunk siguiente del art. 12 nacional no aparece en top-5; el art. 4 santafesino no aparece en top-5 aunque sí está en los chunks, y el top vecino es el art. 67. Ver reporte para fuentes, distancias, revisión de preguntas ausentes y limitaciones.

## Alcance pendiente

Faltan generación local, Gradio, reproducción integral en un directorio fresco, documentación final de asistencia de IA y demo/video. El notebook `trabajo_integrador_2_rag.ipynb` referido en la tarea no está presente en este checkout.

El agente implementó y ejecutó estas validaciones; no se afirma que el estudiante las haya revisado personalmente, grabado una demo o enviado la entrega. La declaración final de asistencia debe completar cuándo, modelos utilizados y qué verificó personalmente el estudiante.
