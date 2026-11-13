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

Requiere Python **3.12** y `uv` (verificación realizada con uv 0.5.4). Los scripts numerados se ejecutan por su ruta; para importarlos desde Python se usa `importlib.import_module`, por ejemplo `import_module("scripts.04_generar")`, porque un identificador de un import normal no puede comenzar con números. Desde la raíz:

```bash
uv sync
uv run python scripts/00_preprocesar.py
uv run python scripts/01_fragmentar.py
uv run pytest -q
uv run python scripts/00_preprocesar.py
```

La última ejecución permite comparar los archivos; la prueba de determinismo también genera una segunda salida y compara sus bytes, incluido el reporte. No hay marcas de tiempo volátiles ni llamadas a servicios externos durante el procesamiento. `uv.lock` fija las dependencias; `requirements.txt` incluye ejecución y pruebas y se exporta con:

```bash
uv export --format requirements-txt --no-hashes --output-file requirements.txt
```

Alternativa de rutas, sin modificar los originales:

```bash
uv run python scripts/00_preprocesar.py --entrada datos --salida /tmp/tp2-procesados
```

El PDF se extrae con `langchain-community` / `PyPDFLoader` y `pypdf`; los TXT se decodifican como UTF-8 estricto. Las versiones exactas están en el lock y en `requirements.txt`. Un archivo ausente, UTF-8 inválido o página PDF sin texto detiene la ejecución: no se sustituye ni se aplica OCR automáticamente.

## Proceso y salidas

`originales locales → lectura → limpieza de espacios/layout → artículos y anotaciones → JSONL + auditoría`

