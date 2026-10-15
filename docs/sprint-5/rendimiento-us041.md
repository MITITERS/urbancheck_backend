# Rendimiento del difuminado (US-041, escenario 8)

Medido el 15/10/2026 en el entorno Docker de desarrollo, sin otra carga en la
máquina. Es el criterio por defecto del punto 4 de las instrucciones: **el
equipo decide si este entorno es representativo del servidor de producción**.

## Máquina

- Mac con Apple Silicon (aarch64), Docker Desktop 28.4.0.
- Contenedor `django` del compose local: 10 CPU y 7,7 GB de RAM asignados.
- Python 3.14.2, onnxruntime sobre CPU (sin GPU), OpenCV, Pillow 12.3.0.
- Script: `python measure_us041.py` (en `docs/sprint-5/measure_us041.py`), que llama a
  `anonymization.service.process`, igual que la tarea de Celery.

## Tiempos por imagen

| Imagen | Cantidad | Promedio | p95 | CPU por imagen |
| --- | --- | --- | --- | --- |
| Foto de celular de 12 MP (4000 × 3000, sintética) | 10 | 1085 ms | 1305 ms | 9,8 s |
| Set de referencia (1600 px de lado mayor, con rostros y patentes) | 37 | 962 ms | 1240 ms | 9,0 s |

El tiempo de CPU es mayor que el de reloj porque onnxruntime reparte la
inferencia entre los 10 núcleos. En un servidor con menos núcleos el tiempo de
reloj crece en proporción: con 2 núcleos, del orden de 5 s por foto de 12 MP,
todavía por debajo del límite de 10 s del escenario 8. **Ese valor es una
estimación, no una medición.**

El benchmark del escenario 9 (`benchmark-us041.md`, misma máquina) dio 786 ms de
promedio y 961 ms de p95 sobre el set de referencia; la diferencia con la tabla
de arriba es la carga del sistema en cada corrida.

## Memoria

| Momento | RSS del proceso |
| --- | --- |
| Al arrancar Django | 141 MB |
| Con los dos modelos cargados | 264 MB |
| Pico, procesando una foto de 12 MP | 847 MB |

El pico es de una foto a la vez, que es como trabaja el worker de Celery con
concurrencia 1. Con concurrencia N, el pico se multiplica por N.

## Tamaño de las imágenes de Docker

| Imagen | Tamaño |
| --- | --- |
| Producción (`compose/production/django/Dockerfile`) | 1,15 GB |
| Desarrollo (`compose/local/django/Dockerfile`) | 2,48 GB |

Los modelos ocupan 27,5 MB del total (YuNet 227 KiB y YOLOv9-s 27,3 MiB).
