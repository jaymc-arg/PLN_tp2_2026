# Comparación Qwen 600/80 vs 1000/150

Fixture: `f25203f27d0dc12bdc430a47cc58911e1c023807d9179a7507e93cc200399275`; 38 casos, 32 positivos (dos comparaciones), seis negativos.
Mismo Qwen, Granite, prompt y temperatura 0. Filtros explícitos del fixture; K por jurisdicción. Top-5 real una vez por scope; generación reutiliza sus primeros tres mediante answer_question(). No se cambió Gradio ni los defaults.
Hit exige TODOS los artículos esperados; MRR usa 1/rango mínimo que reúne todos (máximo de primeros rangos locales). Recall cuenta artículos únicos por pregunta (34 pares pregunta/artículo esperados, no 34 artículos distintos del corpus). Negativos fuera de los denominadores de hit, evidencia y respuesta positiva.
La revisión es inspección del agente de código, no validación jurídica independiente. Sin review completa, las tasas semánticas NO deben interpretarse como resultados definitivos.

| Métrica | 1000/150 (cantidad/denominador; tasa) | 600/80 (cantidad/denominador; tasa) |
|---|---|---|
| hit_at_1 | 26/32; 0.8125 | 25/32; 0.7812 |
| hit_at_3 | 31/32; 0.9688 | 32/32; 1.0000 |
| hit_at_5 | 32/32; 1.0000 | 32/32; 1.0000 |
| mrr_at_5 | 28.583333333333332/32; 0.8932 | 28.333333333333332/32; 0.8854 |
| expected_article_recall_at_1 | 28/34; 0.8235 | 27/34; 0.7941 |
| expected_article_recall_at_3 | 33/34; 0.9706 | 34/34; 1.0000 |
| expected_article_recall_at_5 | 34/34; 1.0000 | 34/34; 1.0000 |
| both_articles_at_1 | 2/2; 1.0000 | 2/2; 1.0000 |
| both_articles_at_3 | 2/2; 1.0000 | 2/2; 1.0000 |
| both_articles_at_5 | 2/2; 1.0000 | 2/2; 1.0000 |
| full_evidence_at_3 | 28/32; 0.8750 | 25/32; 0.7812 |
| supported_answer | 8/32; 0.2500 | 12/32; 0.3750 |
| factually_complete_answer | 13/32; 0.4062 | 16/32; 0.5000 |
| citations_semantically_supported | 12/32; 0.3750 | 15/32; 0.4688 |
| correct_abstention | 5/6; 0.8333 | 5/6; 0.8333 |
| unsupported_negative_answer | 0/6; 0.0000 | 1/6; 0.1667 |
| generic_negative_nonanswer | 1/6; 0.1667 | 0/6; 0.0000 |
| invented_requested_negative_fact | 0/6; 0.0000 | 0/6; 0.0000 |
| exact_model_abstention | 5/6; 0.8333 | 5/6; 0.8333 |

Supported es estricto: hechos requeridos completos, sin extensión material ajena y referencias semánticamente pertinentes. Corrección factual y apoyo de citas se evalúan por separado del chequeo de formato.
Casos sin inspección: 0 / 0; etiquetas de incertidumbre needs_review: 1 / 0. Una incertidumbre no se presenta como fallo confirmado.
En negativas, la falta de abstención no implica necesariamente una ubicación/resultado inventado: se separan afirmaciones factuales no apoyadas (incluidas extensiones ajenas) y el hecho individual solicitado inventado.

## Resultados por jurisdicción

| Jurisdicción | Hit@3 base→600 | Pasaje completo@3 base→600 | Supported base→600 | Abstención correcta base→600 |
|---|---|---|---|---|
| comparativa | 2/2 (1.000) → 2/2 (1.000) | 2/2 (1.000) → 1/2 (0.500) | 0/2 (0.000) → 0/2 (0.000) | 0/0 (n/a) → 0/0 (n/a) |
| nacional | 10/10 (1.000) → 10/10 (1.000) | 9/10 (0.900) → 8/10 (0.800) | 4/10 (0.400) → 4/10 (0.400) | 1/1 (1.000) → 1/1 (1.000) |
| pba | 10/10 (1.000) → 10/10 (1.000) | 8/10 (0.800) → 8/10 (0.800) | 1/10 (0.100) → 3/10 (0.300) | 1/1 (1.000) → 1/1 (1.000) |
| santa_fe | 9/10 (0.900) → 10/10 (1.000) | 9/10 (0.900) → 8/10 (0.800) | 3/10 (0.300) → 5/10 (0.500) | 1/1 (1.000) → 1/1 (1.000) |
| sin_filtro | 0/0 (n/a) → 0/0 (n/a) | 0/0 (n/a) → 0/0 (n/a) | 0/0 (n/a) → 0/0 (n/a) | 2/3 (0.667) → 2/3 (0.667) |

