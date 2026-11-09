# Bitácora de desarrollo — Trabajo Integrador 2 de PLN

**Proyecto:** RAG para consulta y comparación de legislación electoral argentina  
**Materia:** Procesamiento de Lenguaje Natural — Tecnicatura Superior en Ciencia de Datos e Inteligencia Artificial, IFTS N.º 24  
**Repositorio:** [jaymc-arg/PLN_tp2_2026](https://github.com/jaymc-arg/PLN_tp2_2026)  
**Período documentado:** inicio del proyecto al **8 de noviembre de 2026**  
**Estado:** corpus seleccionado, extraído, estructurado y fragmentado; **todavía no se implementaron ni evaluaron la recuperación vectorial ni la generación de respuestas**.

> **Propósito de esta bitácora.** Registrar las decisiones, los problemas encontrados, las correcciones realizadas y la evidencia que permite comprobarlas. No es un manual de instalación ni un registro exhaustivo de comandos del agente. Se ampliará a medida que avance el trabajo y se obtengan resultados del sistema RAG.

## 1. Problema elegido y delimitación

El proyecto busca que una persona interesada en normativa electoral pueda localizar y contrastar disposiciones de **Nación, provincia de Buenos Aires y Santa Fe**, identificando la jurisdicción, la norma y el artículo que respaldan la información recuperada. El propósito es facilitar la **consulta documental verificable**, no proporcionar asesoramiento jurídico ni determinar por cuenta del sistema la vigencia de todas las normas relacionadas.

Se eligió un corpus acotado de **tres documentos reales de organismos oficiales**, con diferencias de formato y de estructura normativa:

| Jurisdicción | Fuente | Formato incorporado | Procedencia |
|---|---|---|---|
| Nación | Código Electoral Nacional, Ley 19.945 (texto actualizado) | `datos/ley_nacional.txt` | [InfoLEG](https://www.argentina.gob.ar/normativa/nacional/ley-19945-19442/actualizacion) |
| Buenos Aires | Ley Electoral 5.109 (texto actualizado) | `datos/ley_pba.txt` | [Sistema de Información Normativa provincial](https://normas.gba.gob.ar/documentos/VGW7pIWV.html) |
| Santa Fe | Código Electoral y de Partidos Políticos, Ley 14.478 (texto original de 2026) | `datos/ley_sta_fe.pdf` | [Tribunal Electoral de Santa Fe](https://www.santafe.gob.ar/ms/tribunalelectoral/wp-content/uploads/sites/84/2026/09/Texto-Original-Ley-N%C2%B0-14478.pdf) |

**Decisión de alcance:** trabajar con los textos completos seleccionados y no descargar indiscriminadamente todas las leyes modificatorias y reglamentaciones a las que remiten. Las referencias a otras normas se conservan como datos de procedencia; una pregunta que necesite el contenido de una norma ausente deberá reconocerse como **fuera del alcance del corpus**.

## 2. Proceso realizado y decisiones

### Etapa 1 — Ingesta y estructuración por artículos (`TP2-RAG-01`)

**Problema inicial.** Las tres fuentes no podían enviarse sin más al modelo de embeddings: dos eran copias de textos legales en TXT y la tercera un PDF de 70 páginas. Incluían encabezados, capítulos, notas de actualización, referencias a otras normas, artículos largos y, en Santa Fe, artículos que continuaban en varias páginas.

**Decisiones y acciones:**

1. **Preservar el material original.** Los archivos de entrada se mantienen en `datos/`; los derivados se escriben en `datos/procesados/`. Se registra el SHA-256 de cada fuente para detectar modificaciones.
2. **Aplicar una limpieza conservadora.** Se normalizan espacios y elementos de maquetación, sin corregir la redacción legal, eliminar incisos ni aplicar lematización o eliminación de palabras frecuentes.
3. **Aprovechar el texto extraíble del PDF.** Santa Fe se procesó mediante `PyPDFLoader`, sin OCR. Se retiraron **140 elementos repetitivos** de encabezado y numeración de página (dos por cada una de las 70 páginas), dejando registro de cada retiro en la auditoría.
4. **Usar el artículo como unidad documental.** Antes de generar chunks se identifican artículos y contexto de libro, título y capítulo. Cada artículo conserva jurisdicción, ley, identificador, fuente y páginas cuando corresponda. Los encabezados, prefacios y firmas que no son artículos se preservan en segmentos separados.
5. **Distinguir articulado y anotaciones.** Cada registro conserva `texto` íntegro y `texto_principal` como vista auxiliar sin determinadas notas editoriales, además de `notas` y `referencias_externas`.

**Fallo detectado durante las pruebas.** Una remisión a `artículo 172.` al comienzo de una línea de la página 45 de Santa Fe fue interpretada inicialmente como una nueva rúbrica dentro del artículo 173. Se corrigió la detección según la forma de los encabezados presentes en estas fuentes y se incorporó una prueba de regresión. El resultado final reconoce **296 artículos**, sin crear uno artificial por esa referencia interna.

**Evidencia:** [`preprocesar.py`](preprocesar.py), [`tests/test_preprocesar.py`](tests/test_preprocesar.py), [`reporte_preprocesamiento.json`](datos/procesados/reporte_preprocesamiento.json) y los tres archivos `*_articulos.jsonl`.

### Etapa 2 — Tratamiento de modificaciones normativas (`TP2-RAG-02`)

**Problema observado.** No todas las transcripciones entre comillas tienen el mismo significado: algunas reproducen antecedentes históricos y otras son el contenido sustantivo de artículos que modifican otras leyes. Una clasificación uniforme podía ocultar información pertinente o incorporar propuestas observadas como si fueran texto principal.

**Caso de Buenos Aires, artículo 13.** El TXT contiene el artículo 13 de la Ley 5.109, con **92 diputados y 46 senadores**, seguido de una nota que transcribe el artículo 26 de la Ley 14.086, que proponía **100 diputados y 50 senadores**, modificación observada por el Decreto 2997/2009. **Decisión:** conservar la nota y la transcripción en `texto`/`notas`, pero no incluirlas en `texto_principal`. El artículo 26 transcripto pertenece a otra ley y no debe confundirse con el artículo 26 propio de la Ley 5.109.

**Caso de Santa Fe, artículos 285 a 290.** Esos artículos introducen nuevas redacciones de disposiciones de otras leyes y reproducen el texto sustituto entre comillas. La primera versión del procesador clasificaba esas citas como transcripciones prescindibles y las retiraba de `texto_principal`. **Corrección:** etiquetarlas como `texto_modificatorio` y conservarlas también en la vista principal. Se comprobó que los seis artículos conservan la redacción completa.

**Límite asumido.** La anotación del artículo 25 bonaerense remite a un subrayado que no sobrevivió al copiado como TXT. Se decidió mantener la advertencia sin reconstruir arbitrariamente el tramo observado. La detección de anotaciones no reemplaza una interpretación jurídica de su vigencia.

**Evidencia:** clasificación implementada en [`preprocesar.py`](preprocesar.py), registros de los artículos citados y pruebas específicas en [`tests/test_preprocesar.py`](tests/test_preprocesar.py).

### Etapa 3 — Fidelidad documental y fragmentación (`TP2-RAG-03`)

**Problema 1: numeración duplicada en PBA.** La fuente bonaerense incluye **dos apariciones del artículo 151**, con contenidos diferentes y una nota sobre la numeración del texto ordenado. Durante una edición manual se había retirado la segunda aparición, reduciendo temporalmente el conteo de 155 a 154. **Corrección:** se recuperó literalmente desde el historial de Git; el procesador volvió a generar 155 registros y asignó identificadores distintos (`pba_5109_art_151` y `pba_5109_art_151__2`) sin inventar numeración jurídica.

**Problema 2: encabezados especiales.** Algunos títulos y capítulos de Santa Fe aparecen como `TÍTULO ÚNICO` o `CAPÍTULO ÚNICO`. Inicialmente podían quedar agrupados en el campo incorrecto. **Corrección:** se amplió el reconocimiento de encabezados, preservando separados los niveles estructurales.

**Problema 3: longitud variable de los artículos.** La unidad jurídica no coincide siempre con un tamaño adecuado para embeddings. Por ejemplo, los artículos 4 y 54 de Santa Fe son extensos. **Decisión:** fragmentar **dentro de cada artículo**, sin concatenar indiscriminadamente artículos o jurisdicciones. Se utilizó `RecursiveCharacterTextSplitter` con tamaño objetivo de **1.000 caracteres** y solapamiento configurado de **150 caracteres**, manteniendo el identificador del artículo y los metadatos en cada fragmento.

El script [`fragmentar.py`](fragmentar.py) genera una representación para búsqueda que repara saltos de línea visuales del PDF **sin alterar los registros originales**. También conserva los textos modificatorios sustantivos y evita indexar artículos nacionales derogados como encabezados vacíos: en esos casos utiliza una descripción expresamente derivada de la nota de derogación de la fuente.

**Observación sobre el solapamiento.** El valor 150 es un parámetro del splitter, no una garantía de 150 caracteres repetidos en todos los límites. Una inspección posterior encontró **112 límites sin repetición literal entre 169 pares de chunks consecutivos** de un mismo artículo. No se interpretó automáticamente como defecto; corresponde examinar su efecto sobre la recuperación en la etapa siguiente.

**Evidencia:** [`fragmentar.py`](fragmentar.py), [`chunks.jsonl`](datos/procesados/chunks.jsonl) y [`reporte_fragmentacion.json`](datos/procesados/reporte_fragmentacion.json).

## 3. Resultados medibles al cierre de esta etapa

| Indicador | Nación | Buenos Aires | Santa Fe | Total |
|---|---:|---:|---:|---:|
| Registros de artículos | 208 | 155 | 296 | **659** |
| Chunks generados | 289 | 175 | 364 | **828** |
| Mediana de longitud del chunk | 506 | 356 | 489 | — |
| Advertencias del preprocesador | 1 | 4 | 1 | **6** |

No se registraron artículos sin vista indexable ni fragmentos que superaran los 1.000 caracteres configurados. Todos los chunks tienen un identificador propio, vínculo con el artículo de origen, jurisdicción, norma y archivo. En Santa Fe se conserva el **rango de páginas del artículo**, no todavía la página exacta que corresponde a cada chunk.

Las seis advertencias no son seis fallos: incluyen prefacios o cierres ajenos al articulado, la duplicación documentada del artículo 151 y las observaciones normativas de los artículos 13 y 25 de PBA. El reporte no determina vigencia legal.

La documentación de desarrollo registra, al finalizar `TP2-RAG-03`, **32 pruebas automatizadas aprobadas**, ejecuciones repetidas de los procesadores con resultados idénticos y verificación de SHA-256 de los archivos de origen. Son **resultados consignados por el agente de programación**; la inspección posterior del repositorio corroboró la estructura y casos representativos, pero no equivale a una auditoría visual exhaustiva de las 70 páginas ni a una ejecución independiente en otro equipo.

## 4. Criterios técnicos adoptados y límites reconocidos

- **Fidelidad antes que limpieza agresiva:** una nota o excepción mal eliminada puede cambiar el significado de una disposición. Por eso el texto completo permanece disponible aun cuando exista una vista simplificada para recuperación.
- **Trazabilidad:** es posible relacionar cada chunk con su artículo y documento, y reconstruir las salidas a partir de las fuentes versionadas.
- **Sin resolución jurídica automática:** la presencia de un artículo en un texto actualizado o de una nota modificatoria no prueba por sí sola que todas las disposiciones relacionadas estén contempladas.
- **Tratamiento diferenciado de los formatos:** TXT sin páginas originales; PDF con página inicial y final del artículo. No se inventaron páginas para los TXT ni una correspondencia precisa por chunk que todavía no ha sido validada.
- **Limitaciones menores aún visibles:** ciertas vistas auxiliares pueden conservar puntuación aislada al retirar notas; la fragmentación recursiva puede dejar poco o ningún solapamiento efectivo. Ambos aspectos podrán contrastarse con resultados de búsqueda reales.
- **Alcance de la validación:** hasta aquí se verificaron **ingesta, estructura, conservación del contenido procesado, fragmentación y reproducibilidad de esas salidas**. No se ha medido todavía pertinencia de recuperación, calidad de respuesta ni abstención frente a preguntas sin evidencia.

## 5. Evidencia y reproducibilidad de la etapa

El repositorio contiene los originales, scripts, datos derivados y reportes. Los comandos documentados para reproducir esta fase desde la raíz son:

```bash
uv sync
uv run python preprocesar.py
uv run python fragmentar.py
uv run pytest -q
```

Los detalles de las pruebas y de los incidentes registrados se encuentran en [`evalucacion/validacion_preprocesamiento.md`](evalucacion/validacion_preprocesamiento.md). Los reportes JSON permiten inspeccionar conteos, advertencias, posiciones, páginas y decisiones de fragmentación sin depender de una descripción verbal del proceso.

## 6. Próximos pasos — pendientes, no realizados

1. **Embeddings e índice:** generar vectores con `bge-m3` mediante Ollama, almacenarlos en Chroma y comprobar la reconstrucción del índice.
2. **Recuperación:** ejecutar consultas con el mismo modelo de embeddings; inspeccionar el ranking, el número de fragmentos recuperados (`k`), los filtros jurisdiccionales y los errores de cobertura.
3. **Generación:** usar un modelo local mediante Ollama (ruta de referencia: `granite4:latest`) con contexto explícito y abstención solicitada ante evidencia insuficiente.
4. **Interfaz:** construir Gradio para mostrar por separado respuesta y **los mismos fragmentos** que se suministraron al generador.
5. **Evaluación:** definir antes de las pruebas al menos **tres preguntas respondibles** (una por documento) y **dos no respondibles**; registrar fuente esperada, fragmentos recuperados, respuesta y al menos una limitación observada. Comparar parámetros de recuperación/fragmentación cuando aporte evidencia.
6. **Cierre:** verificar la instalación desde un directorio limpio, completar README, declarar el uso de herramientas de IA y preparar la demostración de hasta cinco minutos y la entrega.

## 7. Asistencia de IA y responsabilidades

La delimitación del problema, la selección del corpus, la revisión de los casos jurídicos y la planificación se trabajaron con asistencia conversacional de IA. La implementación y ejecución de scripts y pruebas se delegó parcialmente a un **agente de programación** bajo tareas acotadas y criterios de aceptación. Los resultados informados por el agente se contrastaron con los archivos generados y con casos concretos del corpus.

Para la declaración final de la materia se deberá añadir **qué modelos concretos se utilizaron en cada momento** y **qué comprobaciones realizó personalmente el estudiante**. Esta bitácora distingue las pruebas que constan en los registros del agente de las verificaciones posteriores; no atribuye al estudiante comprobaciones que todavía no están documentadas.

---

## Registro de próximas actualizaciones

Las nuevas entradas se incorporarán al avanzar en el proyecto, con este formato breve:

**Fecha y etapa:**  
**Objetivo:**  
**Problema o hipótesis:**  
**Decisión y justificación:**  
**Acción implementada:**  
**Resultado observado y evidencia:**  
**Limitaciones o pendientes:**
