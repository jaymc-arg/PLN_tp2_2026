# PLN_tp2_2026 — RAG local sobre legislación electoral

> **Actualización del conjunto de evaluación:** `evalucacion/preguntas.json` ahora contiene **38 casos (32 respondibles y seis ausentes)**. Para ese conjunto se usa `scripts/evaluar_fragmentacion_pareada.py`, no los evaluadores históricos restringidos a cinco preguntas. El [informe pareado Qwen 1000/150 vs 600/80](evalucacion/experimentos_fragmentacion/comparacion_qwen_600_80_vs_1000_150.md) conserva las ejecuciones reales, la revisión y los comandos. Las tablas históricas de cinco casos de esta guía no corresponden al nuevo conjunto.
>
> `uv run python scripts/evaluar_fragmentacion_pareada.py --ejecutar` crea o reanuda la ejecución local sin repetir casos guardados. Para una corrida nueva, elegir otro directorio con `--salida`; la revisión semántica debe redactarse para sus respuestas reales. `uv run python scripts/evaluar_fragmentacion_pareada.py --review evalucacion/experimentos_fragmentacion/revision_pareada.json` solo aplica la revisión y regenera resúmenes guardados, sin consultar modelos. No se cambiaron los defaults de Gradio ni de fragmentación.

## 1. Introducción y propósito

Un estudiante de legislación electoral necesita localizar y comparar disposiciones de Nación, Provincia de Buenos Aires y Santa Fe con su procedencia, para preparar consultas documentales verificables, **no asesoramiento jurídico**.

El proyecto implementa un sistema de **generación aumentada por recuperación (RAG)**: busca fragmentos de tres leyes y los entrega como evidencia a un modelo local que redacta la respuesta. La interfaz permite inspeccionar por separado respuesta, jurisdicción, fuentes, contexto literal y advertencias de citas. También incluye un laboratorio de fragmentación y evaluaciones reproducibles.

Todo el procesamiento y las consultas se ejecutan localmente. No se usan APIs pagas. Descargar dependencias y modelos sí requiere conexión a Internet.

## 2. Componentes, corpus y archivos

### Flujo de procesamiento

```text
Documentos reales → extracción e inspección → artículos y metadatos
→ fragmentos → embeddings locales Ollama → índice persistente Chroma
→ enrutamiento y recuperación → contexto/prompt explícito
→ generación Ollama → respuesta y evidencia en Gradio
```

| Componente | Implementación / responsabilidad |
|---|---|
| `scripts/00_preprocesar.py` | Lee TXT UTF-8 y PDF con `PyPDFLoader`/`pypdf`; conserva artículos, notas, procedencia y páginas PDF. |
| `scripts/01_fragmentar.py` | Divide cada artículo con `RecursiveCharacterTextSplitter`, sin mezclar artículos. |
| `scripts/02_indexar.py` | Crea/verifica documentos LangChain e indexa con `OllamaEmbeddings` y Chroma. |
| `scripts/03_bis_detectar_jurisdiccion.py` | Detector determinista: Nación, PBA, Santa Fe, comparaciones y solicitudes de aclaración. Es un módulo auxiliar, no una CLI con flags. |
| `scripts/03_recuperar.py` | Recuperación de solo lectura; valida compatibilidad del índice y conserva rankings, distancias y metadatos. |
| `scripts/04_generar.py` | `answer_question()`, `ChatPromptTemplate`, contexto numerado, `ChatOllama` y control sintáctico de citas. |
| `scripts/05_interfaz_gradio.py` | Página local con consultas y laboratorio de fragmentación. |
| `scripts/experimentos_fragmentacion.py` | Prepara/reutiliza índices experimentales aislados; no modifica el índice original. |
| `scripts/evaluar_*.py` | Evaluaciones de recuperación, enrutamiento y generación; se describen en la sección 6. |
| `tests/` | Pruebas de extracción, firmas, rutas, contexto, citas, evaluadores y aislamiento, con dobles cuando corresponde. |

Los scripts numerados se ejecutan por ruta. Para importarlos desde Python se usa `importlib.import_module("scripts.04_generar")`: un identificador de un import normal no puede comenzar con números.

### Corpus y procedencia

Los documentos originales permanecen en `datos/`:

