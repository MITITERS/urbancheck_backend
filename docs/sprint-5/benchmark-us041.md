# Benchmark de anonimización (US-041)

- Fecha: 2026-10-15 10:00
- Set: `anonymization` (37 imágenes)
- Máquina: aarch64, 10 CPU, 7.7 GB de RAM, Python 3.14.2

## Tasa de detección

| Tipo | Detectados | Etiquetados | Tasa |
| --- | --- | --- | --- |
| Rostros | 175 | 189 | 92.6% |
| Patentes | 28 | 30 | 93.3% |
| Total | 203 | 219 | 92.7% |

## Tiempo por imagen

Promedio 786 ms · mediana 814 ms · p95 961 ms · máximo 994 ms

## Falsos negativos

| Archivo | Tipo | Detectados | Etiquetados |
| --- | --- | --- | --- |
| street_cars_01.jpg | Rostros | 2 | 3 |
| street_cars_05.jpg | Rostros | 0 | 1 |
| street_cars_14.jpg | Patentes | 2 | 3 |
| people_01.jpg | Rostros | 16 | 17 |
| people_03.jpg | Rostros | 32 | 33 |
| people_04.jpg | Rostros | 21 | 22 |
| people_05.jpg | Rostros | 14 | 15 |
| people_06.jpg | Rostros | 16 | 18 |
| people_07.jpg | Rostros | 15 | 17 |
| people_08.jpg | Rostros | 15 | 16 |
| people_09.jpg | Rostros | 22 | 24 |
| people_09.jpg | Patentes | 0 | 1 |
| people_10.jpg | Rostros | 9 | 10 |

## Detecciones de más (posibles falsos positivos)

| Archivo | Tipo | Detectados | Etiquetados |
| --- | --- | --- | --- |
| street_cars_03.jpg | Rostros | 1 | 0 |
| street_cars_08.jpg | Patentes | 2 | 1 |
| street_cars_11.jpg | Rostros | 3 | 1 |
| street_cars_12.jpg | Rostros | 1 | 0 |
| street_cars_13.jpg | Patentes | 1 | 0 |
| street_cars_14.jpg | Rostros | 1 | 0 |
| people_02.jpg | Rostros | 5 | 2 |
| people_04.jpg | Patentes | 1 | 0 |