- `scripts/`: ejecutables (`00_preprocesar.py`, `01_fragmentar.py`, `02_indexar.py`, `03_recuperar.py`, `evaluar_recuperacion.py`); sus rutas predeterminadas se resuelven respecto a la raíz del repositorio. `tests/`: pruebas del pipeline y retrieval.
- `datos/procesados/{nacional,pba,santa_fe}_articulos.jsonl`: un registro por artículo en orden de aparición.
- `datos/procesados/chunks.jsonl`: vista recuperable por artículo, dividida con `RecursiveCharacterTextSplitter` (1000 caracteres, solapamiento 150); ejecutable por separado con `uv run python scripts/01_fragmentar.py`.
- `datos/procesados/reporte_fragmentacion.json`: conteos y longitudes observadas de chunks.
- `evalucacion/preguntas.json`: cinco preguntas de evaluación fijadas manualmente antes de probar retrieval: tres respondibles con una fuente por jurisdicción y dos ausentes del corpus.
- `scripts/02_indexar.py`: indexación local Ollama + Chroma; `tests/test_indexar.py`: validación de metadatos, firmas y contrato de indexación con dobles de prueba (no sustituye una prueba del servicio real).
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
uv run python scripts/00_preprocesar.py
uv run python scripts/01_fragmentar.py
uv run python scripts/02_indexar.py
```

`scripts/02_indexar.py` lee los chunks ya generados, crea `Document` de LangChain, usa `OllamaEmbeddings(model="bge-m3", base_url="http://localhost:11434")` y persiste una colección `electoral_laws` bajo `.chroma/electoral_laws/` (ruta ignorada por Git). Al terminar verifica los IDs/cantidad, informa dimensión sólo si el embedding la devuelve y muestra una inspección semántica de hasta tres fragmentos. Esa consulta sirve para inspeccionar la conexión y el ranking, **no acredita que la respuesta a una pregunta sea correcta**. Las preguntas fijas se evalúan por separado en `evalucacion/` mediante retrieval read-only.

La firma local contiene versión de esquema, nombre de colección, modelo y SHA-256 exacto de `chunks.jsonl`. Una repetición con la misma firma es idempotente (IDs estables y upsert); cambio de modelo o chunks detiene el uso y pide regenerar explícitamente:

```bash
uv run python scripts/02_indexar.py --rebuild
```

`--rebuild` elimina sólo el directorio de índice seleccionado, y se niega a borrar carpetas sin un manifest propio reconocido. También se puede seleccionar ruta/modelo mediante `--index-dir` y `--model`; no se debe cambiar el modelo si se pretende reutilizar el índice. Índice y embeddings se ejecutan localmente; no se consulta un proveedor remoto. Versiones verificadas en este entorno: Ollama `0.40.15`; modelo `bge-m3:latest` (ID `790764642607`, dimensión devuelta 1024); `langchain-chroma 0.2.6`, `langchain-ollama 0.3.10`, `chromadb 1.5.9`, cliente Python `ollama 0.6.3`. En la indexación observada hubo 828/828 IDs únicos y persistidos.

El TXT/PDF no se modifica: el indexador sólo lee `chunks.jsonl`. La conversión omite campos `null` (en particular páginas para TXT) en metadatos Chroma y mantiene rango completo de páginas del artículo PDF, no páginas inventadas por chunk. El indexador no mide precisión ni genera respuestas; esas etapas se validan por separado en los reportes de `evalucacion/`.

## Recuperación semántica y evaluación (TP2-RAG-05)

Con el índice existente y Ollama activo, consulta sin filtro o restringe en Chroma por jurisdicción:

```bash
uv run python scripts/03_recuperar.py --pregunta "¿Qué excepciones al deber de votar establece el Código Electoral Nacional?" --k 5
uv run python scripts/03_recuperar.py --pregunta "¿Cómo define Santa Fe la autoridad de mesa?" --jurisdiccion santa_fe --k 5
uv run python scripts/evaluar_recuperacion.py
```

`--k` debe ser positivo; `--jurisdiccion` acepta `nacional`, `pba`, `santa_fe` como selección manual. La CLI de usuario ahora enruta automáticamente y pide aclaración cuando no puede determinar el alcance; `--sin-filtro` activa explícitamente la consulta exploratoria global. La API de bajo nivel `SemanticRetriever.retrieve()` conserva su comportamiento: filtro explícito o sin filtro, sin inferencia implícita. La capa valida modelo/corpus/manifiesto y abre la colección con creación deshabilitada: no llama al indexador, no agrega ni re-embebe documentos. Distancia nativa Chroma menor significa vecino más cercano, **no** probabilidad de respuesta correcta. El API y el JSON conservan texto completo, ID, fuente, artículo y páginas PDF disponibles; TXT no recibe páginas inventadas. Los resultados negativos también tienen vecinos; retrieval no decide abstención.

La ejecución evaluó una vez cada combinación requerida con k=5. `evalucacion/reporte_recuperacion.json` guarda los rankings completos, métricas por artículo, inspecciones manuales de pasajes realizadas por el agente (pendientes de verificación personal del estudiante), paráfrasis, comparación k=1/k=3, un preview numerado con texto íntegro e integridad del índice. `validacion_recuperacion.md` resume la evidencia; `distancias_recuperacion.svg` grafica distancias reales del top-3. En esta corrida, sin filtro y filtrada, Hit@1/3/5 fueron **0.667** y MRR@5 **0.667** (denominador: tres positivas; las negativas se excluyen). La cobertura de pasaje top-3, inspeccionada manualmente por el agente, fue nacional **parcial**, PBA **sí**, Santa Fe **no** en ambos modos. El índice/article hit no equivale a evidencia completa: el chunk siguiente del art. 12 nacional no aparece en top-5; el art. 4 santafesino no aparece en top-5 aunque sí está en los chunks, y el top vecino es el art. 67. Ver reporte para fuentes, distancias, revisión de preguntas ausentes y limitaciones.

## Generación local (TP2-RAG-06, baseline histórica)

Requiere Ollama en ejecución y el modelo local (sin cambiar ni reconstruir el índice):

```bash
ollama pull granite4:latest
uv run python scripts/04_generar.py --pregunta "¿Cuántos diputados y senadores fija el artículo 13 de la Ley 5.109?" --k 3
uv run python scripts/04_generar.py --pregunta "¿Qué partido ganó la elección presidencial argentina de 2023?" --k 3 --json
uv run python scripts/evaluar_generacion.py
```

El generador reusa `SemanticRetriever`, entrega el contexto completo numerado y muestra las fuentes directamente desde retrieval; usa `ChatOllama` con `granite4:latest`, temperatura 0 y `bge-m3` para consultas. Un chequeo automático detecta referencias faltantes o fuera del mapa, pero **no** verifica apoyo semántico ni garantiza abstención. Las salidas históricas se conservan en `evalucacion/reporte_generacion.json` y `evalucacion/validacion_generacion.md`; corresponden al protocolo previo sin enrutamiento. Desde TP2-RAG-07, `scripts/evaluar_generacion.py` usa `answer_question()` y escribe en `reporte_generacion_enrutada.json` / `validacion_generacion_enrutada.md`, sin sobrescribir ni mezclar el baseline anterior. Versión probada: Ollama server 0.40.15, cliente Python 0.6.3; Granite 4 de 3.4B parámetros, Q4_K_M, digest `4235724a127c0f86dcc0247d67c20148705d6dd2319164014d92f71d607f4773`. El modelo no se incluye en Git y debe descargarse localmente.

## Interfaz Gradio local y laboratorio de fragmentación (Stage C)

Las consultas requieren Ollama activo con `bge-m3` y `granite4:latest` descargados. El modo **Índice original** requiere además el índice compatible ya construido (sección «Índice vectorial local») y `datos/procesados/chunks.jsonl`. El laboratorio usa los tres `*_articulos.jsonl` ya preprocesados; no ejecuta preprocesamiento. Los errores se muestran sin cambiar modelos ni reconstruir índices incompatibles.

```bash
uv sync
uv run python scripts/05_interfaz_gradio.py
```

Abrir la dirección local indicada (`127.0.0.1:7860` por defecto, sin enlace público). Escribir una pregunta, elegir K=1/3/5 (3 por defecto) y jurisdicción automática, Nación, Provincia de Buenos Aires, Santa Fe o sin filtro exploratorio; pulsar **Consultar**. En comparaciones, K se aplica **por jurisdicción**. Cambiar controles no ejecuta consultas.

Se muestran por separado respuesta/aclaración, enrutamiento (incluido índice y parámetros realmente usados), fuentes originales con páginas cuando existen y distancia nativa (no confianza), evidencia literal completa enviada al modelo y advertencias de citas. Una cita sintácticamente válida no verifica respaldo semántico. Las rutas irresueltas no recuperan ni generan.

En **Laboratorio de fragmentación**, seleccionar **Índice experimental**, ajustar `chunk_size` (300–2000 **caracteres, no tokens**) y `chunk_overlap` (entero ≥0 y estrictamente menor que size), y pulsar **Preparar / reutilizar índice experimental**. Los valores iniciales son 1000/150. Cambiar controles no fragmenta, indexa ni genera: limpia los resultados previos y bloquea la consulta experimental hasta preparar los valores exactos. El estado muestra construcción, listo/reutilizado o error, cantidad de chunks y rutas activadas. La primera preparación puede tardar mientras Ollama calcula embeddings.

Cada configuración guarda `chunks.jsonl`, `reporte_fragmentacion.json` e `indice/` bajo `.chroma/experimentos/<sha256>/`, ignorado por Git. La identidad incluye parámetros, modelo fijo `bge-m3`, contenido de los artículos, hash del código de fragmentación y versión del splitter. Una configuración completa compatible se valida y reutiliza **sin recalcular embeddings ni reescribir chunks/reportes**. Si cambia size/overlap, se necesita preparar explícitamente otra fragmentación e índice. Si falla la indexación antes de crear el índice, se pueden reutilizar los chunks completos al reintentar; los artefactos corruptos/incompatibles se rechazan sin borrarlos ni usar `rebuild`.

Para volver, seleccionar **Índice original**: no requiere preparación ni reconstruye nada. Incluso 1000/150 experimental usa rutas privadas, nunca `datos/procesados/chunks.jsonl` ni `.chroma/electoral_laws`. El estado es por sesión; las preparaciones/consultas de esta app se serializan para evitar construcciones simultáneas. No ejecutar múltiples procesos preparando la misma configuración a la vez. Esta etapa no incluye dashboard comparativo ni evaluación automática de calidad.

## Alcance pendiente

Faltan reproducción integral en un directorio fresco, documentación final de asistencia de IA y demo/video. El notebook `trabajo_integrador_2_rag.ipynb` referido en la tarea no está presente en este checkout.

## Enrutamiento conservador por jurisdicción (TP2-RAG-07)

La detección es determinista y no usa LLM, embeddings ni Chroma. Distingue referencias normativas/alcance electoral de la mera ubicación geográfica: p. ej., “presidente en PBA” se enruta a Nación; “¿cómo voto en PBA?” pide aclaración. Reconoce también designaciones normativas como “ley provincial santafesina” como Santa Fe, no como una mera ubicación. Las consultas comparativas recuperan por separado el top-k de cada jurisdicción, conservan rankings locales y renumeran fuentes para el contexto único. Distancias de búsquedas separadas no se comparan entre sí. La selección manual prevalece; las rutas ambiguas, no especificadas o fuera del corpus no consultan el índice ni invocan el modelo. `answer_question()` es la única entrada de generación usada por CLI y evaluaciones; `generate_answer()` se conserva con `DeprecationWarning` sólo por compatibilidad y elude el enrutamiento, por lo que no debe usarse en código nuevo. Este clasificador de reglas no determina vigencia legal ni suficiencia de evidencia.

```bash
# Enrutamiento automático por norma o alcance electoral
uv run python scripts/04_generar.py --pregunta "¿Qué excepciones establece el Código Electoral Nacional?" --k 3
# Selección manual (prevalece sobre detección)
uv run python scripts/04_generar.py --pregunta "¿Cómo voto en Buenos Aires?" --jurisdiccion pba
# Opt-out explícito, exploratorio y sin filtro
uv run python scripts/04_generar.py --pregunta "¿Cómo se vota en PBA?" --sin-filtro
# Ambigua: presenta pregunta aclaratoria sin retrieval/generación
uv run python scripts/04_generar.py --pregunta "¿Cómo se vota en PBA?" --json
# Comparación: k=3 por cada jurisdicción
uv run python scripts/04_generar.py --pregunta "¿Qué diferencias hay entre la Ley 5.109 y la Ley 14.478?" --k 3
# Recuperación/evaluación offline (40 etiquetas); impacto sobre índice local opcional
uv run python scripts/03_recuperar.py --pregunta "¿Cómo se vota presidente en PBA?" --k 3
uv run python scripts/evaluar_jurisdiccion.py
uv run python scripts/evaluar_jurisdiccion.py --with-retrieval
```

El fixture independiente [`evalucacion/preguntas_jurisdiccion.json`](evalucacion/preguntas_jurisdiccion.json) tiene 40 preguntas y SHA-256 `3ef5fa9188caefb85876c531bf95b12a5db9612389b17a08583db5e4f45a06fe`. La clasificación offline observada fue 40/40 exacta (matriz diagonal: identificadas 21, ambiguas 7, comparativas 4, no especificadas 4, no soportadas 4), precisión/recall por jurisdicción 1.00, y aclaración adecuada 15/15. Es el resultado sobre este fixture pequeño y etiquetado, no una medida de desempeño general ni prueba de cobertura de casos nuevos.

En el índice local existente, la comparación usó las mismas tres preguntas respondibles y k=1/3/5. Baseline sin filtro, filtro oracle y filtro automático lograron Hit@1/3/5 **2/3** y MRR@5 **2/3**; el denominador E2E fue 3 en cada condición. El enrutamiento automático cubrió 3/3, no evitó llamadas mediante aclaración en ese subconjunto y no devolvió chunks de otras jurisdicciones (0 fugas). La mejora principal es el aislamiento de contexto, no el hit agregado: el artículo 12 nacional sigue parcialmente cubierto (falta el chunk consecutivo con el inciso d) y el artículo 4 de Santa Fe sigue ausente del top-5 aunque existe en el corpus; PBA recupera el pasaje solicitado. En un smoke comparativo k=1, se recuperaron los arts. PBA 151 y Santa Fe 287, no disposiciones sobre composición legislativa; Granite llamó erróneamente a la Ley 14.478 “Ley de Jueces”. Las citas `[1]`/`[2]` pasaron el control de formato pero no respaldan la conclusión solicitada. En el smoke PBA de 92/46, la respuesta dio el dato correcto pero omitió la cita. Son ejemplos de que el filtro y la validación sintáctica no garantizan relevancia ni apoyo semántico. El índice conservó 828 IDs y el manifest hash antes/después. Resultados íntegros, fuentes/páginas y fragmentos recuperados: [`evalucacion/reporte_jurisdiccion.json`](evalucacion/reporte_jurisdiccion.json), análisis: [`evalucacion/validacion_jurisdiccion.md`](evalucacion/validacion_jurisdiccion.md). Estas mediciones no modifican los reportes congelados TP2-RAG-05/06.

`uv run pytest -q` valida fixture/aritmética y tests de rutas con dobles, sin requerir servicios. El chequeo `--with-retrieval` es read-only y nunca reconstruye el índice. Para generación comparativa se envía el contexto exacto reunido y el mapa `[n]` se renumera globalmente; controles de citas siguen siendo sintácticos, no verifican respaldo semántico. La evaluación de las cinco preguntas fija el protocolo automático y registra ruta, filtro, contexto, respuesta y citas en `reporte_generacion_enrutada.json` / `validacion_generacion_enrutada.md`. La ejecución observada mantuvo íntegro el índice: las dos preguntas ausentes se abstuvieron, pero Nación tuvo contexto parcial, Santa Fe no recuperó el art. 4 y generó una respuesta sin ese pasaje, y PBA respondió 92/46 pero omitió cita. El informe histórico sin enrutamiento permanece en `reporte_generacion.json` / `validacion_generacion.md`.

El agente implementó y ejecutó estas validaciones; no se afirma que el estudiante las haya revisado personalmente, grabado una demo o enviado la entrega. La declaración final de asistencia debe completar cuándo, modelos utilizados y qué verificó personalmente el estudiante.
