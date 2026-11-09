# Bitácora de desarrollo — Trabajo Integrador 2 de PLN

**Proyecto:** RAG para consulta y comparación de legislación electoral argentina  
**Materia:** Procesamiento de Lenguaje Natural — Tecnicatura Superior en Ciencia de Datos e Inteligencia Artificial, IFTS N.º 24  
**Repositorio:** [jaymc-arg/PLN_tp2_2026](https://github.com/jaymc-arg/PLN_tp2_2026)  
**Período documentado:** inicio del proyecto al **8 de noviembre de 2026**  
**Última etapa incorporada:** `TP2-RAG-04` (commit `4fecc28`, 8 de noviembre de 2026, hora local).
**Estado:** corpus preparado e **indexado localmente en Chroma con `bge-m3`**. Existe una consulta exploratoria del índice; **aún no se evaluaron sistemáticamente la recuperación ni la generación de respuestas**.

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

**Evidencia:** [`scripts/preprocesar.py`](scripts/preprocesar.py), [`tests/test_preprocesar.py`](tests/test_preprocesar.py), [`reporte_preprocesamiento.json`](datos/procesados/reporte_preprocesamiento.json) y los tres archivos `*_articulos.jsonl`.

### Etapa 2 — Tratamiento de modificaciones normativas (`TP2-RAG-02`)

**Problema observado.** No todas las transcripciones entre comillas tienen el mismo significado: algunas reproducen antecedentes históricos y otras son el contenido sustantivo de artículos que modifican otras leyes. Una clasificación uniforme podía ocultar información pertinente o incorporar propuestas observadas como si fueran texto principal.

**Caso de Buenos Aires, artículo 13.** El TXT contiene el artículo 13 de la Ley 5.109, con **92 diputados y 46 senadores**, seguido de una nota que transcribe el artículo 26 de la Ley 14.086, que proponía **100 diputados y 50 senadores**, modificación observada por el Decreto 2997/2009. **Decisión:** conservar la nota y la transcripción en `texto`/`notas`, pero no incluirlas en `texto_principal`. El artículo 26 transcripto pertenece a otra ley y no debe confundirse con el artículo 26 propio de la Ley 5.109.

**Caso de Santa Fe, artículos 285 a 290.** Esos artículos introducen nuevas redacciones de disposiciones de otras leyes y reproducen el texto sustituto entre comillas. La primera versión del procesador clasificaba esas citas como transcripciones prescindibles y las retiraba de `texto_principal`. **Corrección:** etiquetarlas como `texto_modificatorio` y conservarlas también en la vista principal. Se comprobó que los seis artículos conservan la redacción completa.

**Límite asumido.** La anotación del artículo 25 bonaerense remite a un subrayado que no sobrevivió al copiado como TXT. Se decidió mantener la advertencia sin reconstruir arbitrariamente el tramo observado. La detección de anotaciones no reemplaza una interpretación jurídica de su vigencia.

**Evidencia:** clasificación implementada en [`scripts/preprocesar.py`](scripts/preprocesar.py), registros de los artículos citados y pruebas específicas en [`tests/test_preprocesar.py`](tests/test_preprocesar.py).

### Etapa 3 — Fidelidad documental y fragmentación (`TP2-RAG-03`)

**Problema 1: numeración duplicada en PBA.** La fuente bonaerense incluye **dos apariciones del artículo 151**, con contenidos diferentes y una nota sobre la numeración del texto ordenado. Durante una edición manual se había retirado la segunda aparición, reduciendo temporalmente el conteo de 155 a 154. **Corrección:** se recuperó literalmente desde el historial de Git; el procesador volvió a generar 155 registros y asignó identificadores distintos (`pba_5109_art_151` y `pba_5109_art_151__2`) sin inventar numeración jurídica.

**Problema 2: encabezados especiales.** Algunos títulos y capítulos de Santa Fe aparecen como `TÍTULO ÚNICO` o `CAPÍTULO ÚNICO`. Inicialmente podían quedar agrupados en el campo incorrecto. **Corrección:** se amplió el reconocimiento de encabezados, preservando separados los niveles estructurales.

**Problema 3: longitud variable de los artículos.** La unidad jurídica no coincide siempre con un tamaño adecuado para embeddings. Por ejemplo, los artículos 4 y 54 de Santa Fe son extensos. **Decisión:** fragmentar **dentro de cada artículo**, sin concatenar indiscriminadamente artículos o jurisdicciones. Se utilizó `RecursiveCharacterTextSplitter` con tamaño objetivo de **1.000 caracteres** y solapamiento configurado de **150 caracteres**, manteniendo el identificador del artículo y los metadatos en cada fragmento.

El script [`scripts/fragmentar.py`](scripts/fragmentar.py) genera una representación para búsqueda que repara saltos de línea visuales del PDF **sin alterar los registros originales**. También conserva los textos modificatorios sustantivos y evita indexar artículos nacionales derogados como encabezados vacíos: en esos casos utiliza una descripción expresamente derivada de la nota de derogación de la fuente.

**Observación sobre el solapamiento.** El valor 150 es un parámetro del splitter, no una garantía de 150 caracteres repetidos en todos los límites. Una inspección posterior encontró **112 límites sin repetición literal entre 169 pares de chunks consecutivos** de un mismo artículo. No se interpretó automáticamente como defecto; corresponde examinar su efecto sobre la recuperación en la etapa siguiente.

**Evidencia:** [`scripts/fragmentar.py`](scripts/fragmentar.py), [`chunks.jsonl`](datos/procesados/chunks.jsonl) y [`reporte_fragmentacion.json`](datos/procesados/reporte_fragmentacion.json).

### Etapa 4 — Embeddings e índice vectorial local (`TP2-RAG-04`)

**Objetivo y problema.** Los 828 fragmentos estaban disponibles en formato JSONL, pero todavía no podían consultarse mediante búsqueda semántica. Era necesario convertirlos en vectores, mantener la correspondencia entre cada vector y su evidencia documental y guardar el resultado de forma persistente. También había que evitar indexaciones duplicadas o reutilizar accidentalmente un índice construido con otro corpus o modelo.

**Decisiones y acciones:**

1. **Separar representación y generación.** Se eligió `bge-m3` a través de Ollama como modelo local de *embeddings*. Su función aquí es representar consultas y fragmentos en el mismo espacio vectorial; **no genera respuestas**. El modelo generativo previsto (`granite4:latest`) se incorporará en una etapa posterior.
2. **Utilizar Chroma como almacén persistente.** Se implementó [`scripts/indexar.py`](scripts/indexar.py), que lee [`chunks.jsonl`](datos/procesados/chunks.jsonl), conserva el texto del chunk sin reescribirlo y transforma sus atributos en metadatos admitidos por Chroma. La colección se denomina `electoral_laws` y se guarda en `.chroma/electoral_laws/`, excluida de Git por ser un artefacto reconstruible.
3. **Preservar la trazabilidad.** Cada vector se asocia al ID estable del chunk, al artículo de origen, la jurisdicción, la ley, el nombre del documento y los rangos de páginas disponibles. Para los TXT, que carecen de paginación original, se omiten los campos de página `null` en lugar de inventar una referencia.
4. **Proteger la consistencia de la indexación.** Se incorporó un manifiesto local con modelo, colección, endpoint, versión de firma y hash SHA-256 del archivo de chunks. Reejecutar con la misma firma reutiliza los registros existentes; una firma distinta impide la reutilización silenciosa. El parámetro `--rebuild` permite una reconstrucción explícita del índice administrado por el script.
5. **Fijar casos de prueba antes de evaluar los resultados.** Se creó [`evalucacion/preguntas.json`](evalucacion/preguntas.json) con **tres preguntas respondibles** —Nación artículo 12, PBA artículo 13 y Santa Fe artículo 4— y **dos sin respuesta en el corpus** —resultados de la elección presidencial de 2023 y gastos efectivamente rendidos por partidos en esa campaña—. Incluyen fuente esperada o justificación de ausencia. La intención es utilizar preguntas predefinidas, sin seleccionarlas después de ver qué recupera el sistema.

**Pruebas e incidentes observados.** Ollama informó versión `0.40.15` y el modelo local `bge-m3:latest` (identificador `790764642607`) devolvió vectores de **1.024 dimensiones**. La primera indexación registró **828 de 828 chunks**, con **828 IDs únicos** y metadatos coincidentes con los archivos de entrada. Una segunda ejecución mantuvo el conteo; se verificó además una reconstrucción con `--rebuild`. Al cambiar la firma de modelo a `bge-m3:latest`, el script rechazó reutilizar el índice creado con el nombre configurado `bge-m3` y una inspección posterior mostró que seguía intacto. Esa diferencia de nombre actúa como control estricto de configuración, aunque ambos nombres puedan referir localmente al mismo modelo.

**Consulta exploratoria, no evaluación definitiva.** Para la pregunta «¿Qué excepciones al deber de votar establece el artículo 12?», la búsqueda devolvió en las primeras tres posiciones: **Nación art. 12**, **PBA art. 4** y **Santa Fe art. 77**. El primer resultado coincide directamente con la consulta; los otros dos contienen disposiciones análogas de jurisdicciones diferentes. Esta observación indica que el índice recupera contenido semánticamente relacionado, pero también plantea la necesidad de **evaluar filtros por jurisdicción**. No demuestra todavía precisión global de recuperación, calidad de respuestas ni capacidad de abstenerse.

**Resultado y evidencia.** La documentación de la ejecución registra **39 pruebas automatizadas aprobadas**, además de verificaciones contra el Chroma persistente real. Las pruebas unitarias de [`tests/test_indexar.py`](tests/test_indexar.py) utilizan objetos simulados para comprobar contratos, firmas, metadatos e idempotencia, mientras que [`evalucacion/validacion_indexacion.md`](evalucacion/validacion_indexacion.md) deja constancia de los comandos y de las pruebas efectuadas con Ollama y Chroma reales. **La auditoría posterior de este repositorio verificó el código, las pruebas y los informes versionados; no reprodujo localmente los 828 embeddings ni accedió al índice `.chroma/` del equipo de desarrollo.**

**Límites reconocidos.** Indexar correctamente 828 registros no equivale a demostrar que se recupera el artículo adecuado para todas las preguntas. El índice no se versiona y debe reconstruirse en otros equipos con el modelo disponible. Tampoco está implementado todavía el paso de enviar contexto a un LLM para redactar respuestas.

**Evidencia:** [`scripts/indexar.py`](scripts/indexar.py), [`tests/test_indexar.py`](tests/test_indexar.py), [`evalucacion/preguntas.json`](evalucacion/preguntas.json) y [`evalucacion/validacion_indexacion.md`](evalucacion/validacion_indexacion.md).

## 3. Resultados medibles al cierre de `TP2-RAG-04`

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

Las seis advertencias no son seis fallos: incluyen prefacios o cierres ajenos al articulado, la duplicación documentada del artículo 151 y las observaciones normativas de los artículos 13 y 25 de PBA. El reporte no determina vigencia legal.

La etapa `TP2-RAG-03` cerró con **32 pruebas automatizadas aprobadas**, ejecuciones repetidas de los procesadores con resultados idénticos y verificación de SHA-256 de los archivos de origen. La etapa `TP2-RAG-04` registra **39 pruebas aprobadas** y comprobaciones adicionales del índice real. Estos son **resultados consignados por el agente de programación**; la inspección posterior del repositorio corroboró la implementación y los casos documentados, pero no equivale a una auditoría visual exhaustiva de las 70 páginas ni a una reconstrucción independiente del índice en otro equipo.

## 4. Criterios técnicos adoptados y límites reconocidos

- **Fidelidad antes que limpieza agresiva:** una nota o excepción mal eliminada puede cambiar el significado de una disposición. Por eso el texto completo permanece disponible aun cuando exista una vista simplificada para recuperación.
- **Trazabilidad:** es posible relacionar cada chunk con su artículo y documento, y reconstruir las salidas a partir de las fuentes versionadas.
- **Índice reconstruible y consistente:** Chroma conserva IDs y metadatos; un manifiesto asociado al hash de los chunks y al modelo impide mezclar configuraciones de forma inadvertida. La carpeta del índice no se sube al repositorio.
- **Distinción entre recuperar y responder:** el modelo `bge-m3` identifica similitud entre textos, pero no genera respuestas ni resuelve su validez jurídica. Su rendimiento debe evaluarse antes de incorporar la generación.
- **Sin resolución jurídica automática:** la presencia de un artículo en un texto actualizado o de una nota modificatoria no prueba por sí sola que todas las disposiciones relacionadas estén contempladas.
- **Tratamiento diferenciado de los formatos:** TXT sin páginas originales; PDF con página inicial y final del artículo. No se inventaron páginas para los TXT ni una correspondencia precisa por chunk que todavía no ha sido validada.
- **Limitaciones menores aún visibles:** ciertas vistas auxiliares pueden conservar puntuación aislada al retirar notas; la fragmentación recursiva puede dejar poco o ningún solapamiento efectivo. Ambos aspectos podrán contrastarse con resultados de búsqueda reales.
- **Alcance de la validación:** hasta aquí se verificaron **ingesta, estructura, conservación del contenido procesado, fragmentación y consistencia del índice vectorial**. Se inspeccionó una consulta de humo, pero **no se ha medido sistemáticamente la pertinencia de recuperación, la calidad de respuesta ni la abstención ante preguntas sin evidencia**.
- **Pendientes documentales menores identificados en la revisión:** la tabla inicial de `evalucacion/validacion_preprocesamiento.md` muestra **74** anotaciones bonaerenses, pero el reporte de auditoría y los registros JSONL actuales contienen **72**. Asimismo, el README conserva una frase desactualizada que describe los enlaces de las fuentes como desconocidos, aunque `datos/fuentes.csv` ya consigna enlaces. Son inconsistencias de documentación, no problemas del índice; se deben armonizar al preparar la entrega final.

## 5. Evidencia y reproducibilidad hasta esta etapa

Los documentos originales, el código y los JSONL están versionados. La base Chroma es local y **no** forma parte de Git; se reconstruye con las instrucciones del repositorio. El recorrido reproducible desde la raíz, con Ollama instalado y su servicio activo, es:

```bash
ollama pull bge-m3
uv sync
uv run python scripts/preprocesar.py
uv run python scripts/fragmentar.py
uv run python scripts/indexar.py
uv run pytest -q
```

Para reconstruir expresamente un índice propio ya creado:

```bash
uv run python scripts/indexar.py --rebuild
```

Las validaciones de extracción y fragmentación están en [`evalucacion/validacion_preprocesamiento.md`](evalucacion/validacion_preprocesamiento.md); las de vectorización y persistencia están en [`evalucacion/validacion_indexacion.md`](evalucacion/validacion_indexacion.md). Los reportes y el conjunto de preguntas en [`evalucacion/preguntas.json`](evalucacion/preguntas.json) ofrecen evidencia revisable sin depender únicamente de una explicación retrospectiva. La reproducción completa del RAG en un entorno limpio queda pendiente hasta que estén implementadas sus etapas restantes.

## 6. Próximos pasos — pendientes, no realizados

1. **Recuperación (`TP2-RAG-05`):** implementar una consulta reutilizable sobre Chroma con el mismo modelo de embeddings; inspeccionar ranking, `k`, filtros jurisdiccionales y cobertura de las **cinco preguntas ya fijadas**. Registrar los artículos efectivamente encontrados y los errores, sin ajustar retrospectivamente las preguntas.
2. **Generación (`TP2-RAG-06`):** utilizar `granite4:latest` u otro modelo local justificado con instrucciones explícitas y fragmentos recuperados como contexto; exigir citas y abstención cuando falte evidencia.
3. **Interfaz (`TP2-RAG-07`):** construir Gradio para consultar el sistema y mostrar por separado la respuesta y **los mismos fragmentos** enviados al modelo generativo.
4. **Evaluación (`TP2-RAG-08`):** ejecutar las tres consultas respondibles y las dos no respondibles ya definidas; consignar fuente esperada, recuperación, respuesta, errores y límites. Comparar parámetros de recuperación/fragmentación si resulta pertinente.
5. **Cierre (`TP2-RAG-09/10`):** corregir inconsistencias menores de documentación, comprobar instalación y ejecución en un directorio limpio, completar declaración del uso de IA, preparar demostración de hasta cinco minutos y efectuar la entrega.

## 7. Asistencia de IA y responsabilidades

La delimitación del problema, la selección del corpus, la revisión de los casos jurídicos y la planificación se trabajaron con asistencia conversacional de IA. La implementación y ejecución de scripts y pruebas se delegó parcialmente a un **agente de programación** bajo tareas acotadas y criterios de aceptación. Para `TP2-RAG-04`, el agente también documentó la ejecución contra servicios locales reales (Ollama y Chroma). Los resultados informados se contrastaron con el código, los archivos versionados y casos concretos; la verificación posterior no tuvo acceso al índice local no versionado.

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
