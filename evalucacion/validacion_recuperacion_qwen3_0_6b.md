# TP2-RAG-05 — recuperación semántica: qwen3-embedding:0.6b

Se usó Chroma persistente y Ollama `qwen3-embedding:0.6b`; no hubo generación. Distancia nativa de Chroma: un valor menor indica un vecino más cercano, no una probabilidad de corrección.
Hit@k/MRR se calculan a nivel de artículo y no prueban que un chunk contenga la respuesta.

## Métricas agregadas sobre las tres positivas

| Modo | Denominador | Hit@1 | Hit@3 | Hit@5 | MRR@5 |
|---|---:|---:|---:|---:|---:|
| Sin filtro | 3 | 0.667 | 0.667 | 0.667 | 0.667 |
| Filtrada por jurisdicción | 3 | 0.667 | 0.667 | 1.000 | 0.750 |

Denominador: tres positivas; los fallos aportan 0 al MRR; negativas excluidas. Los chunks repetidos permanecen en el ranking, y el hit por artículo es binario.

## Inspección diagnóstica (una fila por pregunta fija)

La inspección textual manual la realizó el agente de código sobre los chunks recuperados completos; no equivale a revisión jurídica ni a verificación personal del estudiante.

| Pregunta | Evidencia esperada | Hit@1 sin filtro | Hit@3 sin filtro | Hit@5 sin filtro | RR@5 sin filtro | Hit@1 filtrada | Hit@3 filtrada | Hit@5 filtrada | RR@5 filtrada | Cambio top-1/top-3 por filtro | Cobertura pasaje top-3 (sin/con filtro) | Fuente/chunk/distancia top-3 sin filtro | Limitación observada | Diagnóstico | Experimento futuro |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| nacional_respondible_deber_votar | ['nacional_19945_art_12']; El artículo 12 exceptúa a jueces y auxiliares obligados a concurrir a sus oficinas; a quienes el día de la elección estén a más de 500 km del lugar de votación por motivos razonables y acrediten su comparecencia ante la autoridad policial; a personas enfermas o imposibilitadas por fuerza mayor debidamente justificadas; y a personal de servicios públicos cuyas tareas impidan votar, con comunicación y certificación del empleador. La propia norma dice que las exenciones son optativas para el elector. | 1 | 1 | 1 | 1.000 | 1 | 1 | 1 | 1.000 | top-1=igual; top-3=cambió | sin filtro: partial: `nacional_19945_art_12__chunk_0001`: “c) Los enfermos o imposibilitados por fuerza mayor, suficientemente comprobada, que les impida asistir al acto.”; `pba_5109_art_4__chunk_0001`: “b) Los funcionarios y empleados que por sus ocupaciones, como tales, no puedan hacerlo.”; `santa_fe_14478_art_120__chunk_0001`: “ARTÍCULO 120.- No emisión del sufragio en elecciones primarias. Justificación.”; filtrada: partial: `nacional_19945_art_12__chunk_0001`: “Tales electores se presentarán el día de la elección a la autoridad policial más próxima, la que extenderá certificación escrita que acredite la comparecencia;”; `nacional_19945_art_88__chunk_0001`: “Artículo 88. - Derecho del elector a votar.”; `nacional_19945_art_18__chunk_0001`: “Artículo 18: Registro de infractores al deber de votar.” | nacional_19945_art_12__chunk_0001 (ley_nacional.txt; d=0.565965); pba_5109_art_4__chunk_0001 (ley_pba.txt; d=0.746566); santa_fe_14478_art_120__chunk_0001 (ley_sta_fe.pdf, pp. 33–33; d=0.769865) | El rango 1 enumera a-c y la justificación policial/médica, pero no contiene la causal d, su comunicación/certificación ni el carácter optativo de las exenciones. La continuación nacional no llega al top-5. Los rangos 2 y 3 son regímenes provinciales y no completan la enumeración nacional. | fragmentación y recuperación; confusión de jurisdicción en vecinos | Evaluar por separado recuperación del fragmento contiguo, sin incorporarla en este ensayo de modelo. |
| pba_respondible_representacion | ['pba_5109_art_13']; El texto principal del artículo 13 fija la representación en 92 diputados y 46 senadores. La propuesta observada de 100 diputados y 50 senadores aparece en una nota histórica/editorial y no es la respuesta que establece el texto principal del registro. | 1 | 1 | 1 | 1.000 | 1 | 1 | 1 | 1.000 | top-1=igual; top-3=cambió | sin filtro: yes: `pba_5109_art_13__chunk_0001`: “Fíjase la representación legislativa de la Provincia en noventa y dos (92) diputados y cuarenta y seis (46) senadores”; `santa_fe_14478_art_133__chunk_0001`: “La Cámara de Diputados se compone de cincuenta (50) legisladores”; `nacional_19945_art_166__chunk_0001`: “las legislaturas en cada provincia procederán a la elección de un Senador”; filtrada: yes: `pba_5109_art_13__chunk_0001`: “Fíjase la representación legislativa de la Provincia en noventa y dos (92) diputados y cuarenta y seis (46) senadores”; `pba_5109_art_11__chunk_0001`: “Para las elecciones de concejales y consejeros escolares”; `pba_5109_art_151__chunk_0001`: “A efectos de la adecuación de la normativa a los requerimientos específicos del sistema de voto electrónico seleccionado” | pba_5109_art_13__chunk_0001 (ley_pba.txt; d=0.732698); santa_fe_14478_art_133__chunk_0001 (ley_sta_fe.pdf, pp. 36–36; d=0.830141); nacional_19945_art_166__chunk_0001 (ley_nacional.txt; d=0.840519) | El rango 1 sí contiene las dos cantidades requeridas. Los siguientes dos vecinos son Santa Fe y una disposición nacional transitoria sobre senadores de 1995; no deben mezclarse con la composición bonaerense. | acierto del pasaje y ruido interjurisdiccional | Medir el efecto del filtro sin extrapolar este acierto a otras preguntas. |
| santa_fe_respondible_autoridad_mesa | ['santa_fe_14478_art_4']; Es la persona que ejerce la presidencia de la mesa receptora de votos y, ante ausencia o impedimento, quien la reemplaza conforme al orden de designación establecido en el Código. | 0 | 0 | 0 | 0.000 | 0 | 0 | 1 | 0.250 | top-1=cambió; top-3=cambió | sin filtro: no: `nacional_19945_art_14__chunk_0001`: “Todas las funciones que esta ley atribuye a las autoridades de mesa son irrenunciables”; `santa_fe_14478_art_64__chunk_0001`: “Autoridades de mesa en establecimientos de detención.”; `pba_5109_art_45__chunk_0001`: “Los Presidentes de mesa tendrán a sus inmediatas órdenes la fuerza pública necesaria para el cumplimiento de sus funciones.”; filtrada: no: `santa_fe_14478_art_64__chunk_0001`: “son designadas por el Juez Electoral entre personas electoras del circuito electoral”; `santa_fe_14478_art_67__chunk_0001`: “Cada mesa electoral tiene como única autoridad quien ejerce la presidencia de mesa y dos (2) suplentes que la auxilian y reemplazan, en el orden de sus designaciones”; `santa_fe_14478_art_68__chunk_0001`: “Requisitos para ser autoridad de mesa.” | nacional_19945_art_14__chunk_0001 (ley_nacional.txt; d=0.871011); santa_fe_14478_art_64__chunk_0001 (ley_sta_fe.pdf, pp. 21–21; d=0.988991); pba_5109_art_45__chunk_0001 (ley_pba.txt; d=1.031048) | Ninguno de estos tres pasajes es la definición pedida del art. 4. El primer resultado es nacional; el segundo describe designación en establecimientos de detención y el tercero atribuciones respecto de la fuerza pública en PBA. El artículo esperado tampoco aparece en top-5 sin filtro. | recuperación fallida y confusión jurisdiccional | Investigar por separado la priorización de definiciones legales, sin alterar este experimento. |
| ausente_resultado_electoral | hecho ausente: resultados presidenciales 2023 o rendiciones reales | n/a | n/a | n/a | n/a | — | — | — | — | n/a (negativa; sin filtro) | no: El top-3 trata distribución normativa vinculada con elecciones anteriores, requisitos para ser elector y una elección de senador de 1995. Los rangos 4–5 son designación del secretario electoral y reglas para elegir parlamentarios del Mercosur. Ninguno contiene el partido ganador ni votos efectivamente contados en la presidencial de 2023: no se pueden deducir de normas. | santa_fe_14478_art_159__chunk_0002 (ley_sta_fe.pdf, pp. 42–42; d=1.145493); santa_fe_14478_art_25__chunk_0001 (ley_sta_fe.pdf, pp. 9–9; d=1.173420); nacional_19945_art_166__chunk_0003 (ley_nacional.txt; d=1.180156) | vecinos legales próximos no son la evidencia factual pedida | not answerable | incorporar fuente oficial de resultados/rendiciones en una etapa futura, no inferirla de leyes |
| ausente_gasto_real_partido | hecho ausente: resultados presidenciales 2023 o rendiciones reales | n/a | n/a | n/a | n/a | — | — | — | — | n/a (negativa; sin filtro) | no: Los vecinos son obligaciones de cuenta bancaria, topes de aportes y límites de gastos santafesinos; los restantes describen fuentes de financiamiento y multas bonaerenses por plazos de campaña. No son rendiciones ni montos ejecutados por cada partido en la campaña presidencial de 2023. Un tope permitido no acredita gasto real. | santa_fe_14478_art_169__chunk_0001 (ley_sta_fe.pdf, pp. 44–44; d=0.894338); santa_fe_14478_art_173__chunk_0001 (ley_sta_fe.pdf, pp. 45–45; d=0.971084); santa_fe_14478_art_172__chunk_0001 (ley_sta_fe.pdf, pp. 45–45; d=1.012834) | vecinos legales próximos no son la evidencia factual pedida | not answerable | incorporar fuente oficial de resultados/rendiciones en una etapa futura, no inferirla de leyes |

