# RAG local sobre legislación electoral argentina

**Trabajo Integrador 2 — Procesamiento de Lenguaje Natural (IFTS N.º 24, 2026)**  
Repositorio: [jaymc-arg/PLN_tp2_2026](https://github.com/jaymc-arg/PLN_tp2_2026)

Este proyecto implementa un sistema de **generación aumentada por recuperación (RAG)** para consultar disposiciones del Código Electoral Nacional, la Ley Electoral de la Provincia de Buenos Aires y el Código Electoral de Santa Fe. La aplicación recupera fragmentos de las fuentes **antes** de generar y muestra por separado la respuesta, la procedencia y el **contexto literal enviado al modelo**.

La implementación funciona **localmente**, con Python, Ollama, Chroma y Gradio. No pretende verificar la vigencia de las leyes, reemplazar las fuentes oficiales ni prestar asesoramiento jurídico.

## 1. Problema y destinatario

**Destinatario:** estudiante o persona que necesita estudiar y contrastar legislación electoral de distintas jurisdicciones argentinas.

**Necesidad:** encontrar disposiciones específicas, identificar a qué ley y artículo pertenecen, examinar la evidencia que recupera el buscador y reconocer cuándo la documentación disponible no alcanza para responder.

**Qué permite hacer:** consultar deberes y exenciones electorales, autoridades de mesa, composición legislativa y otras disposiciones **contenidas en los tres textos cargados**; seleccionar una jurisdicción o comparar jurisdicciones expresamente identificadas; inspeccionar textos recuperados, fuentes y advertencias de citas.

**Qué no permite concluir:** quién ganó una elección, cuántos votos obtuvo un candidato, el gasto real de una campaña, la vigencia jurídica actual de una disposición o una interpretación legal definitiva. Esos datos requieren otras fuentes o verificación externa.

## 2. Corpus: documentos reales, alcance y procedencia

Se trabaja con **tres documentos normativos reales** almacenados en [`datos/`](datos/). El corpus comprende Nación, Provincia de Buenos Aires y Santa Fe; no representa toda la legislación electoral argentina.

| Archivo incluido | Documento y organismo emisor indicado | Origen registrado | Fecha o versión indicada en el material | Condición de redistribución |
|---|---|---|---|---|
| [`datos/ley_nacional.txt`](datos/ley_nacional.txt) | Código Electoral Nacional, Ley 19.945; Poder Ejecutivo Nacional | [Normativa nacional](https://www.argentina.gob.ar/normativa/nacional/ley-19945-19442/actualizacion) | Texto con modificaciones anotadas; versión consolidada no acreditada | Ley argentina de dominio público |
| [`datos/ley_pba.txt`](datos/ley_pba.txt) | Ley Electoral 5.109; Legislatura de la Provincia de Buenos Aires | [Normativa bonaerense](https://normas.gba.gob.ar/documentos/VGW7pIWV.html) | El archivo menciona el texto ordenado por Decreto 997/93 y modificaciones posteriores | Ley argentina de dominio público |
| [`datos/ley_sta_fe.pdf`](datos/ley_sta_fe.pdf) | Ley 14.478; Legislatura de la Provincia de Santa Fe | [PDF del Tribunal Electoral de Santa Fe](https://www.santafe.gob.ar/ms/tribunalelectoral/wp-content/uploads/sites/84/2026/09/Texto-Original-Ley-N%C2%B0-14478.pdf) | Texto original; sanción 27/08/2026 y promulgación indicada el 09/09/2026 | Ley argentina de dominio público |

El registro [`datos/fuentes.csv`](datos/fuentes.csv) consigna fecha de recuperación **08/11/2026**, enlaces y preguntas de referencia.

**Inspección del material realizada y registrada:** el preprocesador leyó los dos TXT en UTF-8 y extrajo texto del PDF de Santa Fe con `PyPDFLoader`, sin OCR. Se documentó una inspección representativa de la extracción y un seguimiento del artículo 4 de Santa Fe a través de las páginas **1–4**.

La extracción registrada identificó **208 artículos nacionales, 155 bonaerenses y 296 santafesinos**. El sistema conserva también las notas editoriales, duplicaciones de numeración, tramos fuera de artículo y advertencias, sin inferir qué disposiciones están jurídicamente vigentes. Véase [`evalucacion/validacion_preprocesamiento.md`](evalucacion/validacion_preprocesamiento.md).

**Unidad de análisis:** primero se reconoce cada **artículo** con sus metadatos (jurisdicción, ley, número, archivo y rango de páginas si proviene de PDF); después se generan fragmentos dentro de ese artículo. Un artículo largo puede ocupar varios fragmentos.

## 3. Arquitectura: del documento a la respuesta

```text
Tres archivos reales en datos/
    ↓
00_preprocesar.py: lectura, inspección, artículos y procedencia
    ↓
01_fragmentar.py: vista indexable y chunks por artículo
    ↓
02_indexar.py: embeddings Ollama → índice local Chroma
    ↓
Pregunta del usuario → detector conservador de jurisdicción
    ↓
03_recuperar.py: embedding de la pregunta con EL MISMO MODELO
    ↓
Top-K fragmentos (por jurisdicción) + fuente, artículo y página disponible
    ↓
04_generar.py: contexto numerado → prompt → Granite vía Ollama
    ↓
05_interfaz_gradio.py: respuesta + enrutamiento + fuentes + contexto + citas
```

| Componente | Función en el pipeline |
|---|---|
| [`scripts/00_preprocesar.py`](scripts/00_preprocesar.py) | Extrae y segmenta los documentos en artículos, preservando el texto completo, las anotaciones y la procedencia. |
| [`scripts/01_fragmentar.py`](scripts/01_fragmentar.py) | Genera los fragmentos indexables mediante `RecursiveCharacterTextSplitter`, sin mezclar artículos. |
| [`scripts/02_indexar.py`](scripts/02_indexar.py) | Valida los chunks, crea embeddings locales, persiste Chroma y comprueba compatibilidad de índice/modelo/corpus. |
| [`scripts/03_recuperar.py`](scripts/03_recuperar.py) | Busca vecinos en Chroma, opcionalmente filtra por jurisdicción y devuelve texto íntegro, ranking, distancia y metadatos. |
| [`scripts/03_bis_detectar_jurisdiccion.py`](scripts/03_bis_detectar_jurisdiccion.py) | Identifica jurisdicción por reglas textuales explícitas y pide aclaración cuando no puede asignarla con seguridad. |
| [`scripts/04_generar.py`](scripts/04_generar.py) | Construye el contexto y el prompt con citas numeradas; genera y verifica únicamente el formato/existencia de las citas. |
| [`scripts/05_interfaz_gradio.py`](scripts/05_interfaz_gradio.py) | Presenta la consulta y sus cinco salidas; permite ensayar otra fragmentación mediante índices experimentales aislados. |
| [`scripts/experimentos_fragmentacion.py`](scripts/experimentos_fragmentacion.py) | Crea o reutiliza índices identificados por corpus, modelo, parámetros y versión del divisor, sin sobrescribir el original. |

### Modelos, parámetros y versiones de referencia

| Componente | Configuración de la versión principal |
|---|---|
| Python | 3.12 (registro experimental: 3.12.7) |
| Embeddings de indexación **y consulta** | `qwen3-embedding:0.6b` vía Ollama, cuantización Q8_0; 1024 dimensiones registradas |
| Modelo generador | `granite4:latest` vía Ollama, temperatura `0` |
| Embeddings históricos comparados | `bge-m3` (requiere su **propio índice** Chroma y flag adicional) |
| Fragmentación base | `chunk_size=1000`, `chunk_overlap=150`, medidos en **caracteres**, no tokens |
| Fragmentación experimental | `600/80` caracteres; otros valores ajustables en Gradio |
| Índice base persistente | `.chroma/electoral_laws_qwen3_0_6b`, colección `electoral_laws` |
| Interfaz | Gradio local en `127.0.0.1:7860` |

Entorno del experimento registrado: **Ollama 0.40.15**, `langchain-chroma 0.2.6`, `langchain-ollama 0.3.10`, `chromadb 1.5.9` y cliente Python `ollama 0.6.3`. Las dependencias del proyecto están definidas en `pyproject.toml`, fijadas en `uv.lock` y exportadas también en `requirements.txt`; las versiones que cada usuario instale pueden depender del procedimiento de instalación elegido.

## 4. Instalación y ejecución local

### Requisitos

- Git, **Python 3.12**, [`uv`](https://docs.astral.sh/uv/) y [Ollama](https://ollama.com/) instalados.
- Acceso a Internet **solo para descargar** dependencias y modelos.
- Espacio en disco para modelos e índices. Se puede ejecutar en CPU, aunque el cálculo de embeddings y la generación pueden resultar lentos.
- Ejecutar todos los comandos desde la **raíz del repositorio**. Los ejemplos usan Bash/Zsh.

### Paso 1. Obtener el proyecto y el entorno

```bash
git clone https://github.com/jaymc-arg/PLN_tp2_2026.git
cd PLN_tp2_2026
uv sync
```

`uv sync` crea/administra `.venv` e instala las dependencias declaradas. No es necesario activar el entorno al utilizar `uv run`. Si se prefiere seguir la instalación con el `requirements.txt` exigido en la entrega:

```bash
uv venv --python 3.12
uv pip install -r requirements.txt
```

### Paso 2. Descargar los modelos locales

Si Ollama no se encuentra ejecutándose, iniciar su servicio en otra terminal:

```bash
ollama serve
```

Descargar los modelos de la configuración principal:

```bash
ollama pull qwen3-embedding:0.6b
ollama pull granite4:latest
ollama list
```

La consigna de clase menciona `bge-m3`: es una alternativa permitida si se justifica. Este proyecto utiliza **Qwen3 Embedding 0.6B** por defecto y registra una comparación contra BGE-M3. Para probar la alternativa:

```bash
ollama pull bge-m3
```

**No se deben mezclar** vectores producidos por Qwen con consultas realizadas mediante BGE-M3 ni reutilizar el índice de uno para el otro.

### Paso 3. Crear el índice local desde los chunks versionados

Para iniciar con la configuración principal, **no es obligatorio repetir el preprocesamiento** porque `datos/procesados/chunks.jsonl` ya está disponible en el repositorio.

```bash
uv run python scripts/02_indexar.py \
  --chunks datos/procesados/chunks.jsonl \
  --index-dir .chroma/electoral_laws_qwen3_0_6b \
  --model qwen3-embedding:0.6b \
  --smoke-question "¿Qué excepciones establece el artículo 12 del Código Electoral Nacional?"
```

La ejecución registrada con fragmentación base produjo **828 chunks**. El indexador comprueba identificadores y metadatos y hace una consulta de inspección. Este número es un resultado de referencia del corpus versionado, no una garantía ante cambios futuros.

### Paso 4. Ejecutar Gradio

```bash
uv run python scripts/05_interfaz_gradio.py
```

Abrir **http://127.0.0.1:7860**. Escribir una pregunta, elegir `K` (1, 3 o 5), seleccionar jurisdicción automática, manual o sin filtro y pulsar **Consultar**.

La interfaz presenta **cinco salidas independientes**: **respuesta**, **enrutamiento**, **fuentes recuperadas**, **contexto literal completo enviado al modelo** y **control sintáctico de citas**. Los documentos TXT muestran ley/artículo/archivo sin páginas inventadas; el PDF santafesino muestra el rango de páginas del artículo, que **no equivale necesariamente a la página exacta de cada chunk**.

La modalidad **Índice original** utiliza los valores Qwen 1000/150 del código. Las variables de shell de otros ejemplos **no cambian el modelo que usa Gradio**. La interfaz no ofrece actualmente un selector dinámico de modelos; las pruebas con BGE se ejecutan con las CLIs y un índice diferente.

### Paso 5. Consultar también por terminal (opcional)

Solo recuperar la evidencia, sin generación:

```bash
uv run python scripts/03_recuperar.py \
  --pregunta "¿Qué excepciones establece el Código Electoral Nacional?" \
  --k 5 --jurisdiccion nacional \
  --chunks datos/procesados/chunks.jsonl \
  --index-dir .chroma/electoral_laws_qwen3_0_6b \
  --model qwen3-embedding:0.6b
```

Recuperar y generar, mostrando el JSON completo:

```bash
uv run python scripts/04_generar.py \
  --pregunta "Según el artículo 13 de la Ley 5.109, ¿cuántos diputados y senadores hay?" \
  --k 3 --jurisdiccion pba --json \
  --chunks datos/procesados/chunks.jsonl \
  --index-dir .chroma/electoral_laws_qwen3_0_6b \
  --embedding-model qwen3-embedding:0.6b --model granite4:latest
```

En `02_indexar.py` y `03_recuperar.py`, `--model` designa el **modelo de embeddings**; en `04_generar.py` designa el **generador** y `--embedding-model` selecciona el embedding. Sin jurisdicción manual, la aplicación usa el detector conservador: ante una pregunta ambigua solicita precisión en lugar de consultar una jurisdicción arbitraria.

## 5. Reindexación y experimentos reproducibles

El índice Chroma (`.chroma/`) es un **artefacto local derivado**: no debe versionarse. Se puede reconstruir a partir de los documentos y scripts publicados. La firma del índice comprueba el modelo y SHA-256 del archivo de fragmentos, y rechaza una combinación incompatible.

### Reconstruir la cadena desde los documentos originales

Para no sobrescribir los artículos procesados ni el índice base:

```bash
uv run python scripts/00_preprocesar.py \
  --entrada datos --salida .chroma/reconstruccion/procesados

uv run python scripts/01_fragmentar.py \
  --entrada .chroma/reconstruccion/procesados \
  --salida .chroma/reconstruccion/chunks.jsonl \
  --chunk-size 1000 --chunk-overlap 150

uv run python scripts/02_indexar.py \
  --chunks .chroma/reconstruccion/chunks.jsonl \
  --index-dir .chroma/reconstruccion/indice \
  --model qwen3-embedding:0.6b
```

Esto vuelve a ejecutar extracción, reconocimiento de artículos, fragmentación e indexación. La extracción del PDF usa texto digital y **no realiza OCR**. Si cambia un documento, el corte o el modelo, se debe construir un índice correspondiente a la nueva configuración y mantener juntos **ruta de chunks + ruta de índice + modelo**.

`--rebuild` en el indexador **elimina el índice del directorio seleccionado**, con controles para impedir borrar directorios no reconocidos; no debe utilizarse indiscriminadamente. Para comparar variantes se recomienda un nuevo directorio.

### Laboratorio de fragmentación en Gradio

En **Índice experimental**, ajustar `chunk_size` (300–2000 caracteres) y `chunk_overlap` (entero entre 0 y menor que el tamaño), y pulsar **Preparar / reutilizar índice experimental**. Cambiar los controles no genera índices por sí solo. Los archivos del experimento quedan bajo `.chroma/experimentos/<identificador>/` y no reemplazan el índice base. El identificador toma en cuenta parámetros, modelo, contenidos de entrada y versión/código del divisor.

### Comparar dos configuraciones sin cambiar corpus, modelo ni preguntas

El experimento del repositorio compara **1000/150** con **600/80**, ambos con Qwen3 Embedding y Granite 4, y el **mismo conjunto fijo de 38 preguntas**. Se ejecutó con índices aislados; la comparación conserva los rankings y las salidas generadas.

- Informe principal: [`evalucacion/experimentos_fragmentacion/comparacion_qwen_600_80_vs_1000_150.md`](evalucacion/experimentos_fragmentacion/comparacion_qwen_600_80_vs_1000_150.md).
- Runner: [`scripts/evaluar_fragmentacion_pareada.py`](scripts/evaluar_fragmentacion_pareada.py).
- Para inspeccionar resultados existentes no es necesario recalcular embeddings ni generar respuestas.

Para crear o reanudar una ejecución real:

```bash
uv run python scripts/evaluar_fragmentacion_pareada.py --ejecutar
```

**Atención:** la ejecución puede escribir artefactos y retomar casos previamente guardados. Para una corrida completamente separada, utilizar otro directorio con `--salida`. La revisión semántica no se deduce automáticamente de Hit@K: corresponde leer las respuestas y fragmentos de la ejecución concreta.

## 6. Pruebas: resultados observados y fallas del sistema

### Conjunto de evaluación

El conjunto **actual** es [`evalucacion/preguntas.json`](evalucacion/preguntas.json), versión 2, con **38 casos: 32 respondibles y 6 preguntas sin respuesta en el corpus**, incluidas dos comparativas. Los **cinco casos originales** (tres respondibles, uno por documento, y dos ausentes) se mantienen identificables dentro de ese conjunto, pero **los evaluadores históricos** `evaluar_recuperacion.py` y `evaluar_generacion.py` están diseñados para el antiguo protocolo de cinco casos; no se les debe pasar el fixture actual de 38 como si fuera compatible.

### Cinco preguntas exigidas por la consigna

La tabla siguiente resume **salidas realmente registradas** para el experimento principal **Qwen 1000/150, Granite, K=3 con enrutamiento/filtro indicado por el ensayo**. «Evidencia esperada» y «evidencia recuperada» son conceptos distintos. El resultado por pregunta y sus trazas completas figuran en el [informe pareado](evalucacion/experimentos_fragmentacion/comparacion_qwen_600_80_vs_1000_150.md), no en una ejecución nueva realizada para este README.

| Pregunta | Respuesta / fuente esperada | Fragmentos recuperados (archivo y página si existe) | Qué hizo el generador | Observación / diagnóstico |
|---|---|---|---|---|
| **Nación:** ¿Qué excepciones al deber de votar enumera el art. 12 del Código Electoral Nacional? | Art. 12, `ley_nacional.txt`: causales a–d, condiciones y carácter optativo. | `nacional_19945_art_12__chunk_0001`, de `ley_nacional.txt` (TXT sin página). No llegó su continuación pertinente dentro de K=3. | Contestó **parcialmente**, con referencias, pero omitió parte de las causales y condiciones. | **Fragmentación + recuperación:** acertar el artículo no garantiza disponer de todo el pasaje. |
| **PBA:** según el art. 13 de la Ley 5.109, ¿cuántos diputados y senadores integran la representación legislativa? | Art. 13, `ley_pba.txt`: **92 diputados y 46 senadores** en el texto principal. | `pba_5109_art_13__chunk_0001`, de `ley_pba.txt` (TXT sin página), en el primer rango. | Informó correctamente **92/46**, pero sin la cita numerada requerida. | **Generación/citas:** el contenido correcto no implica trazabilidad formal correcta. |
| **Santa Fe:** ¿cómo define el art. 4 de la Ley 14.478 a la autoridad de mesa? | Definición del art. 4, `ley_sta_fe.pdf`, páginas del artículo **1–4**. | Con Qwen 1000/150, el artículo esperado apareció en **rango 4** en la recuperación filtrada; quedó fuera del contexto **K=3**. Entraron otros artículos relacionados. | Produjo una respuesta **parcialmente respaldada**, sin reproducir de forma suficiente el pasaje solicitado. | **Recuperación:** un vecino próximo sobre autoridades no sustituye la definición del artículo preguntado. |
| **Sin respuesta 1:** ¿qué partido ganó la presidencial argentina de 2023 y cuántos votos obtuvo? | **No disponible:** el corpus contiene normas, no resultados electorales. | Chroma devolvió vecinos sobre legislación electoral, **no** actas/resultados oficiales; no había fuente válida para ese dato. | Se **abstuvo correctamente** en el ensayo registrado. | La presencia de chunks no convierte una pregunta en respondible. |
| **Sin respuesta 2:** ¿cuánto gastó efectivamente cada partido en la campaña presidencial de 2023? | **No disponible:** faltan rendiciones efectivas de campaña. | Se recuperaron reglas normativas de financiamiento/gastos, **no** montos realmente ejecutados por partido. | Se **abstuvo correctamente** en el ensayo registrado. | Un límite legal de gasto no prueba el gasto real; la abstención no está garantizada para otras preguntas. |

**Nota sobre páginas:** para Santa Fe, los rangos son los asociados al **artículo de origen**; no existe un mapeo validado de la página exacta dentro de cada chunk. Para los TXT no se publican páginas inexistentes. El JSON de ejecución permite consultar los `chunk_id` completos, el orden de recuperación, el contexto y el texto original generado.

### Comparación cuantitativa de fragmentación: 1000/150 frente a 600/80

| Métrica del ensayo de 38 casos | Qwen 1000/150 | Qwen 600/80 |
|---|---:|---:|
| Fragmentos indexados | 828 | 1.119 |
| Hit@3 por pregunta positiva (artículos esperados) | 31/32 (96,88 %) | 32/32 (100 %) |
| Evidencia completa dentro de K=3 | 28/32 (87,50 %) | 25/32 (78,12 %) |
| Respuestas estrictamente respaldadas | 8/32 (25 %) | 12/32 (37,50 %) |
| Respuestas factualmente completas | 13/32 (40,63 %) | 16/32 (50 %) |
| Abstenciones correctas en preguntas negativas | 5/6 (83,33 %) | 5/6 (83,33 %) |

Las tasas de cobertura y apoyo de respuesta provienen de una **revisión de las trazas realizada por un agente de código**, no de una revisión jurídica independiente ni de una validación personal declarada por el estudiante. Hay una etiqueta de incertidumbre en el brazo 1000/150. **No se puede concluir que 600/80 sea universalmente mejor:** recupera más artículos esperados entre los tres primeros, pero con menor proporción de pasajes completos. Una respuesta respaldada exige contenido suficiente **y** citas semánticamente pertinentes; Hit@3 mide otra cosa.

Para los resultados históricos de recuperación con solo cinco preguntas, ver [`evalucacion/validacion_recuperacion_qwen3_0_6b.md`](evalucacion/validacion_recuperacion_qwen3_0_6b.md), [`evalucacion/validacion_recuperacion.md`](evalucacion/validacion_recuperacion.md) y los JSON asociados. **No mezclar sus denominadores con las 38 preguntas actuales.** Los informes históricos de generación con BGE también tienen otro protocolo y no representan una nueva evaluación de Granite+Qwen.

### Pruebas de código y reproducción de una limitación

```bash
uv run pytest -q
```

Las pruebas usan dobles en componentes que lo requieren, por lo que **aprobar pytest no demuestra precisión del RAG ni que Ollama esté funcionando**. La última ejecución completa **registrada** en el README original informó `171 passed`, con avisos de compatibilidad; ese resultado histórico no equivale a haber ejecutado las pruebas en otra máquina o sobre cambios posteriores.

**Falla concreta para demostrar:** al preguntar por *todas* las exenciones del artículo 12 nacional, el recuperador encuentra el artículo correcto, pero el fragmento enviado no contiene la continuación con la causal restante y el carácter optativo. El generador responde de forma incompleta aunque cite un artículo pertinente. Esto diferencia una **falla de cobertura de contexto** de una mera falla de formato de citas. El ensayo con menor tamaño de chunks tampoco garantiza recuperar esa continuación. Una mejora posible sería favorecer la recuperación de fragmentos contiguos **del mismo artículo**, sujeta a una nueva comparación controlada de evidencia y respuestas; no es una función implementada en el estado documentado.

## 7. Decisiones técnicas y límites

### Por qué la fragmentación respeta artículos

Las leyes tienen encabezados, incisos, definiciones y notas editoriales. Cortar todo el documento como una secuencia única permitiría que un chunk mezcle artículos con reglas o jurisdicciones distintas. Por eso el preprocesador construye artículos y el divisor trabaja **dentro** de cada uno, conservando su identificación. Los artículos breves pueden quedar completos; los extensos se parten. La vista indexable normaliza saltos visuales del PDF y distingue determinadas notas editoriales, **sin reescribir las normas**. Este método no garantiza que una enumeración extensa entre completa en un único chunk.

`chunk_size` y `chunk_overlap` se cuentan en **caracteres de Python**. El corte usa `RecursiveCharacterTextSplitter` (separadores recursivos, no una cantidad fija de palabras) y el overlap intenta preservar contexto entre fragmentos. Los tamaños elegidos son hipótesis que se compararon experimentalmente, no constantes óptimas demostradas.

### Por qué Qwen y qué significa K

El laboratorio de clase utiliza `bge-m3` como referencia. Aquí se eligió `qwen3-embedding:0.6b` como default y se documentó una comparación con BGE usando el **mismo corpus y los mismos chunks**. Esa comparación histórica de cinco casos mostró una mejora acotada de Qwen en Hit@5 con filtro para una pregunta santafesina, sin mejora de Hit@3; **no prueba superioridad general**. Cada modelo necesita su propio índice, aunque dos modelos puedan devolver vectores con la misma dimensión.

`K` determina cuántos fragmentos vecinos se envían como evidencia. En una comparación entre dos jurisdicciones se recuperan **K por jurisdicción**. Pedir más vecinos puede recuperar información necesaria, pero también introducir ruido; Chroma puede devolver vecinos incluso cuando la respuesta no aparece en el corpus. **La distancia vectorial no es una probabilidad de verdad**, y no se aplica un umbral universal de abstención.

### Prompt, citas y abstención

La generación usa `ChatPromptTemplate` y `ChatOllama` local. El prompt exige respuestas en español fundadas en el contexto, distinción entre jurisdicciones, citas `[1]`, `[2]`, etc. y una fórmula explícita de abstención si falta información. La temperatura se fija en cero para reducir variación, **sin garantizar determinismo ni exactitud**.

Las fuentes que se ven en Gradio provienen de los **resultados realmente recuperados**, no de citas libres inventadas por el LLM. El chequeo programático detecta referencias ausentes, malformadas o inexistentes en el mapa, pero **no valida que una afirmación concreta esté semánticamente respaldada**. Las respuestas pueden omitir citas, omitir datos o atribuir contenido de otra fuente. La instrucción de abstención tampoco garantiza un rechazo correcto en todos los casos.

### Enrutamiento y cobertura del corpus

Las reglas de jurisdicción distinguen referencias explícitas a Nación, PBA y Santa Fe, reconocen comparaciones y devuelven aclaraciones ante ambigüedad. Por ejemplo, una ubicación geográfica no basta siempre para saber si se pregunta por la elección nacional o provincial. El detector es específico para este corpus: no debe interpretarse como clasificador legal universal.

No hay OCR automático, recuperación híbrida lexical garantizada en estos scripts ni verificador jurídico externo. La vigencia de artículos observados/derogados no se resuelve automáticamente. Para el PDF se conservan **rangos de página por artículo**, no localizaciones precisas de cada frase; para TXT no existen páginas originales. Los experimentos de código o el agente no sustituyen la comprobación directa del texto legal.

## 8. Declaración de asistencia de inteligencia artificial

Se utilizó asistencia de IA durante el desarrollo. Conforme al historial documentado en [`bitacora.md`](bitacora.md), su intervención comprendió **planificación y delimitación**, **implementación y revisión de scripts**, **preparación de pruebas y experimentos**, **interpretación preliminar de salidas** y **documentación**. Las tareas abarcan las etapas de preprocesamiento, fragmentación, indexación, recuperación, generación, interfaz y evaluación; no se utilizaron modelos generativos externos para responder consultas del RAG operativo.

| Uso de IA | Momento / función | Modelo identificado en el registro | Estado de la verificación |
|---|---|---|---|
| Agente de desarrollo asistido | Implementación, pruebas, depuración e informes durante el trabajo de noviembre de 2026 | En la bitácora se identifica al menos una sesión como `gpt-6.1-sol` | La ejecución y revisión del **agente** están registradas; no equivalen a validación personal independiente. |
| Otras sesiones de asistencia conversacional o de código | Diseño de experimentos, análisis, instrucciones y documentación | **[COMPLETAR: nombres/versiones de los modelos efectivamente utilizados y momentos]** | **[COMPLETAR: qué se comprobó personalmente]** |
| Embeddings de la aplicación | Indexación y búsqueda, no autoría del código | `qwen3-embedding:0.6b`; histórico `bge-m3` | Se registran modelo, parámetros y ejecución. |
| Generación de respuestas del RAG | Respuestas sobre el corpus local | `granite4:latest` | Sus respuestas fueron ensayadas y sus limitaciones figuran en los reportes. |

**Declaración personal pendiente de completar antes de entregar:** indicar qué fuentes originales se abrieron y cotejaron personalmente, qué comandos se ejecutaron en el propio entorno, cuáles de las cinco preguntas se revisaron contra el documento original, qué errores se observaron y qué cambios fueron aceptados. No atribuir al estudiante inspecciones que solamente aparecen registradas como realizadas por un agente.

## 9. Reproducibilidad, solución de problemas y entrega

| Situación | Acción o límite relevante |
|---|---|
| Ollama no responde | Comprobar servicio y `ollama list`; descargar el tag exacto solicitado. No existe un cambio de modelo automático. |
| Falta el índice o su `index_manifest.json` | Ejecutar explícitamente `scripts/02_indexar.py` usando chunks, índice y embedding compatibles. La consulta no reconstruye el índice. |
| Firma de índice incompatible | El corpus o modelo no corresponde al índice. Usar una ruta de índice nueva en lugar de mezclar vectores o borrar un baseline. |
| Gradio indica laboratorio no preparado | Pulsar **Preparar / reutilizar índice experimental** después de modificar tamaño/overlap. |
| La consulta pide aclaración | Indicar la ley, tipo de elección o jurisdicción; una ambigüedad no equivale a falla de Ollama. |
| El modelo respondió sin cita o con una cita dudosa | Revisar `context_sent`, `source_map` y el documento original; validación sintáctica no implica apoyo semántico. |
| El PDF es ilegible o escaneado | Este pipeline no incluye OCR; se requeriría obtener texto extraíble y documentar su verificación. |

**Antes de presentar el trabajo:**

- [ ] Comprobar que el repositorio es accesible y contiene los tres documentos reales que efectivamente se indexaron.
- [ ] **Verificar los enlaces oficiales y las condiciones de redistribución** de cada fuente; corregir o reemplazar las fuentes si corresponde.
- [ ] Clonar en una **carpeta nueva**, ejecutar `uv sync`, descargar modelos, construir Chroma y abrir Gradio con los comandos de este README.
- [ ] Comprobar personalmente las **tres preguntas respondibles y dos ausentes** y contrastar la fuente con el texto original.
- [ ] Completar el detalle de **modelos de IA utilizados**, momentos de asistencia y verificación personal en la sección 8.
- [ ] Grabar un video de **hasta cinco minutos** que muestre el corpus, la aplicación, una respuesta con sus fragmentos y **una limitación real**.
- [ ] Subir el video a Drive y verificar sus permisos; presentar el formulario desde el correo institucional antes del **miércoles 18/11/2026 a las 12:00**.
- [ ] **No publicar DNI, credenciales, `.env`, `.venv/` ni los índices `.chroma/`.** El DNI pertenece únicamente al formulario institucional.

El material entregado incluye instrucciones para reconstruir el índice, pero la disponibilidad de los documentos en GitHub y la reproducibilidad en una instalación limpia **no prueban por sí solas** autenticidad jurídica, permisos de redistribución ni que el sistema responda siempre correctamente.
