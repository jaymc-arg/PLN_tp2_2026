# Bitácora de desarrollo — Trabajo Integrador 2 de PLN

**Proyecto:** RAG para consulta y comparación de legislación electoral argentina  
**Materia:** Procesamiento de Lenguaje Natural — Tecnicatura Superior en Ciencia de Datos e Inteligencia Artificial, IFTS N.º 24  
**Repositorio:** [jaymc-arg/PLN_tp2_2026](https://github.com/jaymc-arg/PLN_tp2_2026)  
**Período documentado:** inicio del proyecto al **11 de noviembre de 2026**  
**Última etapa incorporada:** `TP2-RAG-06` (commit `28f26ef`, 11 de noviembre de 2026).
**Estado:** corpus procesado, 828 chunks indexados en Chroma con `bge-m3`, recuperación evaluada y **generación local implementada con `granite4:latest`**. Se registraron respuestas reales para cinco preguntas fijas, incluidos aciertos de abstención y errores de fundamentación y citas. **No se implementó todavía la interfaz Gradio ni se resolvieron las fallas de recuperación detectadas.**

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
5. **Distinguir articulado y anotaciones.** Cada registro conserva `texto` íntegro y `texto_principal` como vista auxiliar sin determinadas notas editoriales, además de `notas` y `referencias_externas`. Esta vista **no equivale a una consolidación jurídica automática**.

**Fallo detectado durante las pruebas.** Una remisión a `artículo 172.` al comienzo de una línea de la página 45 de Santa Fe fue interpretada inicialmente como una nueva rúbrica dentro del artículo 173. Se corrigió la detección según la forma de los encabezados presentes en estas fuentes y se incorporó una prueba de regresión. El resultado final reconoce **296 artículos**, sin crear uno artificial por esa referencia interna. El criterio es específico de este corpus; no pretende funcionar como parser universal de legislación.

**Evidencia:** [`scripts/00_preprocesar.py`](scripts/00_preprocesar.py), [`tests/test_00_preprocesar.py`](tests/test_00_preprocesar.py), [`reporte_preprocesamiento.json`](datos/procesados/reporte_preprocesamiento.json) y los tres archivos `*_articulos.jsonl`.

### Etapa 2 — Tratamiento de modificaciones normativas (`TP2-RAG-02`)

**Problema observado.** No todas las transcripciones entre comillas tienen el mismo significado: algunas reproducen antecedentes históricos y otras son el contenido sustantivo de artículos que modifican otras leyes. Una clasificación uniforme podía ocultar información pertinente o incorporar propuestas observadas como si fueran texto principal.

**Caso de Buenos Aires, artículo 13.** El TXT contiene el artículo 13 de la Ley 5.109, con **92 diputados y 46 senadores**, seguido de una nota que transcribe el artículo 26 de la Ley 14.086, que proponía **100 diputados y 50 senadores**, modificación observada por el Decreto 2997/2009. **Decisión:** conservar la nota y la transcripción en `texto`/`notas`, pero no incluirlas en `texto_principal`. El artículo 26 transcripto pertenece a otra ley y no debe confundirse con el artículo 26 propio de la Ley 5.109.

**Caso de Santa Fe, artículos 285 a 290.** Esos artículos introducen nuevas redacciones de disposiciones de otras leyes y reproducen el texto sustituto entre comillas. La primera versión del procesador clasificaba esas citas como transcripciones prescindibles y las retiraba de `texto_principal`. **Corrección:** etiquetarlas como `texto_modificatorio` y conservarlas también en la vista principal. Se comprobó que los seis artículos conservan la redacción completa.

**Límite asumido.** La anotación del artículo 25 bonaerense remite a un subrayado que no sobrevivió al copiado como TXT. Se decidió mantener la advertencia sin reconstruir arbitrariamente el tramo observado. La detección de anotaciones no reemplaza una interpretación jurídica de su vigencia.

**Evidencia:** clasificación implementada en [`scripts/00_preprocesar.py`](scripts/00_preprocesar.py), registros de los artículos citados y pruebas específicas en [`tests/test_00_preprocesar.py`](tests/test_00_preprocesar.py).

### Etapa 3 — Fidelidad documental y fragmentación (`TP2-RAG-03`)

**Problema 1: numeración duplicada en PBA.** La fuente bonaerense incluye **dos apariciones del artículo 151**, con contenidos diferentes y una nota sobre la numeración del texto ordenado. Durante una edición manual se había retirado la segunda aparición, reduciendo temporalmente el conteo de 155 a 154. **Corrección:** se recuperó literalmente desde el historial de Git; el procesador volvió a generar 155 registros y asignó identificadores distintos (`pba_5109_art_151` y `pba_5109_art_151__2`) sin inventar numeración jurídica.

**Problema 2: encabezados especiales.** Algunos títulos y capítulos de Santa Fe aparecen como `TÍTULO ÚNICO` o `CAPÍTULO ÚNICO`. Inicialmente podían quedar agrupados en el campo incorrecto. **Corrección:** se amplió el reconocimiento de encabezados, preservando separados los niveles estructurales.

**Problema 3: longitud variable de los artículos.** La unidad jurídica no coincide siempre con un tamaño adecuado para embeddings. Por ejemplo, los artículos 4 y 54 de Santa Fe son extensos. **Decisión:** fragmentar **dentro de cada artículo**, sin concatenar indiscriminadamente artículos o jurisdicciones. Se utilizó `RecursiveCharacterTextSplitter` con tamaño objetivo de **1.000 caracteres** y solapamiento configurado de **150 caracteres**, manteniendo el identificador del artículo y los metadatos en cada fragmento.

El script [`scripts/01_fragmentar.py`](scripts/01_fragmentar.py) genera una representación para búsqueda que repara saltos de línea visuales del PDF **sin alterar los registros originales**. También conserva los textos modificatorios sustantivos y evita indexar artículos nacionales derogados como encabezados vacíos: en esos casos utiliza una descripción expresamente derivada de la nota de derogación de la fuente.

**Observación sobre el solapamiento.** El valor 150 es un parámetro del splitter, no una garantía de 150 caracteres repetidos en todos los límites. Una inspección posterior encontró **112 límites sin repetición literal entre 169 pares de chunks consecutivos** de un mismo artículo. No se interpretó automáticamente como defecto; corresponde examinar su efecto sobre la recuperación en la etapa siguiente.

**Evidencia:** [`scripts/01_fragmentar.py`](scripts/01_fragmentar.py), [`chunks.jsonl`](datos/procesados/chunks.jsonl) y [`reporte_fragmentacion.json`](datos/procesados/reporte_fragmentacion.json).

### Etapa 4 — Embeddings e índice vectorial local (`TP2-RAG-04`)

**Objetivo y problema.** Los 828 fragmentos estaban disponibles en formato JSONL, pero todavía no podían consultarse mediante búsqueda semántica. Era necesario convertirlos en vectores, mantener la correspondencia entre cada vector y su evidencia documental y guardar el resultado de forma persistente. También había que evitar indexaciones duplicadas o reutilizar accidentalmente un índice construido con otro corpus o modelo.

**Decisiones y acciones:**

1. **Separar representación y generación.** Se eligió `bge-m3` a través de Ollama como modelo local de *embeddings*. Su función aquí es representar consultas y fragmentos en el mismo espacio vectorial; **no genera respuestas**. El modelo generativo previsto (`granite4:latest`) se incorporará en una etapa posterior.
2. **Utilizar Chroma como almacén persistente.** Se implementó [`scripts/02_indexar.py`](scripts/02_indexar.py), que lee [`chunks.jsonl`](datos/procesados/chunks.jsonl), conserva el texto del chunk sin reescribirlo y transforma sus atributos en metadatos admitidos por Chroma. La colección se denomina `electoral_laws` y se guarda en `.chroma/electoral_laws/`, excluida de Git por ser un artefacto reconstruible.
3. **Preservar la trazabilidad.** Cada vector se asocia al ID estable del chunk, al artículo de origen, la jurisdicción, la ley, el nombre del documento y los rangos de páginas disponibles. Para los TXT, que carecen de paginación original, se omiten los campos de página `null` en lugar de inventar una referencia.
4. **Proteger la consistencia de la indexación.** Se incorporó un manifiesto local con modelo, colección, endpoint, versión de firma y hash SHA-256 del archivo de chunks. Reejecutar con la misma firma reutiliza los registros existentes; una firma distinta impide la reutilización silenciosa. El parámetro `--rebuild` permite una reconstrucción explícita del índice administrado por el script.
5. **Fijar casos de prueba antes de evaluar los resultados.** Se creó [`evalucacion/preguntas.json`](evalucacion/preguntas.json) con **tres preguntas respondibles** —Nación artículo 12, PBA artículo 13 y Santa Fe artículo 4— y **dos sin respuesta en el corpus** —resultados de la elección presidencial de 2023 y gastos efectivamente rendidos por partidos en esa campaña—. Incluyen fuente esperada o justificación de ausencia. La intención es utilizar preguntas predefinidas, sin seleccionarlas después de ver qué recupera el sistema.

**Pruebas e incidentes observados.** Ollama informó versión `0.40.15` y el modelo local `bge-m3:latest` (identificador `790764642607`) devolvió vectores de **1.024 dimensiones**. La primera indexación registró **828 de 828 chunks**, con **828 IDs únicos** y metadatos coincidentes con los archivos de entrada. Una segunda ejecución mantuvo el conteo; se verificó además una reconstrucción con `--rebuild`. Al cambiar la firma de modelo a `bge-m3:latest`, el script rechazó reutilizar el índice creado con el nombre configurado `bge-m3` y una inspección posterior mostró que seguía intacto. Esa diferencia de nombre actúa como control estricto de configuración, aunque ambos nombres puedan referir localmente al mismo modelo.

**Consulta exploratoria, no evaluación definitiva.** Para la pregunta «¿Qué excepciones al deber de votar establece el artículo 12?», la búsqueda devolvió en las primeras tres posiciones: **Nación art. 12**, **PBA art. 4** y **Santa Fe art. 77**. El primer resultado coincide directamente con la consulta; los otros dos contienen disposiciones análogas de jurisdicciones diferentes. Esta observación indica que el índice recupera contenido semánticamente relacionado, pero también plantea la necesidad de **evaluar filtros por jurisdicción**. No demuestra todavía precisión global de recuperación, calidad de respuestas ni capacidad de abstenerse.

**Resultado y evidencia.** La documentación de la ejecución registra **39 pruebas automatizadas aprobadas**, además de verificaciones contra el Chroma persistente real. Las pruebas unitarias de [`tests/test_02_indexar.py`](tests/test_02_indexar.py) utilizan objetos simulados para comprobar contratos, firmas, metadatos e idempotencia, mientras que [`evalucacion/validacion_indexacion.md`](evalucacion/validacion_indexacion.md) deja constancia de los comandos y de las pruebas efectuadas con Ollama y Chroma reales. **La auditoría posterior de este repositorio verificó el código, las pruebas y los informes versionados; no reprodujo localmente los 828 embeddings ni accedió al índice `.chroma/` del equipo de desarrollo.**

**Límites reconocidos.** Indexar correctamente 828 registros no equivale a demostrar que se recupera el artículo adecuado para todas las preguntas. El índice no se versiona y debe reconstruirse en otros equipos con el modelo disponible. Tampoco está implementado todavía el paso de enviar contexto a un LLM para redactar respuestas.

**Evidencia:** [`scripts/02_indexar.py`](scripts/02_indexar.py), [`tests/test_02_indexar.py`](tests/test_02_indexar.py), [`evalucacion/preguntas.json`](evalucacion/preguntas.json) y [`evalucacion/validacion_indexacion.md`](evalucacion/validacion_indexacion.md).

### Etapa 5 — Recuperación semántica y evaluación de evidencia (`TP2-RAG-05`)

**Problema abordado.** Un índice con 828 vectores y una búsqueda de humo exitosa no garantizan que las preguntas reales recuperen los artículos pertinentes ni que los fragmentos obtenidos contengan todos los datos necesarios. Además, tres normas de jurisdicciones diferentes pueden tratar cuestiones parecidas: una similitud alta no establece qué legislación responde a una pregunta.

**Decisiones y acciones.** Se implementó [`scripts/03_recuperar.py`](scripts/03_recuperar.py) como capa de consulta reutilizable, independiente del indexador, que genera el vector de la pregunta con el mismo `bge-m3` y consulta la colección persistida `electoral_laws`. Admite `k` configurable y filtro opcional `jurisdiccion` (`nacional`, `pba`, `santa_fe`). Devuelve el **texto completo** de cada chunk, su posición, ID, artículo, norma, fuente, páginas cuando existen y **distancia nativa de Chroma**. La distancia ordena vecinos: no es una probabilidad de verdad ni una medida directa de suficiencia probatoria. El código valida el manifiesto y los IDs del índice; no reindexa ni reconstruye los documentos durante una búsqueda.

La evaluación se implementó en [`scripts/evaluar_recuperacion.py`](scripts/evaluar_recuperacion.py) sobre las **cinco preguntas fijadas antes de probar la recuperación** en [`evalucacion/preguntas.json`](evalucacion/preguntas.json): tres respondibles (una por jurisdicción) y dos sin respuesta documental. Para cada positiva se obtuvo una búsqueda sin filtro y otra restringida a su jurisdicción, con `k=5`; los indicadores Hit@1, Hit@3, Hit@5 y MRR@5 se calcularon **a nivel del artículo esperado**, sin cambiar las preguntas tras observar el ranking. Se añadieron una paráfrasis separada y la comparación `k=1` frente a `k=3` sobre el mismo ranking, fuera de las métricas fijas. También se generaron un contexto numerado con los **fragmentos exactos y completos** recuperados, un gráfico de distancias y archivos de resultados auditables. Ningún modelo generativo intervino en esta etapa.

**Resultados cuantitativos.** Tanto sin filtro como con filtro jurisdiccional, Hit@1, Hit@3 y Hit@5 fueron **2/3 = 0,667**, y **MRR@5 = 0,667**. El denominador son únicamente las tres preguntas respondibles; un fallo aporta cero al MRR y las dos negativas no se cuentan como aciertos de recuperación. Es un diagnóstico de cinco casos prefijados, **no una estimación estadística de desempeño general**.

**Inspección del pasaje recuperado:**

- **Nación, artículo 12:** aparece en primer lugar, pero sólo se recupera `nacional_19945_art_12__chunk_0001`. El fragmento siguiente, ausente incluso del top-5, contiene la causal `d)` relativa a servicios públicos, condiciones de acreditación/comunicación y la aclaración de que las exenciones son optativas. Por lo tanto, el *hit por artículo* es correcto, pero la evidencia disponible en top-3 es **parcial**. Aumentar `k` de 1 a 3 no solucionó esa ausencia.
- **Buenos Aires, artículo 13:** el primer resultado es `pba_5109_art_13__chunk_0001`; contiene la regla de **92 diputados y 46 senadores**. La evidencia es **suficiente para la pregunta formulada**, sin interpretar como norma aplicable la propuesta histórica de 100/50 separada de la vista indexable.
- **Santa Fe, artículo 4:** el artículo esperado **no aparece en top-5**, ni siquiera aplicando sólo el filtro `santa_fe`. El primer resultado fue el artículo 67, próximo por tema pero diferente del pasaje definitorio del artículo 4. La definición sí existe en el corpus, en `santa_fe_14478_art_4__chunk_0001`; el problema es de **selección/ordenamiento de evidencia**, no de extracción ausente.
- **Dos preguntas negativas:** Chroma devolvió vecinos relativos a reglas electorales y financiamiento, pero ninguno contenía los **resultados presidenciales de 2023** ni los **gastos reales rendidos por partido** solicitados. La revisión los clasificó como no respondibles **con este corpus**. No se ha probado todavía que un LLM efectivamente se abstenga.

**Sensibilidad a la formulación y al filtro.** La paráfrasis sobre excepciones al voto nacional ubicó primero normas provinciales; el artículo nacional esperado apareció recién en el **puesto 4**. Restringir por jurisdicción eliminó cruces entre normas, pero **no mejoró el Hit@k agregado ni la cobertura faltante** de Nación y Santa Fe. El filtro jurisdiccional es útil, pero no reemplaza la selección de un artículo explícitamente citado ni la recuperación de chunks relacionados dentro de él.

**Validación e interpretación.** [`evalucacion/reporte_recuperacion.json`](evalucacion/reporte_recuperacion.json) conserva rankings top-5, textos íntegros, distancias y métricas; [`evalucacion/revision_manual_recuperacion.json`](evalucacion/revision_manual_recuperacion.json) documenta la inspección de pasajes **realizada por el agente de programación**, con citas cotejadas automáticamente contra los textos devueltos; [`evalucacion/validacion_recuperacion.md`](evalucacion/validacion_recuperacion.md) sintetiza el análisis y [`evalucacion/distancias_recuperacion.svg`](evalucacion/distancias_recuperacion.svg) representa distancias observadas. El repositorio incorpora **11 funciones de prueba nuevas** en [`tests/test_03_recuperar.py`](tests/test_03_recuperar.py), con dobles de prueba para contratos y validación de resultados. El reporte verifica **828 IDs y el mismo hash del manifiesto antes y después** de consultar, sin alteraciones detectadas. La inspección del agente **no equivale a una validación personal del estudiante** y los documentos disponibles no deben confundirse con una evaluación de respuestas generadas.

**Decisión posterior.** Se conserva el índice como línea de base y se registran los errores, en vez de modificar las preguntas para mejorar artificialmente las métricas. Antes de confiar en la generación corresponde **experimentar y comparar** recuperación dirigida por metadatos cuando se mencione un artículo concreto y expansión a chunks contiguos del mismo artículo; verificar si esas estrategias incorporan el inciso `d)` nacional y la definición santafesina. Estos experimentos **aún no están implementados ni evaluados**. Tampoco se fija un umbral universal de distancia para afirmar que una pregunta puede responderse.

### Etapa 6 — Generación local con contexto y fuentes (`TP2-RAG-06`)

**Problema abordado.** La recuperación de `TP2-RAG-05` demostró que una coincidencia semántica no garantiza disponer del pasaje necesario. El siguiente desafío era comprobar cómo responde un modelo generativo ante fragmentos relevantes, incompletos o de otras jurisdicciones; si se abstiene al faltar evidencia; y si sus citas corresponden a lo que recibió realmente. El propósito de esta etapa fue **observar y documentar** el comportamiento del RAG, no presentar una tasa de exactitud general a partir de cinco casos.

**Decisiones y acciones:**

1. **Generación local y reutilización del índice.** Se implementó [`scripts/04_generar.py`](scripts/04_generar.py), integrado con `SemanticRetriever`, `ChatPromptTemplate`, `ChatOllama` y `StrOutputParser`. Se utilizó `granite4:latest` en Ollama local, con temperatura **0**, mientras `bge-m3` permaneció como modelo de embeddings. La versión observada de Granite fue **3,4B parámetros, cuantización Q4_K_M** (digest `4235724a127c…`). No se reconstruyó el índice ni se modificaron los chunks.
2. **Contexto explícito y auditable.** El generador envía los fragmentos completos obtenidos por recuperación en orden, con referencias numeradas `[1]`, `[2]`, etc. El resultado conserva la pregunta, el texto **exactamente enviado como contexto** (`context_sent`), los IDs, fuentes, artículos, jurisdicciones, páginas disponibles, respuesta literal del modelo y mapa de referencias. La instrucción solicita responder en español sólo con la evidencia y no mezclar jurisdicciones; ante información insuficiente, pide responder literalmente: «No encuentro esa información en los documentos».
3. **Comprobar citas sin encubrir fallos.** Se comprueba automáticamente si las referencias tienen el formato esperado, si falta una cita o si un número no corresponde a un fragmento enviado. **Este control no comprueba que una afirmación esté respaldada semánticamente**. Las respuestas originales se guardan sin insertar ni corregir citas a posteriori. Si la recuperación está vacía, no se invoca Granite y se devuelve una abstención explícita; esta situación es distinta de una respuesta insuficientemente fundamentada pero no vacía.
4. **Mantener el conjunto de evaluación fijo.** [`scripts/evaluar_generacion.py`](scripts/evaluar_generacion.py) ejecutó las **tres preguntas respondibles y las dos no respondibles** ya definidas en `evalucacion/preguntas.json`, con **k=3 sin filtro jurisdiccional**. Los resultados y el contexto utilizado se conservaron en [`reporte_generacion.json`](evalucacion/reporte_generacion.json). La inspección textual fue registrada por el agente en [`revision_manual_generacion.json`](evalucacion/revision_manual_generacion.json) y contrastada con las respuestas originales mediante hashes. No equivale a validación jurídica independiente.

**Resultados de las cinco preguntas fijas:**

| Pregunta | Evidencia recibida por Granite | Respuesta observada | Diagnóstico |
|---|---|---|---|
| **Nación, art. 12:** excepciones al voto | Primer chunk del art. 12 nacional, seguido de PBA art. 4 y Santa Fe art. 77 | Enumeró las causales **a–c**, pero omitió la **d** y el carácter optativo. Citó `[1]`. | **Parcial e imprecisa:** faltaba la continuación del artículo; además incorporó una formulación bonaerense sobre la acreditación, atribuyéndola incorrectamente a la fuente nacional `[1]`. Cita formalmente válida, pero respaldo semántico defectuoso. |
| **PBA, art. 13:** composición legislativa | Art. 13 bonaerense en primer lugar | Respondió **92 diputados y 46 senadores**. | **Contenido correcto para la consulta**, pero **sin la cita `[1]` exigida**. La nota histórica observada sobre 100/50 no estaba en la vista indexada. |
| **Santa Fe, art. 4:** definición de autoridad de mesa | Santa Fe arts. 67 y 59, y Nación art. 72; **sin art. 4** | Atribuyó al art. 4 información sobre presidencia, suplentes y balotaje; agregó `[1][2][4]`. | **Error crítico:** respondió sin la fuente solicitada, mezcló jurisdicciones, no se abstuvo y citó **`[4]`, referencia inexistente** entre los tres fragmentos enviados. |
| **Resultado presidencial 2023** (fuera del corpus) | Fragmentos de reglas electorales sin resultados observados | «No encuentro esa información en los documentos». | **Abstención correcta** en esta ejecución. |
| **Gastos reales de campaña 2023** (fuera del corpus) | Disposiciones sobre cuentas y límites legales, sin rendiciones reales | «No encuentro esa información en los documentos». | **Abstención correcta** en esta ejecución; no confundió topes legales con gastos efectivos. |

**Experimento `k=1` frente a `k=3`.** Para la pregunta nacional se mantuvieron modelo, temperatura y prompt; sólo cambió la cantidad de fragmentos recuperados. **Ambas respuestas fueron parciales** porque no llegó el segundo chunk nacional. Con **k=1** el modelo conservó la referencia a la autoridad policial más próxima y su certificación, respaldadas por `[1]`. Con **k=3** aparecieron normas provinciales similares y la respuesta sustituyó ese detalle por «autoridad que corresponda», expresión del fragmento bonaerense, pero la adjudicó a `[1]`. En este caso **agregar fragmentos empeoró la atribución normativa sin mejorar la cobertura**. No se infiere de un único experimento que k=1 sea siempre superior.

**Qué aprendimos.** En las tres preguntas respondibles hubo al menos una deficiencia: omisión de evidencia y contaminación de fuente (Nación), falta de cita (PBA) o respuesta sin la disposición pedida y referencia inventada (Santa Fe). **Sólo PBA obtuvo una respuesta sustantivamente correcta y suficiente para su pregunta concreta, aunque incumplió la citación**. Las dos preguntas negativas terminaron en abstención, pero el caso de Santa Fe demuestra que **la instrucción de abstenerse no es una barrera confiable cuando se recupera evidencia temática pero insuficiente**. El cotejo de números de cita es necesario y no suficiente.

**Verificación y límites.** La ejecución real documentada utilizó Ollama **0.40.15**, `granite4:latest`, temperatura **0**, y mantuvo intactos los **828 registros**, los IDs y el manifiesto Chroma antes y después. `tests/test_04_generar.py` cubre con dobles de prueba contexto, metadatos, citas, abstención y errores del runtime; el material inspeccionado **no aporta un conteo final de la suite completa**, por lo que no se inventa. Los informes permiten cotejar cada respuesta con el texto enviado, pero el análisis fue realizado por el agente y debe ser revisado por el estudiante. La configuración con temperatura 0 no garantiza veracidad ni repetibilidad.

**Evidencia:** [`scripts/04_generar.py`](scripts/04_generar.py), [`scripts/evaluar_generacion.py`](scripts/evaluar_generacion.py), [`tests/test_04_generar.py`](tests/test_04_generar.py), [`evalucacion/reporte_generacion.json`](evalucacion/reporte_generacion.json), [`evalucacion/revision_manual_generacion.json`](evalucacion/revision_manual_generacion.json) y [`evalucacion/validacion_generacion.md`](evalucacion/validacion_generacion.md).

## 3. Resultados medibles al cierre de `TP2-RAG-06`

| Indicador | Nación | Buenos Aires | Santa Fe | Total |
|---|---:|---:|---:|---:|
| Registros de artículos | 208 | 155 | 296 | **659** |
| Chunks generados | 289 | 175 | 364 | **828** |
| Mediana de longitud del chunk | 506 | 356 | 489 | — |
| Advertencias del preprocesador | 1 | 4 | 1 | **6** |

No se registraron artículos sin vista indexable ni fragmentos que superaran los 1.000 caracteres configurados. Todos los chunks tienen un identificador propio, vínculo con el artículo de origen, jurisdicción, norma y archivo. En Santa Fe se conserva el **rango de páginas del artículo**, no todavía la página exacta que corresponde a cada chunk.

| Indicador de la nueva etapa de indexación | Resultado informado y documentado |
|---|---|
| Modelo de embeddings | `bge-m3:latest` mediante Ollama local |
| Dimensión del vector | **1.024** |
| Colección Chroma | `electoral_laws` |
| Fragmentos almacenados / esperados | **828 / 828** |
| IDs únicos verificados | **828** |
| Segunda ejecución | **828 registros**, sin incremento |
| Reconstrucción controlada | `--rebuild` probado satisfactoriamente |
| Prueba exploratoria | Artículo 12 nacional en primer lugar; normas análogas de PBA y Santa Fe en segundo y tercero |
| Pruebas automatizadas al cierre | **39 aprobadas** (según reporte del agente) |

**Resultado de recuperación `TP2-RAG-05`** (evaluación con tres preguntas respondibles, fijadas con antelación):

| Medida | Sin filtro | Con jurisdicción |
|---|---:|---:|
| Hit@1 | **0,667** | **0,667** |
| Hit@3 | **0,667** | **0,667** |
| Hit@5 | **0,667** | **0,667** |
| MRR@5 | **0,667** | **0,667** |

En cobertura del pasaje top-3: **Nación parcial; PBA suficiente; Santa Fe ausente**, en ambos modos. Las dos preguntas negativas no encuentran evidencia que fundamente la respuesta, aunque Chroma siempre devuelva vecinos. El índice conserva **828 IDs** antes y después de las consultas. `tests/test_03_recuperar.py` incorpora **11 funciones de prueba**; no se atribuye una nueva cifra de *suite* completa aprobada sin registro de su ejecución en los informes consultados.

**Resultado de generación `TP2-RAG-06`:** `granite4:latest` (3,4B, Q4_K_M), con temperatura **0** y **k=3** sobre las mismas cinco preguntas, sin filtro jurisdiccional. Las respuestas fueron: **Nación parcial y con contaminación de fuente**, **PBA sustantivamente correcta pero sin cita**, **Santa Fe incorrectamente atribuida al artículo 4, con cita `[4]` inexistente y sin abstención**, y **dos abstenciones correctas** en las preguntas fuera del corpus. En esta muestra **ninguna de las tres respuestas positivas cumplió simultáneamente cobertura suficiente y requisito de citas**; esto no es una tasa poblacional de exactitud. El experimento `k=1`/`k=3` sobre Nación mantuvo la omisión de la causal `d)` y mostró que el contexto adicional introdujo una atribución de PBA a Nación. El índice siguió en **828/828** registros, sin alteraciones.

Las seis advertencias no son seis fallos: incluyen prefacios o cierres ajenos al articulado, la duplicación documentada del artículo 151 y las observaciones normativas de los artículos 13 y 25 de PBA. El reporte no determina vigencia legal.

La etapa `TP2-RAG-03` cerró con **32 pruebas automatizadas aprobadas**, ejecuciones repetidas de los procesadores con resultados idénticos y verificación de SHA-256 de los archivos de origen. La etapa `TP2-RAG-04` registra **39 pruebas aprobadas** y comprobaciones adicionales del índice real. Estos son **resultados consignados por el agente de programación**; la inspección posterior del repositorio corroboró la implementación y los casos documentados, pero no equivale a una auditoría visual exhaustiva de las 70 páginas ni a una reconstrucción independiente del índice en otro equipo.

## 4. Criterios técnicos adoptados y límites reconocidos

- **Fidelidad antes que limpieza agresiva:** una nota o excepción mal eliminada puede cambiar el significado de una disposición. Por eso el texto completo permanece disponible aun cuando exista una vista simplificada para recuperación.
- **Trazabilidad:** es posible relacionar cada chunk con su artículo y documento, y reconstruir las salidas a partir de las fuentes versionadas.
- **Índice reconstruible y consistente:** Chroma conserva IDs y metadatos; un manifiesto asociado al hash de los chunks y al modelo impide mezclar configuraciones de forma inadvertida. La carpeta del índice no se sube al repositorio.
- **Distinción entre recuperar, generar y fundamentar:** `bge-m3` identifica vecinos semánticos, pero no decide suficiencia jurídica; `granite4:latest` genera lenguaje a partir del contexto recibido. En la evaluación, **dos aciertos de artículo no significaron dos respuestas completas**: Nación sólo aportó evidencia parcial. La generación confirmó que un fragmento temáticamente próximo puede producir una respuesta atribuida a otra norma. Las distancias nativas no representan probabilidades de certeza.
- **Sin resolución jurídica automática:** la presencia de un artículo en un texto actualizado o de una nota modificatoria no prueba por sí sola que todas las disposiciones relacionadas estén contempladas.
- **Tratamiento diferenciado de los formatos:** TXT sin páginas originales; PDF con página inicial y final del artículo. No se inventaron páginas para los TXT ni una correspondencia precisa por chunk que todavía no ha sido validada.
- **Limitaciones de fragmentación:** ciertas vistas auxiliares pueden conservar puntuación aislada al retirar notas; la fragmentación recursiva puede dejar poco o ningún solapamiento efectivo. La falta del segundo chunk nacional muestra una consecuencia concreta de cobertura, aunque no permite atribuir el fallo únicamente al solapamiento.
- **Alcance de la validación:** se evaluaron **recuperación y generación local sobre cinco preguntas fijadas**. Además del hit por artículo y la cobertura del pasaje, se contrastó cada salida de Granite con las fuentes realmente enviadas. En este lote hubo dos abstenciones pertinentes, pero las tres respuestas positivas tuvieron defectos de cobertura o citas. **El control automático de referencias sólo detecta errores sintácticos y números inexistentes, no respalda semánticamente el contenido ni garantiza abstención.**
- **Pendientes documentales menores identificados en la revisión:** la tabla inicial de `evalucacion/validacion_preprocesamiento.md` muestra **74** anotaciones bonaerenses, pero el reporte de auditoría y los registros JSONL actuales contienen **72**. Asimismo, el README conserva una frase desactualizada que describe los enlaces de las fuentes como desconocidos, aunque `datos/fuentes.csv` ya consigna enlaces. Son inconsistencias de documentación, no problemas del índice; se deben armonizar al preparar la entrega final.

## 5. Evidencia y reproducibilidad hasta esta etapa

Los documentos originales, el código y los JSONL están versionados. La base Chroma es local y **no** forma parte de Git; se reconstruye con las instrucciones del repositorio. El recorrido reproducible desde la raíz, con Ollama instalado y su servicio activo, es:

```bash
ollama pull bge-m3
ollama pull granite4:latest
uv sync
uv run python scripts/00_preprocesar.py
uv run python scripts/01_fragmentar.py
uv run python scripts/02_indexar.py
uv run python scripts/evaluar_recuperacion.py
uv run python scripts/evaluar_generacion.py
uv run pytest -q
```

Para reconstruir expresamente un índice propio ya creado:

```bash
uv run python scripts/02_indexar.py --rebuild
```

Las validaciones de extracción y fragmentación están en [`evalucacion/validacion_preprocesamiento.md`](evalucacion/validacion_preprocesamiento.md); las de vectorización y persistencia en [`evalucacion/validacion_indexacion.md`](evalucacion/validacion_indexacion.md); las de búsqueda en [`evalucacion/validacion_recuperacion.md`](evalucacion/validacion_recuperacion.md); y las respuestas reales con sus fuentes en [`evalucacion/validacion_generacion.md`](evalucacion/validacion_generacion.md). Los JSON de recuperación y generación conservan texto íntegro, orden, identificadores y resultados originales. La reproducción integral en un entorno limpio continúa pendiente hasta el cierre.

## 6. Próximos pasos — pendientes, no realizados

1. **Experimento de mejora de recuperación:** comparar la línea de base con búsqueda dirigida por jurisdicción y artículo cuando la pregunta los mencione, y expansión de chunks contiguos del mismo artículo. Evaluar si recupera la causal `d)` nacional y la definición del art. 4 santafesino **sin sustituir los resultados originales de `TP2-RAG-05/06`**. Conservar la distinción entre evidencia suficiente y artículo presente en top-k.
2. **Citas y seguridad de la respuesta:** comprobar de manera visible las referencias faltantes, los números inexistentes y el riesgo de atribuir frases de otra jurisdicción a una fuente. Decidir antes del uso en interfaz si las salidas con referencias inválidas o evidencia insuficiente se deben bloquear, advertir o marcar para revisión; no atribuir fiabilidad por un prompt solamente.
3. **Interfaz (`TP2-RAG-07`):** implementar Gradio mostrando respuesta, fuentes recuperadas y **los mismos fragmentos íntegros** enviados al modelo, incluidas advertencias de citación cuando correspondan.
4. **Evaluación integral (`TP2-RAG-08`):** mantener las cinco preguntas congeladas; contrastar la línea de base con los experimentos, con revisión sustantiva de las citas y abstenciones. Probar cambios de `k` y de estrategia de recuperación sin presentar mejoras anecdóticas como resultados generalizables.
5. **Cierre (`TP2-RAG-09/10`):** armonizar inconsistencias documentales menores, verificar una instalación limpia, documentar el uso de IA y la revisión del estudiante, y preparar la demostración y entrega.

## 7. Asistencia de IA y responsabilidades

La delimitación del problema, la selección del corpus, la revisión de los casos jurídicos y la planificación se trabajaron con asistencia conversacional de IA. La implementación y ejecución de scripts y pruebas se delegó parcialmente a un **agente de programación** bajo tareas acotadas y criterios de aceptación. En `TP2-RAG-04`, `TP2-RAG-05` y `TP2-RAG-06`, el agente documentó ejecuciones contra Ollama y Chroma locales. Inspeccionó los fragmentos recuperados y, en la sexta etapa, las respuestas originales de Granite, contrastándolas con el contexto y las citas. Los resultados se revisaron posteriormente a partir del código y archivos versionados; **no se volvió a ejecutar el modelo ni se accedió al índice local**, y no se atribuye al estudiante una comprobación personal aún no documentada.

Para la declaración final de la materia se deberá añadir **qué modelos concretos se utilizaron en cada momento** y **qué comprobaciones realizó personalmente el estudiante**. Esta bitácora distingue las pruebas que constan en los registros del agente de las verificaciones posteriores; no atribuye al estudiante comprobaciones que todavía no están documentadas.

---

## Integración mínima e interfaz Gradio — tarea actual

**Objetivo:** consulta local de solo lectura con respuesta, enrutamiento, fuentes, contexto literal completo y revisión sintáctica de citas separados.
**Decisión:** trasladar `build_evidence_context()` sin cambios de representación a `scripts/03_recuperar.py`; generador y evaluador comparten esa función. La interfaz usa un callback directo a `answer_question()` y un formateador, sin caché ni reconstrucción, con K=1/3/5 y cinco modos de enrutamiento. No se modificaron corpus, chunks, prompts, indexador ni resultados congelados.
**Archivos:** `scripts/03_recuperar.py`, `scripts/04_generar.py`, `scripts/evaluar_recuperacion.py`, nuevo `scripts/05_interfaz_gradio.py`, nuevo `tests/test_05_interfaz_gradio.py`, `pyproject.toml`, `uv.lock`, `requirements.txt`, `README.md` y esta bitácora.
**Comandos ejecutados y resultados:**
- `uv add gradio` → Gradio 6.32.0; `uv export --format requirements-txt --no-hashes --output-file requirements.txt`; `uv sync` completados. Aviso de copia en lugar de hardlinks, sin fallo.
- `uv run pytest -q tests/test_05_interfaz_gradio.py tests/test_04_generar.py tests/test_03_recuperar.py` → 57 passed (antes de agregar el test de construcción de página).
- `uv run pytest -q` → **137 passed**, 16 avisos esperados por pruebas de compatibilidad con `generate_answer()`.
- `uv run python - <<'PY' … PY` → importación de `scripts.recuperar`, `scripts.generar`, `scripts.evaluar_recuperacion`, `scripts.evaluar_generacion` y ejecución independiente de cada CLI con `--help`: OK. El mismo chequeo llamó `consultar()` con «¿Cuántos diputados y senadores fija el artículo 13 de la Ley 5.109?» y «¿Cómo se vota en PBA?» sin dobles.
- `curl --max-time 5 -sS http://localhost:11434/api/tags` → Ollama respondió con `bge-m3:latest` y `granite4:latest` disponibles.
- `git diff --check` → limpio.
**Resultados observados y límites:** falta `.chroma/electoral_laws` en este checkout. La consulta específica mostró `RetrievalIndexError` y orientación de prerrequisitos; la ambigua mostró motivo/aclaración, sin fuentes ni contexto. La ruta del índice siguió inexistente después: no se reconstruyó. No fue posible medir IDs/manifest antes/después de una recuperación ni validar generación real por ausencia del índice. No se abrió navegador ni puerto: la construcción real de Blocks y el lanzamiento exclusivamente local se verificaron con `launch` sustituido; importación sin consulta/lanzamiento también cubierta. Las pruebas con dobles no son resultados de desempeño jurídico/RAG. La interfaz no permite cambiar chunk size/overlap.
**Asistencia:** implementación, pruebas y documentación realizadas por el agente de programación (modelo de sesión `gpt-6.1-sol`); no se atribuye verificación personal al estudiante.

## 2026-11-13 — Reparación de imports tras numerar scripts

Se adaptaron los imports de los scripts de ejecución, evaluadores, laboratorio y tests a los nuevos nombres `00_`–`05_` mediante `importlib.import_module()`, conservando aliases locales y un único módulo compartido por nombre canónico. Se mantuvieron los archivos renombrados y las demás modificaciones locales; no se añadieron wrappers ni hooks de importación. README documenta esta sintaxis y corrige la referencia al test de indexación.

Verificación: `uv run pytest -q` → **169 passed**, 16 avisos esperados de deprecación. Un chequeo con `uv run python - <<'PY' … PY` importó los 11 módulos, ejecutó `--help` en los ocho CLIs con argumentos y ejecutó `scripts/05_interfaz_gradio.py` mediante `runpy.run_path(..., run_name='__main__')` con `gr.Blocks.launch` sustituido: construcción y lanzamiento local correctos, sin abrir puerto ni consultar modelos. `git diff --check` limpio. No se ejecutó fragmentación, indexación ni generación real en esta reparación. Commit propuesto: `fix: adaptar imports a los scripts numerados`.

## Registro de próximas actualizaciones

Las nuevas entradas se incorporarán al avanzar en el proyecto, con este formato breve:

**Fecha y etapa:**  
**Objetivo:**  
**Problema o hipótesis:**  
**Decisión y justificación:**  
**Acción implementada:**  
**Resultado observado y evidencia:**  
## Nueva entrada — `TP2-RAG-07`

**Fecha y etapa:** 11 de noviembre de 2026 — enrutamiento conservador por jurisdicción.
**Objetivo:** identificar el ámbito normativo antes de consultar Chroma sin inferirlo de una ubicación ambigua; pedir precisión cuando corresponda y permitir comparaciones explícitas.
**Problema o hipótesis:** la similitud semántica global podía mezclar reglas semejantes de distintos niveles. Un lugar (PBA/Santa Fe/Buenos Aires) no necesariamente identifica qué elección rige la pregunta. Un filtro automático demasiado agresivo también podría dirigir a la ley equivocada.
**Decisión y justificación:** detector puro, determinista y acotado a Nación/PBA/Santa Fe; reglas diferenciadas para referencias legales, alcance electoral y geografía; sin puntajes probabilísticos. Rutas irresueltas detienen el flujo antes de embeddings y modelo. Se conservó `SemanticRetriever.retrieve()` como API explícita de bajo nivel; `generate_answer()` se mantiene sólo como wrapper de compatibilidad deprecado. Todas las llamadas de aplicación y evaluación pasan por `answer_question()`. Overrides manuales prevalecen; `--sin-filtro` es un opt-out visible. Las comparaciones consultan k por jurisdicción, conservan rankings/distancias locales y renumeran una sola vez las citas del contexto compartido.
**Acción implementada:** `scripts/03_bis_detectar_jurisdiccion.py`, orquestación y CLIs de `scripts/04_generar.py`/`scripts/03_recuperar.py`, evaluación independiente en `scripts/evaluar_jurisdiccion.py`, 40 casos en `evalucacion/preguntas_jurisdiccion.json`, tests específicos y reportes `reporte_jurisdiccion.json`/`validacion_jurisdiccion.md`. No se cambió el fixture congelado de cinco consultas, corpus, chunks, indexador ni generación baseline; no se reindexó.
**Resultado observado y evidencia:** fixture SHA-256 `3ef5fa9188caefb85876c531bf95b12a5db9612389b17a08583db5e4f45a06fe`. La matriz de confusión fue diagonal: identificadas 21/21, ambiguas 7/7, comparativas 4/4, no especificadas 4/4, no soportadas 4/4 (40/40 exactas); precisión/recall por jurisdicción 1.00, cobertura de filtro individual 21/21, misruteo dañino 0/40, aclaración adecuada 15/15 y comparación exacta 4/4. Esto mide sólo los 40 ejemplos del fixture; no es estimación general.

La evaluación read-only del índice real obtuvo Hit@1/3/5 y MRR@5 iguales en baseline no filtrado, filtro oracle y filtro automático: 2/3 en cada medida; cada métrica tiene denominador 3. El detector cubrió 3/3 preguntas respondibles, ninguna consulta se evitó por aclaración en ese subconjunto y la búsqueda automática devolvió 0 chunks de jurisdicción incorrecta. La integridad fue estable: 828 IDs, mismo hash de IDs (`d991473a…`) y manifest (`93c7538f…`) antes/después. Al inspeccionar evidencia: Nación recupera el art. 12, pero no su continuación con inciso d); PBA recupera el pasaje del art. 13 suficiente para la cantidad solicitada; Santa Fe no trae el art. 4 al top-5, aunque el pasaje sí está en el corpus. Un hit de artículo no significa pasaje completo.