## Resultados por tipo de caso

| Tipo de caso | Hit@3 base→600 | Pasaje completo@3 base→600 | Supported base→600 | Abstención correcta base→600 |
|---|---|---|---|---|
| articulo_breve | 9/9 (1.000) → 9/9 (1.000) | 9/9 (1.000) → 9/9 (1.000) | 2/9 (0.222) → 6/9 (0.667) | 0/0 (n/a) → 0/0 (n/a) |
| articulo_largo | 1/1 (1.000) → 1/1 (1.000) | 1/1 (1.000) → 1/1 (1.000) | 1/1 (1.000) → 0/1 (0.000) | 0/0 (n/a) → 0/0 (n/a) |
| articulo_mediano | 9/9 (1.000) → 9/9 (1.000) | 9/9 (1.000) → 7/9 (0.778) | 3/9 (0.333) → 2/9 (0.222) | 0/0 (n/a) → 0/0 (n/a) |
| comparativa | 2/2 (1.000) → 2/2 (1.000) | 2/2 (1.000) → 1/2 (0.500) | 0/2 (0.000) → 0/2 (0.000) | 0/0 (n/a) → 0/0 (n/a) |
| enumeracion_larga | 4/4 (1.000) → 4/4 (1.000) | 3/4 (0.750) → 2/4 (0.500) | 0/4 (0.000) → 2/4 (0.500) | 0/0 (n/a) → 0/0 (n/a) |
| multichunk | 1/1 (1.000) → 1/1 (1.000) | 0/1 (0.000) → 0/1 (0.000) | 0/1 (0.000) → 0/1 (0.000) | 0/0 (n/a) → 0/0 (n/a) |
| negativa | 0/0 (n/a) → 0/0 (n/a) | 0/0 (n/a) → 0/0 (n/a) | 0/0 (n/a) → 0/0 (n/a) | 3/4 (0.750) → 3/4 (0.750) |
| original | 2/3 (0.667) → 3/3 (1.000) | 1/3 (0.333) → 2/3 (0.667) | 0/3 (0.000) → 0/3 (0.000) | 2/2 (1.000) → 2/2 (1.000) |
| parafrasis | 3/3 (1.000) → 3/3 (1.000) | 3/3 (1.000) → 3/3 (1.000) | 2/3 (0.667) → 2/3 (0.667) | 0/0 (n/a) → 0/0 (n/a) |

## Índices y entorno