| Archivo | Documento | Inspección registrada por el agente |
|---|---|---|
| `ley_nacional.txt` | Código Electoral Nacional, Ley 19.945 | Art. 12 y excepciones cotejados con el TXT. |
| `ley_pba.txt` | Ley Electoral 5.109 | Arts. 2, 3 y 13 cotejados; se conservan notas editoriales y numeración duplicada. |
| `ley_sta_fe.pdf` | Ley 14.478 de Santa Fe | 70 páginas con texto extraíble, sin OCR; cotejo visual representativo y seguimiento del art. 4 entre pp. 1–4. |

[datos/fuentes.csv](datos/fuentes.csv) registra la procedencia disponible y una pregunta respondible por documento. **La URL oficial, fecha de descarga y permiso de redistribución siguen sin verificación suficiente**; deben verificarse antes de publicar el corpus. No se acredita autenticidad externa ni vigencia jurídica. El TXT nacional tenía un recorte manual previo del usuario; el programa no elimina otra introducción.

### Configuración actual

| Elemento | Valor predeterminado |
|---|---|
| Embeddings | `qwen3-embedding:0.6b` |
| Generación | `granite4:latest`, temperatura 0 |
| Ollama | `http://localhost:11434` |
| Fragmentos originales | `datos/procesados/chunks.jsonl` |
| Fragmentación original | Tamaño 1000, solapamiento 150 **caracteres, no tokens** |
| Índice Qwen | `.chroma/electoral_laws_qwen3_0_6b` |
| Índice histórico BGE-M3 | `.chroma/electoral_laws`, con modelo `bge-m3` |
| Colección Chroma | `electoral_laws` |
| Interfaz | `127.0.0.1:7860` por defecto, sin enlace público |

Las versiones de dependencias están fijadas en `uv.lock` y exportadas en `requirements.txt`. La ejecución Qwen registrada usó Python 3.12.7, Ollama 0.40.15, langchain-chroma 0.2.6, langchain-ollama 0.3.10, chromadb 1.5.9 y cliente ollama 0.6.3. El modelo Qwen instalado fue Q8_0, dimensión 1024; su digest completo está en el informe de recuperación Qwen.

## 3. Prerrequisitos