Smoke tests reales mediante `scripts/04_generar.py`: pregunta explícita de Ley 5.109 → ruta PBA, una recuperación, modelo invocado; Granite devolvió 92/46 correctamente pero omitió la cita requerida (chequeo de citas fallido por cita faltante). Pregunta comparativa entre Leyes 5.109/14.478 → dos recuperaciones filtradas y modelo invocado; con k=1 llegaron arts. PBA 151 y Santa Fe 287, no pasajes sobre composición. Granite llamó “Ley de Jueces” a la Ley 14.478 y produjo una comparación no sustentada; `[1]`/`[2]` son números existentes y pasan el chequeo sintáctico, no el semántico. Pregunta “¿Cómo se vota en PBA?” → ruta ambigua, cero registros y `model_invoked=false`. Esto es una limitación real tanto de selección de evidencia como de generación; el filtro por jurisdicción no corrige relevancia intra-jurisdiccional.
**Limitaciones o pendientes:** 40/40 no valida preguntas fuera del fixture ni vigencia legal; el detector puede producir abstenciones conservadoras. El filtro separa fuentes pero no repara fragmentación ni recuperación fallida. Los smoke tests no comprueban apoyo semántico de citas. La revisión independiente del estudiante sigue pendiente. Los resultados anteriores de `TP2-RAG-05/06` permanecen congelados y sin reinterpretación.