### 1000_150
Índice: `.chroma/electoral_laws_qwen3_0_6b`; chunks: `datos/procesados/chunks.jsonl`.
```json
{
  "runtime": {
    "embedding": {
      "ollama_server_version": "0.40.15",
      "ollama_python_client_version": "0.6.3",
      "api_base_url": "http://localhost:11434",
      "model_tag": "qwen3-embedding:0.6b",
      "model_digest": "ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d",
      "model_size_bytes": 639150858,
      "model_details": {
        "parent_model": "/Users/ollama/.ollama/models/blobs/sha256-06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439",
        "format": "gguf",
        "family": "qwen3",
        "families": [
          "qwen3"
        ],
        "parameter_size": "595.78M",
        "quantization_level": "Q8_0",
        "context_length": 32768,
        "embedding_length": 1024,
        "runner": "ggml"
      },
      "temperature": 0
    },
    "generation": {
      "ollama_server_version": "0.40.15",
      "ollama_python_client_version": "0.6.3",
      "api_base_url": "http://localhost:11434",
      "model_tag": "granite4:latest",
      "model_digest": "4235724a127c0f86dcc0247d67c20148705d6dd2319164014d92f71d607f4773",
      "model_size_bytes": 2099520825,
      "model_details": {
        "parent_model": "/Users/runner/.ollama/models/blobs/sha256-5c7ac4aead1bcf4c8da9534ed72cc632d005aeed6547f1e8662ccdfae688364e",
        "format": "gguf",
        "family": "granite",
        "families": [
          "granite"
        ],
        "parameter_size": "3.4B",
        "quantization_level": "Q4_K_M",
        "context_length": 131072,
        "embedding_length": 2560,
        "runner": "ggml"
      },
      "temperature": 0
    },
    "prompt_sha256": "977716dc3cd4769a0690da2e0b2f796d5e8322f9f03cfd33a2259dd5f450e350",
    "versions": {
      "langchain-chroma": "0.2.6",
      "langchain-ollama": "0.3.10",
      "chromadb": "1.5.9",
      "ollama": "0.6.3"
    }
  },
  "fragmentation": {
    "chunk_size_caracteres": 1000,
    "chunk_overlap_caracteres": 150,
    "longitud": "caracteres Python del texto del chunk; splitter recursivo",
    "total_chunks": 828,
    "jurisdicciones": {
      "nacional": {
        "chunks": 289,
        "min": 86,
        "mediana": 506,
        "max": 998
      },
      "pba": {
        "chunks": 175,
        "min": 50,
        "mediana": 356,
        "max": 995
      },
      "santa_fe": {
        "chunks": 364,
        "min": 46,
        "mediana": 489.0,
        "max": 1000
      }
    },
    "chunks_mayores_que_chunk_size": [],
    "registros_sin_vista": [],
    "limitaciones": [
      "Los chunks heredan rango de páginas del artículo completo; no se asignan páginas internas sin mapeo validado.",
      "Las longitudes no implican calidad de recuperación; embeddings y evaluación están fuera de alcance.",
      "Las descripciones de artículos derogados sólo repiten la nota explícita de la fuente y no afirman vigencia."
    ]
  },
  "index_verification": {
    "initial_count": 828,
    "final_count": 828,
    "missing_ids_completed": 0,
    "chunks_sha256": "381218f917d28ad9ba66f887173971d56da222d451a6314009e2245ef99e3871",
    "manifest": {
      "managed_by": "tp2-rag-04",
      "signature_version": 1,
      "embedding_model": "qwen3-embedding:0.6b",
      "ollama_base_url": "http://localhost:11434",
      "collection": "electoral_laws",
      "chunks_sha256": "381218f917d28ad9ba66f887173971d56da222d451a6314009e2245ef99e3871"
    },
    "dimensions": 1024,
    "chroma_configuration": {
      "hnsw": {
        "space": "l2",
        "ef_construction": 100,
        "ef_search": 100,
        "max_neighbors": 16,
        "resize_factor": 1.2,
        "sync_threshold": 1000
      },
      "spann": null,
      "embedding_function": null
    },
    "temporary_reconstruction_matches_exact_bytes": true,
    "splitter_code_sha256": "fa83359cdef9caa1f8d09c9078f1232301f2f53af1d1a5160fcd30ec9fb28d9a",
    "splitter_version": "0.3.11"
  },
  "index_before": {
    "count": 828,
    "ids_sha256": "d991473aa3f76b07ecd9e35afa203bb1b26a2946b45a2d57f971d46059513df0",
    "manifest_sha256": "c5131ae5fb7641cd55a9a370c1399eb0dc0bba3b30a2872fc4dc983642d64449",
    "ids_match_chunks": true
  },
  "index_after": {
    "count": 828,
    "ids_sha256": "d991473aa3f76b07ecd9e35afa203bb1b26a2946b45a2d57f971d46059513df0",
    "manifest_sha256": "c5131ae5fb7641cd55a9a370c1399eb0dc0bba3b30a2872fc4dc983642d64449",
    "ids_match_chunks": true
  },
  "protected_inputs_unchanged": true,
  "execution_summary": {
    "case_count": 38,
    "retrieval_scope_queries": 40,
    "model_invocations": 38,
    "runtime_errors": 0
  }
}
```