## Filtros, k, paráfrasis y evidencia

Para cada positiva se consultó una vez sin filtro y una vez con jurisdicción; las dos negativas se consultaron sin filtro. Cada condición usa k=5; top-1/top-3/top-5 se obtienen cortando el mismo ranking. El JSON conserva todos los textos top-5, IDs, fuentes/páginas cuando existen y distancias nativas.

Paráfrasis separada (fuera de métricas): “¿En qué situaciones puede una persona electora quedar exceptuada de votar en una elección nacional?”. Qwen coloca el artículo nacional 12 en rango 1 también con la paráfrasis independiente. En top-3 siguen dos artículos bonaerenses: exenciones y protección frente a detención/obstrucción del tránsito al comicio. Solo el primero aporta parte de la respuesta nacional; la continuación del art. 12 no aparece en top-5. La mejora de rango no resuelve la fragmentación.

Comparación k=1/k=3 desde el mismo ranking (nacional_respondible_deber_votar): {'question_id': 'nacional_respondible_deber_votar', 'k1_coverage': 'partial: rango 1 con a-c, sin la continuación nacional que contiene d y condiciones adicionales.', 'k3_coverage': 'partial: los otros dos pasajes son PBA art. 4 y Santa Fe art. 120; no completan el artículo nacional. Aumenta evidencia visible, no la cobertura de esa respuesta.', 'diagnosis': 'Se usaron cortes del mismo ranking Qwen top-5, no una consulta adicional; no se interpreta la norma provincial como una excepción nacional.'}