### Homogeneización de generación y evaluación enrutada

**Decisión:** conservar `generate_answer()` por compatibilidad, con `DeprecationWarning` y documentación de que elude el enrutamiento; no usarla en código de aplicación ni evaluadores nuevos. La extracción/generación común quedó en `_generate_from_records()`, invocada desde `answer_question()` después de resolver la ruta. `scripts/evaluar_generacion.py` ahora usa `answer_question()` tanto en los cinco casos como en k=1/k=3. Sus resultados salen a archivos nuevos (`reporte_generacion_enrutada.json`, `validacion_generacion_enrutada.md`); el reporte TP2-RAG-06 y su revisión no se sobrescribieron ni se reutilizaron. El evaluador rechaza aplicar el protocolo nuevo sobre un reporte histórico sin enrutamiento.

**Ejecución observada:** `uv run python scripts/evaluar_generacion.py` completó cinco preguntas más una repetición k=1; la integridad Chroma antes/después fue `True`. Las cinco preguntas quedaron identificadas y filtradas: Nación art. 12, PBA art. 13, Santa Fe (recuperó art. 67/59/264, no el art. 4 pedido), y ambas ausentes a Nación. El modelo se abstuvo en los dos casos ausentes. En PBA dio 92/46 pero omitió la cita. En Santa Fe respondió sin abstenerse pese a que el artículo preguntado no llegó en contexto; la cita formal no valida el respaldo. El caso nacional tuvo vecinos del artículo 12 pero su contexto top-3 sigue sin incluir la continuación con el inciso d). El JSON guarda textos íntegros, ruta, filtro, respuesta original y chequeo de citas por caso.