### 600_80
Índice: `.chroma/experimentos/6e7d71baa70d370e317a0bc678415048235cbabcda839600713d02b50f8de63e/indice`; chunks: `.chroma/experimentos/6e7d71baa70d370e317a0bc678415048235cbabcda839600713d02b50f8de63e/chunks.jsonl`.
```json
{
  "runtime": {
    "embedding": {
      "ollama_server_version": "0.40.15",
      "ollama_python_client_version": "0.6.3",
      "api_base_url": "http://localhost:11434",
      "model_tag": "qwen3-embedding:0.6b",
      "model_digest": "ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d",
      "model_size_bytes": 639150858,
      "model_details": {
        "parent_model": "/Users/ollama/.ollama/models/blobs/sha256-06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439",
        "format": "gguf",
        "family": "qwen3",
        "families": [
          "qwen3"
        ],
        "parameter_size": "595.78M",
        "quantization_level": "Q8_0",
        "context_length": 32768,
        "embedding_length": 1024,
        "runner": "ggml"
      },
      "temperature": 0
    },
    "generation": {
      "ollama_server_version": "0.40.15",
      "ollama_python_client_version": "0.6.3",
      "api_base_url": "http://localhost:11434",
      "model_tag": "granite4:latest",
      "model_digest": "4235724a127c0f86dcc0247d67c20148705d6dd2319164014d92f71d607f4773",
      "model_size_bytes": 2099520825,
      "model_details": {
        "parent_model": "/Users/runner/.ollama/models/blobs/sha256-5c7ac4aead1bcf4c8da9534ed72cc632d005aeed6547f1e8662ccdfae688364e",
        "format": "gguf",
        "family": "granite",
        "families": [
          "granite"
        ],
        "parameter_size": "3.4B",
        "quantization_level": "Q4_K_M",
        "context_length": 131072,
        "embedding_length": 2560,
        "runner": "ggml"
      },
      "temperature": 0
    },
    "prompt_sha256": "977716dc3cd4769a0690da2e0b2f796d5e8322f9f03cfd33a2259dd5f450e350",
    "versions": {
      "langchain-chroma": "0.2.6",
      "langchain-ollama": "0.3.10",
      "chromadb": "1.5.9",
      "ollama": "0.6.3"
    }
  },
  "fragmentation": {
    "chunk_size_caracteres": 600,
    "chunk_overlap_caracteres": 80,
    "longitud": "caracteres Python del texto del chunk; splitter recursivo",
    "total_chunks": 1119,
    "jurisdicciones": {
      "nacional": {
        "chunks": 406,
        "min": 83,
        "mediana": 411.5,
        "max": 600
      },
      "pba": {
        "chunks": 219,
        "min": 50,
        "mediana": 342,
        "max": 600
      },
      "santa_fe": {
        "chunks": 494,
        "min": 46,
        "mediana": 423.5,
        "max": 600
      }
    },
    "chunks_mayores_que_chunk_size": [],
    "registros_sin_vista": [],
    "limitaciones": [
      "Los chunks heredan rango de páginas del artículo completo; no se asignan páginas internas sin mapeo validado.",
      "Las longitudes no implican calidad de recuperación; embeddings y evaluación están fuera de alcance.",
      "Las descripciones de artículos derogados sólo repiten la nota explícita de la fuente y no afirman vigencia."
    ]
  },
  "index_verification": {
    "initial_count": 1119,
    "final_count": 1119,
    "missing_ids_completed": 0,
    "chunks_sha256": "a2d17dea09bf2f8ef4aa273fbb5758a5add4d4c1afcdf5f143e653ec9f0b286a",
    "manifest": {
      "managed_by": "tp2-rag-04",
      "signature_version": 1,
      "embedding_model": "qwen3-embedding:0.6b",
      "ollama_base_url": "http://localhost:11434",
      "collection": "electoral_laws",
      "chunks_sha256": "a2d17dea09bf2f8ef4aa273fbb5758a5add4d4c1afcdf5f143e653ec9f0b286a"
    },
    "dimensions": 1024,
    "chroma_configuration": {
      "hnsw": {
        "space": "l2",
        "ef_construction": 100,
        "ef_search": 100,
        "max_neighbors": 16,
        "resize_factor": 1.2,
        "sync_threshold": 1000
      },
      "spann": null,
      "embedding_function": null
    },
    "temporary_reconstruction_matches_exact_bytes": true,
    "splitter_code_sha256": "fa83359cdef9caa1f8d09c9078f1232301f2f53af1d1a5160fcd30ec9fb28d9a",
    "splitter_version": "0.3.11"
  },
  "index_before": {
    "count": 1119,
    "ids_sha256": "bbda9489ecec0d511dbadda693736a26819884bc3f444fa2080e8b7d802a3496",
    "manifest_sha256": "5890c90943f7a5565349191c650150ba35e20f09178e4c848f29aa7f20110bf4",
    "ids_match_chunks": true
  },
  "index_after": {
    "count": 1119,
    "ids_sha256": "bbda9489ecec0d511dbadda693736a26819884bc3f444fa2080e8b7d802a3496",
    "manifest_sha256": "5890c90943f7a5565349191c650150ba35e20f09178e4c848f29aa7f20110bf4",
    "ids_match_chunks": true
  },
  "protected_inputs_unchanged": true,
  "execution_summary": {
    "case_count": 38,
    "retrieval_scope_queries": 40,
    "model_invocations": 38,
    "runtime_errors": 0
  }
}
```

## Pares por pregunta