- Python **3.12** y [uv](https://docs.astral.sh/uv/).
- [Ollama](https://ollama.com/) instalado y su servicio activo.
- Espacio para el entorno, modelos e índices. Se puede ejecutar en CPU, pero indexar y generar puede tardar varios minutos; no se especifica un mínimo de hardware validado.
- Los documentos de `datos/` y los archivos procesados usados por la configuración elegida.
- Ejecutar los ejemplos desde la raíz del repositorio, en Bash/Zsh. Las rutas explícitas relativas se interpretan desde esa terminal.

Los índices `.chroma/` y los modelos Ollama **no se versionan**: en una instalación nueva hay que descargarlos/construirlos. No hace falta activar `.venv` cuando se usa `uv run`.

## 4. Puesta en marcha paso a paso

### Paso 1 — Instalar dependencias

```bash
uv sync
```

Opcional, si preferís activar el entorno en Linux/macOS:

```bash
source .venv/bin/activate
```

### Paso 2 — Iniciar Ollama y descargar modelos

En una terminal, **solo si Ollama no está ya ejecutándose**:

```bash
ollama serve
```

Dejá esa terminal abierta. En otra terminal, desde el proyecto:

```bash
ollama pull qwen3-embedding:0.6b
ollama pull granite4:latest
ollama list
```

### Paso 3 — Elegir modelo, fragmentos e índice

Usaremos estas variables en los comandos siguientes. Son variables de la terminal, no un sistema de configuración adicional:

```bash
EMBEDDING_MODEL="qwen3-embedding:0.6b"
GENERATION_MODEL="granite4:latest"
CHUNKS="datos/procesados/chunks.jsonl"
INDEX_DIR=".chroma/electoral_laws_qwen3_0_6b"
```

**Para probar BGE-M3**, descargalo y cambiá juntos modelo e índice:

```bash
ollama pull bge-m3
EMBEDDING_MODEL="bge-m3"
INDEX_DIR=".chroma/electoral_laws"
```

Mantené `CHUNKS` correspondiente al índice elegido. **Nunca consultes un índice con un modelo o archivo de fragmentos distinto del usado para construirlo.** La firma del índice comprueba modelo y SHA-256 de los fragmentos y rechaza incompatibilidades; igual dimensión no significa compatibilidad.

### Paso 4 — Construir el índice elegido, si hace falta

Para la configuración original se pueden usar directamente los fragmentos versionados: **no hace falta volver a preprocesar ni fragmentar**.

```bash
uv run python scripts/02_indexar.py \
  --chunks "$CHUNKS" --index-dir "$INDEX_DIR" --model "$EMBEDDING_MODEL" \
  --smoke-question "¿Qué excepciones al deber de votar establece el artículo 12?"
```

El indexador verifica IDs y metadatos, agrega documentos faltantes y ejecuta una consulta de inspección. Repetirlo con la misma firma no duplica IDs, pero sí necesita Ollama y calcula el embedding de la consulta de inspección. Si el índice ya es compatible, podés pasar directamente a consultar.

`--rebuild` es **destructivo para el directorio de índice seleccionado**: no lo uses para alternar modelos. Solo corresponde a una reconstrucción deliberada de un índice propio y reconocido. Para experimentos, preferí otra ruta.

### Paso 5 — Consultar por terminal

**Solo recuperación, sin redactar una respuesta:**

```bash
uv run python scripts/03_recuperar.py \
  --model "$EMBEDDING_MODEL" --index-dir "$INDEX_DIR" --chunks "$CHUNKS" \
  --pregunta "¿Qué excepciones establece el Código Electoral Nacional?" --k 5
```

**Recuperación y generación, con salida JSON completa:**

```bash
uv run python scripts/04_generar.py \
  --embedding-model "$EMBEDDING_MODEL" --model "$GENERATION_MODEL" \
  --index-dir "$INDEX_DIR" --chunks "$CHUNKS" \
  --pregunta "Según el artículo 13 de la Ley 5.109, ¿cuántos diputados y senadores hay?" \
  --k 3 --json
```

> **Importante:** `--model` en `02_indexar.py` y `03_recuperar.py` selecciona **embeddings**. En `04_generar.py` y `evaluar_generacion.py` selecciona el **generador**; allí los embeddings se eligen con `--embedding-model`. En generación también existe el alias `--modelo`.

| Control de consulta | Comportamiento |
|---|---|
| Sin flags de jurisdicción | Enrutamiento automático conservador. |
| `--jurisdiccion nacional`, `pba` o `santa_fe` | Selección manual que prevalece sobre la detección. |
| `--sin-filtro` | Consulta exploratoria global. Es incompatible con `--jurisdiccion`. |
| `--k` | Cantidad de fragmentos **por jurisdicción** en comparaciones. Recuperación acepta cualquier entero positivo; generación admite 1, 3 o 5. |
| `--json` | Solo en `04_generar.py`: conserva respuesta, contexto literal, ruta, fuentes y chequeo de citas. |

Por ejemplo, podés reemplazar la pregunta y agregar `--jurisdiccion santa_fe --k 5`. Una comparación explícita entre las leyes 5.109 y 14.478 consulta cada jurisdicción por separado. «¿Cómo se vota en PBA?» es ambigua: sin selección manual ni `--sin-filtro`, pide precisión sin recuperar ni generar.

La CLI de recuperación muestra un **adelanto de hasta 350 caracteres** por resultado; no es el contexto completo. Para ver evidencia íntegra usá generación con `--json`, Gradio o los JSON de evaluación.

### Paso 6 — Abrir Gradio

```bash
uv run python scripts/05_interfaz_gradio.py
```

Abrí **http://127.0.0.1:7860** o la dirección local indicada. Elegí pregunta, K=1/3/5 y jurisdicción; pulsá **Consultar**. Las salidas son respuesta/aclaración, enrutamiento, fuentes recuperadas, evidencia literal completa enviada al modelo y revisión de citas.

**Las variables de terminal del paso 3 no cambian Gradio.** La interfaz no tiene flags ni selector de modelos: usa los defaults compartidos de `scripts/02_indexar.py`. Actualmente **Índice original significa Qwen + fragmentación 1000/150**, no BGE. Para cambiar globalmente Gradio a BGE, cambiar juntos `DEFAULT_MODEL` a `"bge-m3"` y `DEFAULT_INDEX` a `ROOT / ".chroma/electoral_laws"`, y reiniciar. Para alternar sin editar código, usá las CLIs anteriores.

En **Laboratorio de fragmentación**, seleccioná **Índice experimental**, elegí tamaño (300–2000 caracteres) y solapamiento (entero ≥0 y menor que tamaño), y pulsá **Preparar / reutilizar índice experimental**. Cambiar controles no indexa ni genera: limpia resultados anteriores y exige preparar la configuración visible antes de consultar.

Los experimentos consumen los artículos ya procesados y guardan `chunks.jsonl`, `reporte_fragmentacion.json` e `indice/` bajo `.chroma/experimentos/<hash>/`. La identidad incluye modelo, parámetros, contenido de artículos y código/versión del divisor. Una configuración completa compatible se reutiliza sin recalcular embeddings ni reescribir sus fragmentos. El estado es por sesión; al elegir **Índice original** se vuelve sin reconstruir nada. No ejecutar varios procesos preparando simultáneamente la misma configuración.

## 5. Probar otras configuraciones por terminal

### Cambiar tamaño y solapamiento sin alterar los fragmentos originales

Estos flags miden **caracteres**, no tokens. Tamaño controla la longitud máxima de los fragmentos; solapamiento busca repetir contexto entre fragmentos contiguos, según los separadores disponibles. No asegura que todas las excepciones de un artículo queden juntas. El punto de partida 1000/150 equilibra contexto y repetición, pero el art. 12 nacional demuestra una división incompleta real.

Ejemplo independiente de 600/50:

```bash
uv run python scripts/01_fragmentar.py \
  --entrada datos/procesados \
  --salida .chroma/pruebas/qwen_600_50/chunks.jsonl \
  --chunk-size 600 --chunk-overlap 50

EMBEDDING_MODEL="qwen3-embedding:0.6b"
CHUNKS=".chroma/pruebas/qwen_600_50/chunks.jsonl"
INDEX_DIR=".chroma/pruebas/qwen_600_50/indice"

uv run python scripts/02_indexar.py \
  --chunks "$CHUNKS" --index-dir "$INDEX_DIR" --model "$EMBEDDING_MODEL"
```

Después usá **esas mismas tres variables** en consultas y evaluaciones. No cambies `--chunks` manteniendo un índice anterior. El fragmentador escribe el reporte `reporte_fragmentacion.json` **junto al archivo de salida**: usar directorios distintos evita sobrescribir el reporte de otra configuración.

### Reconstruir extracción y artículos, solo si lo necesitás

No es necesario para probar embeddings sobre los fragmentos versionados. Para inspeccionar toda la cadena sin sobrescribir los procesados originales:

```bash
uv run python scripts/00_preprocesar.py \
  --entrada datos --salida .chroma/reconstruccion/procesados
uv run python scripts/01_fragmentar.py \
  --entrada .chroma/reconstruccion/procesados \
  --salida .chroma/reconstruccion/chunks.jsonl \
  --chunk-size 1000 --chunk-overlap 150
```

El preprocesador genera los tres `*_articulos.jsonl` y `reporte_preprocesamiento.json` en su directorio de salida. El fragmentador genera el JSONL solicitado y su reporte. Si después indexás esta reconstrucción, elegí también una ruta de índice independiente.

## 6. Evaluaciones: ejecución configurable y lectura de resultados

### Reglas comunes

- Los cinco casos de [evalucacion/preguntas.json](evalucacion/preguntas.json) son tres respondibles (uno por ley) y dos ausentes (resultado presidencial 2023 y gasto real de campaña). Se fijaron antes de observar resultados.
- No cambies preguntas, fragmentación y modelo a la vez si querés atribuir una diferencia a una sola variable.
- Los evaluadores **escriben sus archivos de salida**. No ejecutarlos sobre rutas históricas si querés conservarlas. Los ejemplos siguientes usan un directorio propio; cambiá su nombre para cada corrida.
- `--review` indica una **revisión manual de entrada**, no un archivo que el evaluador complete automáticamente. Si no existe, el reporte queda pendiente de revisión; eso no significa necesariamente que haya fallado la ejecución.
- No reutilices una revisión de otra configuración sin inspeccionar los resultados reales: los IDs, citas o hashes pueden no coincidir. Los diagnósticos semánticos no se deducen de Hit@k ni del formato de las citas.

Antes de ejecutar, definí modelo, fragmentos e índice con el paso 3, o con tu configuración de la sección 5. Por ejemplo, para volver a Qwen original:

```bash
EMBEDDING_MODEL="qwen3-embedding:0.6b"
GENERATION_MODEL="granite4:latest"
CHUNKS="datos/procesados/chunks.jsonl"
INDEX_DIR=".chroma/electoral_laws_qwen3_0_6b"
RUN_DIR="evalucacion/mis_pruebas/qwen_original_01"
```

Los evaluadores crean los directorios de sus reportes. Repetir los ejemplos con el mismo `RUN_DIR` sobrescribe **tus salidas de esa corrida**.

### A. Recuperación — `evaluar_recuperacion.py`

Necesita el índice compatible y Ollama con embeddings; **no invoca el generador**. Hace seis consultas positivas (tres × sin/con filtro), dos negativas y una paráfrasis nacional independiente. Todas usan K=5; deriva k=1/k=3 del mismo ranking, verifica el contexto numerado y compara IDs/manifest antes y después.

```bash
uv run python scripts/evaluar_recuperacion.py \
  --questions evalucacion/preguntas.json \
  --model "$EMBEDDING_MODEL" --index-dir "$INDEX_DIR" --chunks "$CHUNKS" \
  --report "$RUN_DIR/recuperacion.json" \
  --markdown "$RUN_DIR/recuperacion.md" \
  --plot "$RUN_DIR/distancias.svg" \
  --review "$RUN_DIR/revision_recuperacion.json" \
  --baseline-report evalucacion/reporte_recuperacion.json
```

`--baseline-report` es opcional: compara reportes del mismo fixture, **no ejecuta búsquedas BGE** ni demuestra que otros parámetros sean idénticos. Para una comparación controlada de embeddings, mantené los mismos chunks. No existe un flag `--k` en este evaluador: su protocolo fija K=5.

| Archivo / campo | Cómo leerlo |
|---|---|
| `recuperacion.json` | Evidencia completa: `positive_questions`, `negative_questions`, rankings `results`, textos, IDs, artículos, distancias, fuentes y páginas disponibles. |
| `article_metrics` | Acierto del artículo esperado, no suficiencia del fragmento. Incluye `first_expected_rank`. |
| `aggregate_positive_metrics` | Hit@1/3/5 y MRR@5 sobre las **tres positivas**; negativas excluidas. |
| `filter_comparison` | Indica si cambió el primer resultado o el conjunto/orden top-3 al aplicar filtro. |
| `paraphrase_trial`, `k_comparison` | Ensayo independiente y comparación de cortes del ranking. La paráfrasis no entra en el agregado fijo. |
| `numbered_evidence_context` | Contexto literal completo con numeración global. No es una respuesta generada. |
| `index_integrity` | Debe indicar `unchanged: true`; compara IDs y manifest, no validez jurídica. |
| `recuperacion.md` | Resumen legible, diagnósticos y comparación si se pasó `--baseline-report`. |
| `distancias.svg` | Distancias reales del top-3 nacional sin filtro. No son porcentajes de confianza. |
| `revision_recuperacion.json` | Lo redactás tras inspeccionar resultados: `fixed_positive` por modo, `reviewed_top3_chunk_ids`, cobertura `yes/partial/no`, citas literales; además negativas, paráfrasis y comparación K. La función `validate_manual_review()` en el script define el contrato. |

Tras escribir una revisión válida, podés actualizar JSON, Markdown y gráfico **sin nuevas consultas**:

```bash
uv run python scripts/evaluar_recuperacion.py \
  --usar-reporte-existente "$RUN_DIR/recuperacion.json" \
  --questions evalucacion/preguntas.json --model "$EMBEDDING_MODEL" \
  --report "$RUN_DIR/recuperacion.json" --markdown "$RUN_DIR/recuperacion.md" \
  --plot "$RUN_DIR/distancias.svg" --review "$RUN_DIR/revision_recuperacion.json" \
  --baseline-report evalucacion/reporte_recuperacion.json
```

Sin rutas explícitas, el evaluador usa los archivos `reporte_recuperacion_qwen3_0_6b.json`, `validacion_recuperacion_qwen3_0_6b.md`, `distancias_recuperacion_qwen3_0_6b.svg` y la revisión `revision_manual_recuperacion_qwen3_0_6b.json` en `evalucacion/`. Usá los ejemplos con `RUN_DIR` para no sobrescribir ese registro.

### B. Enrutamiento — `evaluar_jurisdiccion.py`

La clasificación sobre las 40 etiquetas de `preguntas_jurisdiccion.json` **no requiere Ollama ni índice**:

```bash
uv run python scripts/evaluar_jurisdiccion.py \
  --fixture evalucacion/preguntas_jurisdiccion.json \
  --report "$RUN_DIR/jurisdiccion_sin_recuperacion.json" \
  --markdown "$RUN_DIR/jurisdiccion_sin_recuperacion.md"
```

Para agregar recuperación real sobre las tres preguntas positivas de `evalucacion/preguntas.json`:

```bash
uv run python scripts/evaluar_jurisdiccion.py \
  --fixture evalucacion/preguntas_jurisdiccion.json --with-retrieval \
  --model "$EMBEDDING_MODEL" --index-dir "$INDEX_DIR" --chunks "$CHUNKS" \
  --report "$RUN_DIR/jurisdiccion_con_recuperacion.json" \
  --markdown "$RUN_DIR/jurisdiccion_con_recuperacion.md"
```

`--fixture` configura las etiquetas del detector; **no cambia** el archivo fijo de tres preguntas usado por `--with-retrieval`. El script no ofrece flags para K, revisión manual ni rerender desde un reporte previo.

En el JSON, `classification.cases` muestra etiqueta esperada/predicha, señales, motivo y aclaración; `classification.metrics` contiene matriz de confusión, precisión/recall y errores de enrutamiento. `retrieval_impact` indica `not requested`, `blocked` o `completed`. Si está completado, inspeccioná sus `runs`, `metrics`, fugas jurisdiccionales e integridad: `--with-retrieval` puede quedar bloqueado aunque la clasificación se haya completado.

**Advertencia:** `retrieval_impact.passage_review` contiene diagnósticos textuales históricos codificados en el script; no es una inspección nueva automática de tus pasajes. Revisá los rankings reales y usá el evaluador de recuperación para una nueva revisión específica de modelo/configuración.

Sin rutas explícitas, escribe `reporte_jurisdiccion.json` y `validacion_jurisdiccion.md` en `evalucacion/`, sobrescribiendo esos destinos.

### C. Generación — `evaluar_generacion.py`

Requiere embeddings, índice y modelo generador. Ejecuta las cinco preguntas mediante `answer_question()` con enrutamiento automático y K=3, más una ejecución nacional K=1. No tiene flags para elegir K, filtro manual o `--sin-filtro` durante esta evaluación.

```bash
uv run python scripts/evaluar_generacion.py \
  --questions evalucacion/preguntas.json \
  --embedding-model "$EMBEDDING_MODEL" --model "$GENERATION_MODEL" \
  --index-dir "$INDEX_DIR" --chunks "$CHUNKS" \
  --report "$RUN_DIR/generacion.json" --markdown "$RUN_DIR/generacion.md" \
  --review "$RUN_DIR/revision_generacion.json"
```

| Campo / archivo | Interpretación |
|---|---|
| `fixed_cases[].expected` | Respuesta/fuentes esperadas, fijadas antes de la generación. |
| `fixed_cases[].generation` | Respuesta real, `original_response`, ruta, `source_map`, `retrieval_records` y `context_sent` exacto. |
| `citation_check` | Citas faltantes, inexistentes o malformadas. Una cita válida sintácticamente puede no respaldar una afirmación. |
| `generation_status`, `overall_generation_error` | Verificar errores o casos no ejecutados antes de interpretar resultados. No convertir una ejecución fallida en un acierto o abstención. |
| `k_comparison` | Contexto/respuesta/citas con K=1 y K=3; no un porcentaje general de precisión. |
| `manual_review`, `diagnosis` | Estado de inspección semántica. Si está pendiente, no asumir que la respuesta está respaldada. |
| `runtime`, `embedding_model`, `index_integrity` | Modelo generador/digest, embeddings usados y comprobación de integridad. |
| `generacion.md` | Tabla legible de casos, respuestas y limitaciones. |
| `revision_generacion.json` | Entrada manual, no salida automática: cobertura, apoyo de respuesta, fallos/observaciones y hashes de las respuestas originales, incluida la comparación K. Ver `validate_manual_review()` en el script. |

Para aplicar una revisión o rehacer el resumen sin llamar a Ollama:

```bash
uv run python scripts/evaluar_generacion.py \
  --usar-reporte-existente "$RUN_DIR/generacion.json" \
  --questions evalucacion/preguntas.json \
  --embedding-model "$EMBEDDING_MODEL" --model "$GENERATION_MODEL" \
  --report "$RUN_DIR/generacion.json" --markdown "$RUN_DIR/generacion.md" \
  --review "$RUN_DIR/revision_generacion.json"
```

El rerender usa los datos del JSON guardado: **no cambia de modelo ni reevalúa respuestas** por pasar otros flags. Rechaza reportes históricos sin el protocolo actual de enrutamiento y valida los hashes de las respuestas si hay revisión. Una revisión vieja puede quedar marcada como no aplicada o impedir el rerender; no se debe forzar su reutilización.

Sin rutas explícitas, escribe `reporte_generacion_enrutada.json` y `validacion_generacion_enrutada.md`; busca `revision_manual_generacion_enrutada.json`. Ese archivo de revisión puede no existir y no se crea automáticamente. El texto interno legado `baseline.retrieval_protocol` todavía menciona BGE: para identificar el embedding real mirá `embedding_model` y los registros de ejecución, no esa etiqueta histórica.

### Cómo interpretar las métricas

- **Hit@k:** fracción de preguntas positivas cuyo artículo esperado aparece entre los primeros k fragmentos. Varias coincidencias del mismo artículo no suman aciertos adicionales.
- **MRR@5:** promedio de `1 / primer rango esperado`; si no aparece en top-5, aporta 0. Ejemplo: rango 4 aporta 0.25.
- **Cobertura de pasaje:** revisión de si los fragmentos contienen la respuesta completa, parcial o ninguna. Puede haber un hit de artículo sin la excepción o definición requerida.
- **Precisión/recall de jurisdicción:** miden clasificación, no exactitud de la respuesta legal.
- **Distancia Chroma:** menor indica un vecino más cercano dentro de ese espacio; no es probabilidad ni permite comparar calidad directamente entre modelos.

Primero verificá errores/integridad, después fuentes y pasajes, y finalmente apoyo de la respuesta y citas. Un ranking no vacío en una pregunta ausente no demuestra que el corpus pueda responderla.

### Dónde están los resultados ya registrados

| Registro | Archivos y lectura |
|---|---|
| Extracción / indexación | [validacion_preprocesamiento.md](evalucacion/validacion_preprocesamiento.md), [validacion_indexacion.md](evalucacion/validacion_indexacion.md). Informes históricos de inspecciones, no salidas automáticas de cada ejecución actual. |
| Recuperación BGE-M3 | [reporte_recuperacion.json](evalucacion/reporte_recuperacion.json), [validacion_recuperacion.md](evalucacion/validacion_recuperacion.md), [revision_manual_recuperacion.json](evalucacion/revision_manual_recuperacion.json). Histórico conservado; el SVG puede no estar disponible en este checkout. |
| Recuperación Qwen | [reporte_recuperacion_qwen3_0_6b.json](evalucacion/reporte_recuperacion_qwen3_0_6b.json), [validacion_recuperacion_qwen3_0_6b.md](evalucacion/validacion_recuperacion_qwen3_0_6b.md), [revision_manual_recuperacion_qwen3_0_6b.json](evalucacion/revision_manual_recuperacion_qwen3_0_6b.json). Incluyen comparación y citas cotejadas. El evaluador también puede generar el SVG con sufijo Qwen. |
| Enrutamiento | [reporte_jurisdiccion.json](evalucacion/reporte_jurisdiccion.json), [validacion_jurisdiccion.md](evalucacion/validacion_jurisdiccion.md). Clasificación registrada 40/40 sobre ese conjunto; impacto de recuperación histórico con BGE. |
| Generación BGE histórica | [reporte_generacion.json](evalucacion/reporte_generacion.json), [validacion_generacion.md](evalucacion/validacion_generacion.md): protocolo anterior sin enrutamiento. [reporte_generacion_enrutada.json](evalucacion/reporte_generacion_enrutada.json), [validacion_generacion_enrutada.md](evalucacion/validacion_generacion_enrutada.md): protocolo enrutado. No son una evaluación de generación con Qwen. |

Resumen de recuperación registrada (denominador: tres positivas):

| Modelo / modo | Hit@1 | Hit@3 | Hit@5 | MRR@5 |
|---|---:|---:|---:|---:|
| BGE-M3 sin filtro | 0.667 | 0.667 | 0.667 | 0.667 |
| BGE-M3 filtrado | 0.667 | 0.667 | 0.667 | 0.667 |
| Qwen sin filtro | 0.667 | 0.667 | 0.667 | 0.667 |
| Qwen filtrado | 0.667 | 0.667 | 1.000 | 0.750 |

Los cinco casos registrados muestran: Nación sigue parcial por falta de la continuación del art. 12; PBA recupera 92 diputados/46 senadores; Santa Fe encuentra la definición en rango 4 filtrado Qwen, fuera de K=3; las preguntas sobre ganador/votos de 2023 y gasto real no tienen evidencia factual en estas leyes. La paráfrasis nacional mejora de rango 4 a 1 con Qwen, pero PBA/Santa Fe tienen más vecinos de otras jurisdicciones sin filtro. No se infiere una mejora general a partir de estos casos.

## 7. Pruebas y ayuda de comandos

```bash
uv run pytest -q
uv run python scripts/00_preprocesar.py --help
uv run python scripts/01_fragmentar.py --help
uv run python scripts/02_indexar.py --help
uv run python scripts/03_recuperar.py --help
uv run python scripts/04_generar.py --help
uv run python scripts/evaluar_recuperacion.py --help
uv run python scripts/evaluar_jurisdiccion.py --help
uv run python scripts/evaluar_generacion.py --help
```

Los tests no requieren Ollama, índice real ni abrir un puerto; las pruebas con dobles no son resultados de rendimiento del RAG. La última ejecución de suite registrada para el cambio a Qwen fue **171 passed**, con 16 avisos esperados de compatibilidad de `generate_answer()`. Para código nuevo se usa `answer_question()`.

Gradio no implementa una CLI configurable con `--help`: ejecutá su script sin flags. Para regenerar el archivo de dependencias exportado, si se cambian dependencias mediante `uv`:

```bash
uv export --format requirements-txt --no-hashes --output-file requirements.txt
```

## 8. Errores frecuentes, fidelidad y límites

| Síntoma | Qué revisar |
|---|---|
| No conecta a Ollama / falta modelo | Servicio `ollama serve` y `ollama list`; descargar el tag exacto. No hay cambio automático de modelo. |
| Falta índice o manifest | Construir explícitamente con `02_indexar.py`, modelo/chunks/ruta correctos. La consulta no lo crea. |
| Firma incompatible | Revisar juntos modelo, fragmentos e índice. Usar una nueva ruta para otra configuración, no borrar un baseline para resolverlo. |
| Laboratorio no preparado | Elegir modo experimental y pulsar Preparar tras aplicar los valores; cambiar controles invalida el estado anterior. |
| Respuesta de aclaración | Precisar elección/norma o elegir jurisdicción manualmente; no es un fallo del servidor. |
| Review pendiente / cita que no coincide | Inspeccionar el JSON real y redactar una revisión de esa corrida. No copiar citas o hashes de otro resultado. |
| Datos correctos sin cita, o cita sin apoyo | Revisar `context_sent` y advertencias. El control de formato no valida semántica. |

Los artículos conservan texto, notas, estructura, duplicados y fuente. Las páginas PDF son las originales, desde 1, y pueden abarcar todo el artículo; los TXT no reciben páginas inventadas. El preprocesador conserva auditoría de layout, referencias, anotaciones y segmentos fuera de artículos; no aplica OCR automático. `texto_principal` distingue notas editoriales de texto modificatorio, pero no constituye una consolidación jurídica.

Entre los límites reales: excepción nacional dividida entre chunks, definición santafesina fuera de top-3, vecinos de leyes distintas, notas históricas/observadas en PBA y respuestas de Granite sin cita o con citas formalmente válidas pero sin apoyo. El parser está ajustado a este corpus, no es un analizador universal de leyes. No se garantiza vigencia, completitud ni abstención del generador.

## 9. Asistencia de IA y pendientes de entrega

Se utilizó IA para delimitar el trabajo, implementar código, elaborar pruebas, ejecutar validaciones locales e inspeccionar/documentar resultados. Las intervenciones registradas el 13/11/2026 incluyen integración Gradio, laboratorio, reparación de imports y ensayo Qwen; [bitacora.md](bitacora.md) detalla tareas, comandos y límites. Una sesión de agente está identificada allí como `gpt-6.1-sol`; no se atribuye ese identificador a todas las sesiones sin registro. Qwen/BGE son modelos de embeddings del sistema y Granite su generador, no la identificación del asistente de programación.

El agente registró comprobaciones técnicas y lectura de evidencia, **no una revisión jurídica independiente ni verificación personal del estudiante**. La declaración final debe completar modelos/fechas de asistencia que falten y qué comprobó personalmente el estudiante.

Quedan pendientes la verificación de procedencia/redistribución, reproducción integral en un directorio fresco, revisión personal de resultados y demo/entrega final. Esta guía no afirma que esos pasos ya se realizaron. No incluir DNI, secretos ni credenciales en el repositorio público; `.venv/`, índices y archivos de entorno deben permanecer ignorados.