**Validación de código:** tests de evaluación con fake retriever/modelo comprueban que los cinco casos y la comparación pasan por `answer_question()` y que un informe histórico no se reusa. `generate_answer()` sólo permanece cubierto por pruebas de compatibilidad/deprecación. No se ejecutó ni reconstruyó índice durante esta etapa.

**Ajuste posterior por consulta real:** la consulta «¿Cómo define la ley provincial santafesina al voto recurrido?» quedó inicialmente `ambiguous` porque “santafesina” se había codificado sólo como geografía, no como modificador de una referencia normativa. Se agregaron alias explícitos de legislación provincial santafesina (y bonaerense) al detector y una prueba de regresión con la consulta exacta. Ahora enruta a `santa_fe`; una ejecución real con k=5 recuperó el chunk 10 del artículo 4 (p. 1–4), que contiene literalmente la definición de voto recurrido, y Granite respondió citando `[2]` (cita formalmente válida). Reevaluación del fixture de 40: sigue 40/40; comparación retrieval completada, sin cambios al fixture ni al índice. Pruebas posteriores al ajuste: targeted `uv run pytest -q tests/test_03_bis_detectar_jurisdiccion.py tests/test_enrutar_preguntas.py` 38 passed; full `uv run pytest -q` 107 passed (16 avisos de deprecación intencionales en pruebas de compatibilidad); `git diff --check` limpio.