| ID | Hit@1/3/5 y RR: base → 600 | Pasaje K3: base → 600 | Hechos: base → 600 | Citas semánticas: base → 600 | Respuesta: base → 600 | Diagnóstico |
|---|---|---|---|---|---|---|
| nacional_respondible_deber_votar | 1/1/1; 1.000 → 1/1/1; 1.000 | partial → partial | partial → partial | full → full | partially_supported → partially_supported | Regresión dentro de partial: la base tiene a-c y certificación, 600 solo a-b. Ninguna recupera d/optatividad. |
| pba_respondible_representacion | 1/1/1; 1.000 → 1/1/1; 1.000 | full → full | full → full | missing → missing | partially_supported → partially_supported | Empate: 92/46 y evidencia completa, pero ambas respuestas sin citas. |
| santa_fe_respondible_autoridad_mesa | 0/0/1; 0.250 → 0/1/1; 0.500 | partial → full | partial → full | partial → partial | partially_supported → partially_supported | Mejora de pasaje: definición exacta de rango 4 a 2. 600 agrega requisitos de [3] pero cita [1][2], por eso no es supported estricto. |
| ausente_resultado_electoral | n/a (negativa) → n/a (negativa) | none → none | not_applicable → not_applicable | not_applicable → not_applicable | abstained_correctly → abstained_correctly | Hechos not_applicable→not_applicable; citas not_applicable→not_applicable. Mismo pasaje K3. |
| ausente_gasto_real_partido | n/a (negativa) → n/a (negativa) | none → none | not_applicable → not_applicable | not_applicable → not_applicable | abstained_correctly → abstained_correctly | Hechos not_applicable→not_applicable; citas not_applicable→not_applicable. Mismo pasaje K3. |
| nacional_electores_edad | 1/1/1; 1.000 → 1/1/1; 1.000 | full → full | partial → partial | full → full | partially_supported → partially_supported | Hechos partial→partial; citas full→full. Mismo pasaje K3. |
| nacional_licencia_laboral | 1/1/1; 1.000 → 1/1/1; 1.000 | full → full | full → full | full → full | supported → supported | Hechos full→full; citas full→full. Mismo pasaje K3. |
| nacional_subregistros_electores | 1/1/1; 1.000 → 1/1/1; 1.000 | full → full | partial → full | partial → full | partially_supported → supported | Hechos partial→full; citas partial→full. Mismo pasaje K3. |
| nacional_registro_infractores | 1/1/1; 1.000 → 1/1/1; 1.000 | full → full | partial → partial | missing → partial | partially_supported → partially_supported | Hechos partial→partial; citas missing→partial. Mismo pasaje K3. |
| nacional_difusion_padrones | 1/1/1; 1.000 → 0/1/1; 0.500 | full → full | full → partial | full → none | supported → partially_supported | Hechos full→partial; citas full→none. Mismo pasaje K3. |
| nacional_reclamos_padron | 1/1/1; 1.000 → 1/1/1; 1.000 | full → full | full → full | full → full | supported → supported | Hechos full→full; citas full→full. Mismo pasaje K3. |
| nacional_boleta_unica | 1/1/1; 1.000 → 1/1/1; 1.000 | full → full | uncertain → full | partial → full | needs_review → supported | Hechos uncertain→full; citas partial→full. Mismo pasaje K3. |
| nacional_designacion_autoridades | 1/1/1; 1.000 → 1/1/1; 1.000 | full → full | full → full | full → partial | supported → partially_supported | Hechos full→full; citas full→partial. Mismo pasaje K3. |
| nacional_eleccion_presidencial | 1/1/1; 1.000 → 1/1/1; 1.000 | full → partial | partial → partial | partial → missing | partially_supported → partially_supported | Hechos partial→partial; citas partial→missing. Cambio de suficiencia del contexto. |
| pba_electores | 1/1/1; 1.000 → 1/1/1; 1.000 | full → full | partial → partial | missing → partial | partially_supported → partially_supported | Hechos partial→partial; citas missing→partial. Mismo pasaje K3. |
| pba_exenciones_deber_votar | 1/1/1; 1.000 → 1/1/1; 1.000 | partial → partial | incorrect → partial | partial → partial | partially_supported → partially_supported | Intercambio: 600 recupera optatividad pero pierde causales; la base incluso inventa obligatoriedad/transporte. No mejora completa. |
| pba_documentos_habilitantes | 0/1/1; 0.500 → 0/1/1; 0.500 | full → full | full → full | full → full | supported → supported | Hechos full→full; citas full→full. Mismo pasaje K3. |
| pba_distritos_municipales | 1/1/1; 1.000 → 1/1/1; 1.000 | full → full | partial → partial | partial → partial | partially_supported → partially_supported | Hechos partial→partial; citas partial→partial. Mismo pasaje K3. |
| pba_septima_seccion | 0/1/1; 0.500 → 0/1/1; 0.500 | partial → partial | partial → incorrect | missing → missing | partially_supported → partially_supported | Ambas sin lista de municipios; 600 además confunde Séptima con Capital. |
| pba_junta_electoral_composicion | 1/1/1; 1.000 → 1/1/1; 1.000 | full → full | full → full | missing → full | partially_supported → supported | Hechos full→full; citas missing→full. Mismo pasaje K3. |
| pba_junta_electoral_funciones | 1/1/1; 1.000 → 1/1/1; 1.000 | full → full | partial → full | full → full | partially_supported → supported | Hechos partial→full; citas full→full. Mismo pasaje K3. |
| pba_presidente_mesa_requisitos | 1/1/1; 1.000 → 0/1/1; 0.500 | full → full | partial → partial | partial → partial | partially_supported → partially_supported | Hechos partial→partial; citas partial→partial. Mismo pasaje K3. |
| pba_proclamacion_intendente | 1/1/1; 1.000 → 1/1/1; 1.000 | full → full | partial → partial | partial → partial | partially_supported → partially_supported | Hechos partial→partial; citas partial→partial. Mismo pasaje K3. |
| santa_fe_ambito_aplicacion | 0/1/1; 0.500 → 0/1/1; 0.500 | full → full | full → full | full → full | supported → supported | Hechos full→full; citas full→full. Mismo pasaje K3. |
| santa_fe_electores_extranjeros | 1/1/1; 1.000 → 1/1/1; 1.000 | full → partial | full → partial | full → full | supported → partially_supported | Hechos full→partial; citas full→full. Cambio de suficiencia del contexto. |
| santa_fe_capacidad_mesa | 1/1/1; 1.000 → 1/1/1; 1.000 | full → full | incorrect → incorrect | partial → partial | partially_supported → partially_supported | Ambas deforman excepciones de 60 electores pese a evidencia completa: errores de generación distintos. |
| santa_fe_convocatoria_primarias | 1/1/1; 1.000 → 1/1/1; 1.000 | full → full | full → full | full → full | supported → supported | Hechos full→full; citas full→full. Mismo pasaje K3. |
| santa_fe_autoridades_mesa | 1/1/1; 1.000 → 1/1/1; 1.000 | full → full | partial → full | partial → partial | partially_supported → partially_supported | 600 mejora orden/supuestos, pero mantiene referencia no pertinente [2]. |
| santa_fe_exenciones_voto | 0/1/1; 0.333 → 0/1/1; 0.333 | full → partial | full → partial | none → none | partially_supported → partially_supported | Hechos full→partial; citas none→none. Cambio de suficiencia del contexto. |
| santa_fe_horario_constitucion_mesa | 1/1/1; 1.000 → 1/1/1; 1.000 | full → full | full → full | partial → full | partially_supported → supported | Hechos full→full; citas partial→full. Mismo pasaje K3. |
| santa_fe_boleta_unica | 0/1/1; 0.500 → 1/1/1; 1.000 | full → full | full → full | partial → full | partially_supported → supported | Hechos full→full; citas partial→full. Mismo pasaje K3. |
| santa_fe_cuenta_campana | 1/1/1; 1.000 → 1/1/1; 1.000 | full → full | partial → full | full → full | partially_supported → supported | Hechos partial→full; citas full→full. Mismo pasaje K3. |
| comparativa_nacional_santa_fe_electores | 1/1/1; 1.000 → 1/1/1; 1.000 | full → partial | partial → incorrect | partial → partial | partially_supported → partially_supported | Ambos artículos en rango 1 en ambos brazos; 600 pierde dos años de residencia y concluye erróneamente que ambos exigen nacionalidad argentina. |
| comparativa_nacional_santa_fe_bup | 1/1/1; 1.000 → 1/1/1; 1.000 | full → full | partial → partial | partial → partial | partially_supported → partially_supported | Scopes fijados en ambos brazos ante ambigüedad del detector. 600 explicita mejor alcance nacional/exclusividad SF, pero añade una excepción no apoyada. |
| ausente_ganador_gobernador_pba_2023 | n/a (negativa) → n/a (negativa) | none → none | not_applicable → not_applicable | not_applicable → not_applicable | abstained_correctly → abstained_correctly | Hechos not_applicable→not_applicable; citas not_applicable→not_applicable. Mismo pasaje K3. |
| ausente_gastos_campana_sf_2025 | n/a (negativa) → n/a (negativa) | none → none | not_applicable → not_applicable | not_applicable → not_applicable | abstained_correctly → abstained_correctly | Hechos not_applicable→not_applicable; citas not_applicable→not_applicable. Mismo pasaje K3. |
| ausente_votos_presidenciales_2023 | n/a (negativa) → n/a (negativa) | none → none | not_applicable → not_applicable | not_applicable → not_applicable | abstained_correctly → abstained_correctly | Hechos not_applicable→not_applicable; citas not_applicable→not_applicable. Mismo pasaje K3. |
| ausente_escuela_asignada | n/a (negativa) → n/a (negativa) | none → none | not_applicable → incorrect | full → partial | partially_supported → partially_supported | Ninguna abstención explícita. Base: normas genéricas sin ubicación inventada; 600 añade la atribución errónea de Ley 5.109 a CABA. |

