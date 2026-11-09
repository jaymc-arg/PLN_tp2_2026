# TP2-RAG-04 — fixtures e indexación local

## Preguntas fijadas antes de probar retrieval

`preguntas.json` contiene cinco fixtures manuales definidos antes de cualquier consulta semántica: tres respondibles desde Nación art. 12, PBA art. 13 y Santa Fe art. 4; dos ausentes del corpus (resultado presidencial 2023 y rendiciones reales de gastos de campaña). Cada positivo registra fuente/ID y respuesta de referencia. No se cambiaron a la luz del smoke query.

## Entorno local verificado

- Ollama servidor/CLI: **0.40.15**, atendiendo en `http://localhost:11434`.
- Modelo local: `bge-m3:latest`, ID `790764642607`, descarga reportada `1.2 GB`; `ollama show bge-m3`: arquitectura BERT, 566.70M parámetros, contexto 8192, dimensión de embedding **1024**, F16, capacidad `embedding`, licencia mostrada MIT.
- Python 3.12.7; `langchain-chroma` 0.2.6; `langchain-ollama` 0.3.10; `chromadb` 1.5.9; cliente Python `ollama` 0.6.3.

## Índice construido y comprobado

`scripts/indexar.py` lee `datos/procesados/chunks.jsonl`, crea `langchain_core.documents.Document` con `page_content` idéntico a `texto`, omite metadata nula (páginas TXT) y conserva el rango PDF de artículo. Persiste colección `electoral_laws` bajo `.chroma/electoral_laws/`, excluida de Git. La firma local incluye modelo, endpoint localhost, colección, versión de esquema y SHA-256 de `chunks.jsonl`.

Comandos ejecutados:

```text
ollama --version                                           -> ollama version 0.40.15
ollama pull bge-m3                                         -> success
uv run python - <<'PY' [OllamaEmbeddings.embed_query]      -> vector length 1024
uv run python scripts/indexar.py                           -> Indexados 828/828; dimensión 1024
uv run python scripts/indexar.py                           -> Indexados 828/828; rerun idempotente
consulta Chroma get(include=['metadatas'])                  -> 828 IDs; 828 únicos; conjunto = IDs del JSONL
comparación de metadata almacenada con chunks.jsonl         -> todos los IDs coinciden; TXT sin claves de página,
                                                              PDF con páginas y demás campos esperados
uv run python scripts/indexar.py --rebuild                 -> reconstruyó e indexó 828/828 desde cero
uv run python scripts/indexar.py                           -> después de rebuild: 828/828, sin duplicados
uv run python scripts/indexar.py --model bge-m3:latest     -> rechaza firma distinta antes de reutilizar;
                                                              inspección posterior: índice original intacto, 828 IDs
uv run pytest -q                                            -> 39 passed (14.31 s)
```

El directorio real midió **8.9 MB** en la inspección posterior. Las pruebas automatizadas validan contrato y casos de configuración mediante dobles de prueba; la cuenta, IDs, metadata y reconstrucción anteriores son además verificaciones hechas contra el Chroma persistente real.

## Smoke query (inspección, no evaluación de respuestas)

Pregunta de humo configurada: “¿Qué excepciones al deber de votar establece el artículo 12?”. El ranking observado fue:

1. `nacional_19945_art_12__chunk_0001` — Nación, art. 12, `ley_nacional.txt` (coincidencia directa con el tema consultado).
2. `pba_5109_art_4__chunk_0001` — PBA, art. 4, `ley_pba.txt` (norma análoga sobre exenciones al voto).
3. `santa_fe_14478_art_77__chunk_0001` — Santa Fe, art. 77, pp. 23–23 (norma análoga sobre eximición del sufragio).

Esto confirma que se produjo una lista semántica y visible de fuentes; **no** demuestra corrección de respuestas ni recuperación correcta en las cinco preguntas fijadas. La presencia de disposiciones análogas de otras jurisdicciones es una observación útil para futura evaluación/filtros, no una medición de precisión. No se ejecutó evaluación formal del retrieval ni generación.

## Configuración, límites y reproducción

El índice se crea con `bge-m3` para documentos y consultas, usando explícitamente `http://localhost:11434`. IDs estables se usan en upsert; rerun no aumenta el número. La firma impide reutilizar silenciosamente otra configuración. `--rebuild` eliminó y recreó el índice propio seleccionado; no afecta fuentes ni chunks. `.chroma/` está en `.gitignore` y no se versiona.

`datos/fuentes.csv` conserva desconocidos URL oficial verificadas, fecha de recuperación y permisos/condiciones de redistribución para las tres fuentes. No se rellenaron por inferencia ni se descargó material suplementario.

Para reproducir localmente: instalar/iniciar Ollama, `ollama pull bge-m3`, `uv sync`, generar chunks si hace falta (`uv run python scripts/preprocesar.py && uv run python scripts/fragmentar.py`) y ejecutar `uv run python scripts/indexar.py`. Para recrear: `uv run python scripts/indexar.py --rebuild`. Las consultas son sólo inspección; generación, API de retrieval de la siguiente etapa, Gradio y evaluación de respuestas siguen fuera de esta tarea.