## 2026-11-13 — Stage C: laboratorio interactivo de fragmentación

**Objetivo y alcance:** añadir preparación/reutilización explícita de índices experimentales a la misma página Gradio, sin dashboard comparativo ni cambios al protocolo RAG.

**Decisiones y archivos:** `scripts/experimentos_fragmentacion.py` contiene pocas funciones de validación, identidad y preparación; reutiliza `fragmentar.build_chunks()`, `indexar.run_index(rebuild=False)` y `SemanticRetriever`. La identidad SHA-256 incluye size/overlap, `bge-m3`, contenido de los tres artículos JSONL, hash de `01_fragmentar.py` y versión de `langchain-text-splitters`. Los artefactos viven exclusivamente en `.chroma/experimentos/<hash>/` (ya ignorado). `scripts/05_interfaz_gradio.py` añade modo original/experimental, controles en caracteres, botón deliberado, estado por sesión, estados visibles y limpieza de resultados al cambiar parámetros. La consulta sigue llamando una vez a `answer_question()` con las rutas seleccionadas. Preparaciones/consultas se serializan dentro de la app. Se actualizaron `tests/test_05_interfaz_gradio.py`, nuevo `tests/test_experimentos_fragmentacion.py` y la sección Gradio de `README.md`. Los comentarios locales preexistentes en `scripts/02_indexar.py` se preservaron; no fueron cambios de esta implementación.

