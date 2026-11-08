# Validación de TP2-RAG-01

Validación ejecutada por el agente sobre los archivos locales. No constituye evaluación RAG, dictamen sobre vigencia ni revisión personal del estudiante.

## Resultados de la ejecución final

| Fuente | Artículos | Anotaciones | Referencias detectadas | Advertencias |
|---|---:|---:|---:|---:|
| Nacional | 208 | 146 | 156 | 1 |
| PBA | 155 | 72 | 92 | 4 |
| Santa Fe | 296 | 6 | 29 | 1 |

Las referencias cuentan menciones únicas dentro de cada artículo, no normas únicas del corpus. El reporte JSON contiene los hashes SHA-256 de los originales, los textos fuera de artículos y las 140 líneas de layout retiradas del PDF (encabezado y marca de página en cada una de las 70 páginas).

## Cotejos representativos con las fuentes

| Caso | Fuente y comprobación | Salida observada |
|---|---|---|
| Nacional art. 12 | TXT UTF-8, desde `Artículo 12. -` hasta antes del 13; comparación íntegra tras normalizar espacios | Conserva deber, incisos a–d, certificaciones, plazo de diez días, carácter optativo y nota de sustitución; la nota se separa sólo en la vista auxiliar |
| PBA art. 2 | TXT, tramo completo entre arts. 2 y 3 | Conserva remisión literal a Ley 11.700; no agrega requisitos de esa ley |
| PBA art. 3 | TXT, inciso b de estado y condición | `INCISO DEROGADO POR LEY 11.833` y texto histórico permanecen juntos en un pasaje anotado; no se elimina del campo `texto` |
| PBA art. 13 | TXT, tramo completo hasta 13 bis | Vista principal conserva noventa y dos diputados; nota y transcripción observada conservan cien diputados, sin crear falsos artículos 26 o 13 |
| Santa Fe art. 4 | PDF original p. 1 renderizado con `pdftoppm` y leído visualmente; contraste con `pdftotext -layout` y extracción `PyPDFLoader`; continuación extraída pp. 2–4 | Un único registro pp. 1–4; definiciones desde a. agrupación política hasta al. voto recurrido; el capítulo siguiente queda fuera del artículo |

Los originales TXT son los propios documentos utilizados, no una extracción adicional. No se volvió a recortar el nacional. Las tres huellas SHA-256 finales coinciden con las medidas antes de implementar; las pruebas también las fijan explícitamente.

## Hallazgos y advertencias pendientes

- Nacional: encabezado previo a la primera rúbrica conservado como no clasificado.
- PBA: prefacio conservado; observación del art. 13; observación del art. 25 que depende de subrayado perdido; dos artículos 151, con IDs `pba_5109_art_151` y `pba_5109_art_151__2`.
- Santa Fe: prefacio y cierre de sanción/firmas/decreto conservados fuera de artículos. No hay números duplicados entre las rúbricas detectadas.
- **Fallo observado durante la inspección:** un primer detector reconocía como segunda rúbrica la remisión `artículo 172.` envuelta al inicio de una línea de la p. 45, dentro del art. 173. Se corrigió exigiendo mayúscula inicial en las rúbricas del corpus y se agregó regresión sintética y real. El conteo final santafesino es 296, no 297. Esto no generaliza a documentos cuyas rúbricas estén en minúscula.
- Las transcripciones de artículos modificatorios santafesinos permanecen completas en `texto` y se distinguen como `transcripcion_citada`. Las notas y la vista principal no determinan fuerza jurídica.
- No hubo páginas vacías ni caracteres de reemplazo U+FFFD en la extracción PDF inspeccionada. No se realizó OCR ni cotejo visual exhaustivo de las 70 páginas.
- No se verificaron URL oficial, fecha de recuperación ni permiso de redistribución: datos pendientes en `fuentes.csv`. No se descargó material suplementario.
- El notebook citado por la tarea no está disponible en este checkout.

## Comandos ejecutados

Pruebas dirigidas durante el desarrollo:

- `uv run pytest -q -k 'not real and not deterministic'`: 8 aprobadas.
- `uv run pytest -q -k real`: 6 aprobadas inicialmente; la inspección posterior encontró el falso límite citado y motivó una regresión.
- `uv run pytest -q -k 'real or headings'`: 10 aprobadas después de corregirlo.

Verificación final completa:

```text
uv sync                                     OK
uv run python preprocesar.py                 OK; 208 / 155 / 296
uv run pytest -q                             15 passed (9.89 s)
sha256sum datos/procesados/*                 huellas guardadas en archivo temporal
uv run python preprocesar.py                 OK; segunda ejecución
sha256sum -c <archivo temporal de huellas>    4 archivos OK, incluido reporte
sha256sum datos/ley_nacional.txt datos/ley_pba.txt datos/ley_sta_fe.pdf  sin cambios
uv sync --locked                            OK
uv export --format requirements-txt --no-hashes --output-file requirements.txt  OK
git diff --check                            OK
```

Se intentó también `uv lock --check`, pero **uv 0.5.4 no admite esa opción**; se reemplazó por `uv sync --locked`, que sí terminó correctamente. El CSV también se abrió con `csv.DictReader`: tres filas válidas sin columnas sobrantes.

No se verificó reproducción integral del futuro RAG en un directorio fresco: queda fuera de esta etapa.
