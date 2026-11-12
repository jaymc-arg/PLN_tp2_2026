# Evaluación de enrutamiento jurisdiccional

Fixture independiente: `40` casos; SHA-256 `3ef5fa9188caefb85876c531bf95b12a5db9612389b17a08583db5e4f45a06fe`. No se usa Ollama/Chroma para clasificar.

Coincidencia exacta status+jurs.: 40/40 = 1.000.
Cobertura filtro único: 21/21.
Ruteo correcto entre casos identificables: 21/21.
Misruteo dañino: 0/40 = 0.000.
Aclaración adecuada: 15/15.

## Matriz de confusión (filas reales, columnas predichas)

| Real \ Predicho | identified | ambiguous | comparative | unspecified | unsupported |
|---|---:|---:|---:|---:|---:|
| identified | 21 | 0 | 0 | 0 | 0 |
| ambiguous | 0 | 7 | 0 | 0 | 0 |
| comparative | 0 | 0 | 4 | 0 | 0 |
| unspecified | 0 | 0 | 0 | 4 | 0 |
| unsupported | 0 | 0 | 0 | 0 | 4 |

## Métricas por jurisdicción

| Jurisdicción | Precisión (TP/predichos) | Recall (TP/reales) |
|---|---:|---:|
| nacional | 9/9 (1.0) | 9/9 (1.0) |
| pba | 10/10 (1.0) | 10/10 (1.0) |
| santa_fe | 10/10 (1.0) | 10/10 (1.0) |

## Errores observados

- Ninguno en este fixture; esto no valida casos no representados.

## Impacto en recuperación local

Índice intacto: `True`. Cobertura auto 3/3; aclaraciones que evitaron retrieval: 0; fugas cross-jurisdicción auto: 0 chunks.
- **baseline_unfiltered** (denominador E2E=3; no ruteadas cuentan como fallo): hit_at_1=2/3 (0.667), hit_at_3=2/3 (0.667), hit_at_5=2/3 (0.667), mrr_at_5=2.0/3 (0.667)
- **oracle_filter** (denominador E2E=3; no ruteadas cuentan como fallo): hit_at_1=2/3 (0.667), hit_at_3=2/3 (0.667), hit_at_5=2/3 (0.667), mrr_at_5=2.0/3 (0.667)
- **automatic_filter** (denominador E2E=3; no ruteadas cuentan como fallo): hit_at_1=2/3 (0.667), hit_at_3=2/3 (0.667), hit_at_5=2/3 (0.667), mrr_at_5=2.0/3 (0.667)
Los hits son a nivel artículo, no demuestran cobertura completa del pasaje. Consulte el JSON para resultados íntegros y páginas.
Inspección manual de los tres pasajes: `nacional_respondible_deber_votar`: El top incluye el chunk 1 del art. 12, pero no la continuación con inciso d), certificación del empleador y carácter optativo; el artículo aparece como hit sin cubrir todo el pasaje pedido. `pba_respondible_representacion`: El chunk superior del art. 13 contiene el dato preguntado (92 diputados y 46 senadores); no se interpreta la nota histórica como texto principal. `santa_fe_respondible_autoridad_mesa`: El art. 4 no aparece en top-5; el vecino art. 67 trata autoridades de mesa pero no es la definición consultada. El art. 4 existe en los chunks versionados.