## Victorias, regresiones y empates de 600/80

Pasaje compara none < partial < full. Respuesta supported usa un indicador binario estricto; etiquetas intermedias siguen detalladas por caso.

| Indicador | Victorias | Regresiones | Empates | Pendientes |
|---|---:|---:|---:|---:|
| hit_at_3 | 1 | 0 | 31 | 0 |
| passage_k3 | 1 | 4 | 27 | 0 |
| supported_answer | 6 | 3 | 22 | 1 |
| correct_negative_abstention | 0 | 0 | 6 | 0 |
| negative_no_unsupported_facts | 0 | 1 | 5 | 0 |

Listas de IDs en `resultados_pareados.json`. Agregados por jurisdicción, tipo y ambos en los JSON de cada brazo.

## Diagnóstico y conclusión

### Conclusión principal
**600/80 no demuestra una mejora conjunta de evidencia y calidad frente a 1000/150.** Hit@3 mejora 31/32→32/32, pero evidencia completa K3 cae 28/32→25/32 (−9.375 puntos porcentuales). Hit@1 baja 26/32→25/32; Hit@5 queda 32/32. MRR@5 baja 0.893229→0.885417 (−0.0078125). No se cambia el default 1000/150.
Las respuestas supported estrictas sí aumentan 8/32→12/32 (+12.5 puntos): 6 victorias, 3 regresiones, 22 empates y 1 par incierto por el alcance de único medio en la base nacional BUP. No se cuenta esa incertidumbre como derrota confirmada. Corrección factual completa: 13/32→16/32. Son anotaciones conservadoras del agente, no precisión jurídica independiente.
En pasajes K3 hay 1 victoria (definición SF art. 4), 4 regresiones (fórmula presidencial indivisible; dos años de residencia extranjera SF; causales finales SF art. 77; comparación de electores) y 27 empates. Las mejoras de citación no compensan automáticamente la pérdida de requisitos/condiciones en el contexto.
### Tres casos originales
- **Nación art. 12:** mismo hit de artículo en rango 1, pero 1000/150 aporta a-c y certificación y 600/80 solo a-b. Ninguno recupera d/optatividad en K3 ni K5. Empate coarse partial con regresión de contenido dentro de la categoría; raíces: fragmentación/ranking, no cambio de modelo.
- **PBA art. 13:** ambos conservan el pasaje 92 diputados/46 senadores y ambos modelos contestan esos números sin referencias. Evidencia full en ambos; problema de generación/citación, no de retrieval.
- **Santa Fe art. 4:** la definición pasa de rango 4 (fuera de K3) a rango 2. La base usa el art. 67 como apoyo indirecto y lo atribuye al 4. 600/80 da la definición correcta, pero añade requisitos provenientes de [3] mientras cita [1][2]. Mejora real de evidencia, sin respuesta completamente citada según la rúbrica estricta.
### Comparaciones y negativas
Ambas comparaciones reúnen ambos artículos en K=1/3/5 local en los dos brazos: 2/2 casos y recall de los cuatro artículos 4/4. Eso no implica suficiente pasaje ni buena respuesta. En electores, 600/80 pierde dos años de residencia continua en SF y concluye erróneamente que ambos códigos exigen nacionalidad argentina. En BUP, los scopes se fijaron explícitamente porque el detector puro considera ambigua la segunda pregunta; no se modificó el detector ni la pregunta y no se contó una aclaración como acierto.
Abstenciones claras: **5/6 en ambos brazos**. escuela_asignada recibe una explicación de normas, no una declaración de insuficiencia del corpus. La base no inventa ubicación ni un hecho personal; 600/80 tampoco inventa escuela, pero atribuye Ley 5.109 a CABA. Afirmaciones materiales no apoyadas en negativas: 0/6→1/6; hecho individual solicitado inventado: 0/6 en ambos. Son indicadores distintos, no complementos obligatorios de la abstención.
### Límites y revisión
185 pruebas unitarias no son evidencia de calidad del modelo: la evidencia experimental son las 80 consultas top-5 y 76 invocaciones reales aquí guardadas. Las anclas literales solo asisten inspección y consistencia; las citas, omisiones, cambios de condiciones, atribuciones y extensiones fueron revisadas por el agente. Una referencia con formato válido puede apuntar a multas/abrogaciones en vez de la norma afirmada, o invertir una excepción (mesa especial con menos de 60 electores).
38 casos deliberadamente seleccionados, una generación por brazo y pregunta, sin réplicas ni estimación de variabilidad: no permiten extrapolar desempeño general ni atribuir cada diferencia de redacción exclusivamente a chunking. Temperatura 0 no es una garantía de reproducibilidad bit a bit. La revisión no establece vigencia o validez jurídica ni reemplaza verificación personal del estudiante. No se alteraron prompts, modelo, distancia, reglas de enrutamiento por defecto, Gradio ni parámetros de fragmentación de producción.
Ver revisión por caso, citas literales y faltantes en revision_pareada.json y en review de cada traza. Los informes históricos de cinco casos solo se protegieron por hash; no se usaron sus métricas, citas o diagnósticos como evidencia para los 38 nuevos casos.