El preview numerado completo se deriva de los mismos chunks recuperados y se guarda en `evalucacion/reporte_recuperacion_qwen3_0_6b.json`; se validaron orden, IDs, etiquetas y texto sin truncar. No se construye prompt ni se invoca un generador.

Chroma devuelve vecinos cercanos aunque el corpus no responda. Un resultado no vacío no demuestra answerability ni se usa un umbral universal de distancia para abstener.

Integridad de índice antes/después: `True`. Distancias reales representativas: `evalucacion/distancias_recuperacion_qwen3_0_6b.svg`. No se midió corrección de respuestas generadas.

## Comparación bge-m3 (histórico) vs qwen3-embedding:0.6b

Baseline conservado: `evalucacion/reporte_recuperacion.json`. Mismas preguntas, chunks, filtros y k=5; sin prefijos/instrucciones adicionales para consultas ni documentos. No se ejecutó generación.

Las distancias de espacios de embeddings diferentes NO son puntajes de calidad comparables.

| Modo | Métrica | BGE-M3 | Qwen | Δ absoluto |
|---|---|---:|---:|---:|
| unfiltered | hit_at_1 | 0.667 | 0.667 | +0.000 |
| unfiltered | hit_at_3 | 0.667 | 0.667 | +0.000 |
| unfiltered | hit_at_5 | 0.667 | 0.667 | +0.000 |
| unfiltered | mrr_at_5 | 0.667 | 0.667 | +0.000 |
| jurisdiction_filtered | hit_at_1 | 0.667 | 0.667 | +0.000 |
| jurisdiction_filtered | hit_at_3 | 0.667 | 0.667 | +0.000 |
| jurisdiction_filtered | hit_at_5 | 0.667 | 1.000 | +0.333 |
| jurisdiction_filtered | mrr_at_5 | 0.667 | 0.750 | +0.083 |