**Comandos y resultados:**
- `uv run pytest -q tests/test_experimentos_fragmentacion.py tests/test_05_interfaz_gradio.py`: **47 passed** en la primera pasada dirigida.
- `uv run pytest -q`: **169 passed**, 16 avisos esperados de compatibilidad/deprecación. Incluye validación antes de I/O, identidad determinista y dependiente del corpus, aislamiento incluso en 1000/150, reutilización sin indexador, errores/incompatibilidades, rutas/K, estado no aplicado e importación sin trabajo.
- `uv run python - <<'PY' … PY`: importaciones y CLIs `--help` independientes de fragmentar/indexar/recuperar/generar/evaluar_recuperacion/evaluar_generacion: OK.
- `curl --max-time 5 -sS http://localhost:11434/api/tags`: ambos modelos disponibles. `uv run python -u - <<'PY' … PY > /tmp/tp2-stage-c-smoke.log 2>&1`: preparación real 500/80, consulta vía `consultar()`, segunda preparación con `build_chunks`/`run_index` sustituidos por errores si se llamaban, y snapshots de integridad. Completó sin esos errores.
- `uv run python scripts/05_interfaz_gradio.py` (servidor de prueba detenido al terminar): navegador en `http://127.0.0.1:7860`, bloqueo experimental sin preparación, retorno al original y aclaración ambigua, preparación/reutilización 500/80, consulta real y limpieza de respuesta/fuentes/evidencia al editar size a 600. Sin errores de página ni mensajes de consola en las comprobaciones. `git diff --check`: limpio.