## Ejecución y verificación

- Fixture reemplazado en su ruta por el usuario y validado antes de búsquedas: SHA-256 `f25203f27d0dc12bdc430a47cc58911e1c023807d9179a7507e93cc200399275`; 38 IDs únicos, 32 respondibles, seis negativas y dos comparaciones de dos jurisdicciones. Las 32 referencias se contrastaron con texto_principal sin inconsistencias. No se archivó una copia histórica ni se creó preguntas_fragmentacion.json.
- Inspección local previa: candidato `6e7d71baa70d370e317a0bc678415048235cbabcda839600713d02b50f8de63e` = Qwen 600/80, chunks/reporte/manifest/Chroma existentes y 1119 IDs completos, **cero faltantes**. También se encontraron `e52e…` (otra configuración Qwen, 1114 chunks y 0 IDs) y `a7ff…` (BGE, 1292 IDs), no usados ni reparados. No se creó un experimento duplicado ni un índice baseline nuevo.
- Baseline: `.chroma/electoral_laws_qwen3_0_6b` con `datos/procesados/chunks.jsonl`, 828 IDs completos. Ambos chunks/reports corresponden a reconstrucción temporal byte a byte con los mismos tres artículos JSONL y código/versión actual del divisor. Temporales eliminados; originales sin reescritura.
- Ejecución real: `uv run python -u scripts/evaluar_fragmentacion_pareada.py --ejecutar > /tmp/tp2-paired-run.log 2>&1`. 40 scopes top-5 y 38 generaciones por brazo; cero errores. K=1/3/5 se derivaron del mismo ranking. answer_question recibió un adaptador de lectura de esos resultados reales, no respuestas simuladas ni una segunda recuperación. No se llamaron rutinas de embedding de documentos porque los dos índices ya estaban completos.
- Revisión: lectura de las respuestas completas, comprobación de hechos/condiciones contra fuentes y pasajes suministrados, lectura adicional de fragmentos de citas/afirmaciones problemáticas. `criterios_pasajes.json` conserva anclas de fuente; `revision_pareada.json` contiene 76 juicios, hashes de respuesta y citas cotejadas. Inspección por agente de código, no revisión legal/humana independiente.
- Render sin nuevas consultas: `uv run python scripts/evaluar_fragmentacion_pareada.py --review evalucacion/experimentos_fragmentacion/revision_pareada.json`. Los reportes JSON y este Markdown incluyen agregados por jurisdicción/tipo y pares con IDs de victorias/regresiones/empates.
- Tests dirigidos: `uv run pytest -q tests/test_fragmentacion_pareada.py tests/test_indexar.py tests/test_recuperar.py tests/test_evaluar_generacion.py` → 33 passed en la primera pasada. Suite final `uv run pytest -q` → **185 passed**, 16 avisos de deprecación esperados. Los contratos históricos usan datos sintéticos temporales; no se presentan como resultados del fixture de 38 casos.
- Verificación final mediante Python: fixture y todos los hashes protegidos iguales, IDs/manifest de ambos índices iguales a antes de la ejecución, todos los textos/metadatos persistidos iguales a sus chunks, dimensiones 1024 y configuración HNSW/L2 idéntica. Digest del Qwen y del Granite instalados sin cambio respecto del comienzo. Todas las citas manuales son substrings de los chunks realmente enviados y cada contexto coincide exactamente con el builder compartido.
- Preservación: preguntas_jurisdiccion.json, reportes/revisiones históricos, artículos JSONL y chunks originales sin cambios. No se restauró ni regeneró el SVG histórico que ya estaba eliminado al iniciar. No se ejecutó --rebuild, no se cambiaron defaults ni Gradio. El override opcional de jurisdicciones múltiples en answer_question solo fija el scope del fixture en este ensayo; sin ese argumento el comportamiento previo se conserva.

Los JSON conservan textos íntegros, fuentes/páginas, distancias, recall por artículo, diagnósticos y denominadores por jurisdicción/tipo. Las distancias no son confianza ni probabilidades.