| Pregunta/modo | Primer rango BGE→Qwen | H@1/3/5 BGE→Qwen | RR@5 BGE→Qwen | Pasaje BGE→Qwen | Otra jurisdicción top-3/top-5 BGE→Qwen |
|---|---|---|---|---|---|
| nacional_respondible_deber_votar/unfiltered | 1→1 | 1/1/1→1/1/1 | 1.000→1.000 | partial→partial | 2/3→2/2 |
| pba_respondible_representacion/unfiltered | 1→1 | 1/1/1→1/1/1 | 1.000→1.000 | yes→yes | 1/3→2/4 |
| santa_fe_respondible_autoridad_mesa/unfiltered | None→None | 0/0/0→0/0/0 | 0.000→0.000 | no→no | 1/2→2/3 |
| nacional_respondible_deber_votar/jurisdiction_filtered | 1→1 | 1/1/1→1/1/1 | 1.000→1.000 | partial→partial | 0/0→0/0 |
| pba_respondible_representacion/jurisdiction_filtered | 1→1 | 1/1/1→1/1/1 | 1.000→1.000 | yes→yes | 0/0→0/0 |
| santa_fe_respondible_autoridad_mesa/jurisdiction_filtered | None→4 | 0/0/0→0/0/1 | 0.000→0.250 | no→no | 0/0→0/0 |

Rangos de pasajes específicos (`None` = no recuperado en top-5; no significa ausente del corpus):

```json
{
  "nacional_19945_art_12__chunk_0002": {
    "baseline": {
      "nacional_respondible_deber_votar/unfiltered": null,
      "nacional_respondible_deber_votar/jurisdiction_filtered": null
    },
    "current": {
      "nacional_respondible_deber_votar/unfiltered": null,
      "nacional_respondible_deber_votar/jurisdiction_filtered": null
    }
  },
  "santa_fe_14478_art_4__chunk_0001": {
    "baseline": {
      "santa_fe_respondible_autoridad_mesa/unfiltered": null,
      "santa_fe_respondible_autoridad_mesa/jurisdiction_filtered": null
    },
    "current": {
      "santa_fe_respondible_autoridad_mesa/unfiltered": null,
      "santa_fe_respondible_autoridad_mesa/jurisdiction_filtered": 4
    }
  }
}
```

Paráfrasis separada, primer rango del artículo esperado: 4→1.