**Evidencia real de aislamiento y reutilización:** el baseline ahora sí existe: 828 IDs, SHA-256 de IDs `d991473aa3f76b07ecd9e35afa203bb1b26a2946b45a2d57f971d46059513df0`, manifest `93c7538fc463b647b056881df9a49001905d650c698f4dc95a0ee0f3ddd922e1`. Ambos snapshots permanecieron iguales antes/después del smoke, sin reconstrucción del original. Los hashes de todos los archivos de `datos/procesados/` y `evalucacion/` también permanecieron iguales. El experimento `a7ff887e474354132b0b98ff4de7932d23e18b4e5798a3c891f2ef7939a9c518` produjo **1292 chunks** (480 Nación, 248 PBA, 564 Santa Fe), embeddings de dimensión 1024. Segunda preparación: **Reutilizado**; mismos IDs/manifest experimentales y mismos hashes/mtime de chunks, reporte y manifest, sin fragmentación ni indexación nuevas. La primera preparación en CPU demoró varios minutos; cambiar controles no produjo ese trabajo.

**Consulta observada y límites:** «¿Cuántos diputados y senadores fija el artículo 13 de la Ley 5.109?» con K=3 automático recuperó, en orden, `pba_5109_art_13__chunk_0001`, `pba_5109_art_13__chunk_0002`, `pba_5109_art_124__chunk_0001` (TXT, sin páginas). La llamada directa respondió 92/46 con `[1]`; la repetición en navegador respondió 92/46 pero omitió citas y la interfaz mostró `citations_missing=True`. El tercer vecino es ajeno a la composición solicitada. No se afirma mejora de calidad por esta observación ni verificación semántica de citas. Un artefacto incompleto/incompatible se rechaza sin borrarlo: el reintento puede aprovechar chunks íntegros si el fallo ocurrió antes de crear el índice; no hay reparación automática de colecciones parciales. La serialización es dentro de un solo proceso Gradio, no un lock entre procesos; no preparar la misma configuración desde varios procesos a la vez. No se ejecutaron evaluadores ni se modificaron informes históricos, fuentes o artículos.

**Asistencia:** implementación, pruebas y registro por el agente de programación; no se atribuye al estudiante ninguna verificación personal no realizada.