La mejora cuantitativa fija se limita al modo filtrado: Santa Fe pasa de no recuperar el artículo esperado en top-5 a rango 4. Hit@5 sube de 2/3 a 3/3 (+1/3) y MRR@5 de 2/3 a 3/4 (+1/12). Hit@1 y Hit@3 quedan en 2/3, igual que todas las métricas sin filtro. Nación y PBA conservan primer rango 1 en ambos modos.
El pasaje definitorio santafesino completo está ahora en rango 4 filtrado, no en top-3 ni en top-5 global. La cobertura estricta del pasaje solicitado en top-3 permanece Nación parcial, PBA sí, Santa Fe no. El art. 67 ofrece apoyo relacionado, pero no prueba la atribución al art. 4. La continuación nacional con causal d y carácter optativo sigue fuera de top-5 en ambos modelos y ambos modos.
No hay mejora general del aislamiento jurisdiccional sin filtro: Nación conserva 2 vecinos de otra jurisdicción en top-3 (top-5 pasa de 3 a 2), PBA empeora de 1 a 2 en top-3 (3 a 4 en top-5) y Santa Fe de 1 a 2 en top-3 (2 a 3 en top-5). Con filtro explícito ambos modelos tienen cero vecinos de otra jurisdicción.
La paráfrasis separada mejora el primer rango del artículo nacional de 4 con BGE-M3 a 1 con Qwen, fuera del agregado fijo. La comparación k=1/k=3 no añade las excepciones nacionales faltantes; las dos preguntas ausentes siguen devolviendo vecinos normativos que no establecen los hechos pedidos.
Este cambio de tag/modelo, con su cuantización propia, se ensayó sin instrucciones adicionales ni cambios de chunks, filtro, distancia o ranking. Tres positivas y dos ausentes no estiman precisión general ni vigencia legal; las distancias de modelos distintos no son magnitudes de calidad comparables. La inspección del agente y las comprobaciones de citas no sustituyen revisión jurídica ni verificación personal del estudiante.

## Entorno y preservación

```json
{
  "python": "3.12.7",
  "ollama_server": "0.40.15",
  "embedding_model": {
    "tag": "qwen3-embedding:0.6b",
    "digest": "ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d",
    "quantization": "Q8_0",
    "returned_dimensions": 1024
  },
  "packages": {
    "langchain-chroma": "0.2.6",
    "langchain-ollama": "0.3.10",
    "chromadb": "1.5.9",
    "ollama": "0.6.3"
  },
  "query_encoding": "Texto original sin prefijo ni instrucción añadida; mismo OllamaEmbeddings que el baseline.",
  "index_build_command": "uv run python scripts/02_indexar.py",
  "new_index": {
    "path": ".chroma/electoral_laws_qwen3_0_6b",
    "unique_ids": 828,
    "manifest": {
      "managed_by": "tp2-rag-04",
      "signature_version": 1,
      "embedding_model": "qwen3-embedding:0.6b",
      "ollama_base_url": "http://localhost:11434",
      "collection": "electoral_laws",
      "chunks_sha256": "381218f917d28ad9ba66f887173971d56da222d451a6314009e2245ef99e3871"
    },
    "all_metadata_and_texts_match_original_chunks": true,
    "smoke_top3_ids": [
      "nacional_19945_art_12__chunk_0001",
      "pba_5109_art_4__chunk_0001",
      "pba_5109_art_9__chunk_0001"
    ]
  },
  "frozen_questions_sha256": "5b0c0f545671a2a34ea68de096c10c6fb22914bb7b3410011c19df9f40d3de4e",
  "source_chunks_unchanged": true,
  "all_preexisting_evaluation_files_unchanged": true,
  "historical_artifacts_sha256": {
    "evalucacion/reporte_recuperacion.json": "636d08e2e0c35d512b98a5524509d1f8b6ee7a054bad0bb164d89d68a9704249",
    "evalucacion/revision_manual_recuperacion.json": "f035e1b1f0d57dc1ac9d0f2f9c5421a6825206024c23621947a2722249c1d7ee",
    "evalucacion/validacion_recuperacion.md": "8ec612edfeca9a8d67afd78cd14d775dbcd6e3dffff2988b10f38c90c49d3b6b",
    "evalucacion/distancias_recuperacion.svg": "b9eed94fd5c0a8a01f04accacd409dfeb3f6bbc0e4e7e76a817ba9c6661b1ed8"
  },
  "bge_index_preservation": {
    "ids_count": 828,
    "ids_sha256": "d991473aa3f76b07ecd9e35afa203bb1b26a2946b45a2d57f971d46059513df0",
    "manifest_sha256": "93c7538fc463b647b056881df9a49001905d650c698f4dc95a0ee0f3ddd922e1",
    "ids_and_manifest_unchanged": true
  },
  "protocol_runs": {
    "positive_queries": 6,
    "negative_queries": 2,
    "independent_paraphrase_queries": 1,
    "k": 5,
    "k1_k3_derived_from_same_ranking": true
  }
}
```
