# Set de referencia de la anonimización (US-041, escenario 9)

Las fotos del set **no se versionan**: son personas, patentes y la vía pública.
Viven en una carpeta aparte, por defecto `benchmark_data/anonymization/` en la
raíz del repo (ignorada por git y por Docker), o donde diga
`DJANGO_ANONYMIZATION_REFERENCE_SET`. La leen dos cosas:

- `python manage.py benchmark_anonymization [CARPETA] [--report informe.md]`,
  que mide la tasa de detección, lista los falsos negativos y toma tiempos;
- los tests de detección de `anonymization/tests/test_service.py`, que se
  saltean (con el motivo a la vista) si la carpeta no está.

## Forma de la carpeta

```text
benchmark_data/anonymization/
  manifest.json
  images/
    people_01.jpg
    ...
```

`manifest.json` es una lista con una entrada por imagen:

```json
[
  {"file": "people_01.jpg", "faces": 3, "plates": 0, "source": "...", "license": "...", "notes": "..."}
]
```

Solo `file`, `faces` y `plates` son obligatorios.

Los tests de detección esperan encontrar, como mínimo, estos archivos con lo que
dice al lado; si el set cambia, hay que ajustar las constantes de
`test_service.py`: `people_12.jpg` (un rostro), `people_10.jpg` (ocho rostros o
más), `plate_closeup_02.jpg` (una patente), `street_cars_05.jpg` (cuatro
patentes o más) y `street_cars_10.jpg` (dos rostros y dos patentes o más).

## Set provisorio

Hasta que el equipo cargue fotos propias de Villa María, el set es el que se
armó en el Sprint 5 con 37 fotos de Wikimedia Commons con licencia libre (CC0,
CC BY o CC BY-SA), reducidas a 1600 px de lado mayor y sin EXIF. El manifiesto
guarda la página de origen, la licencia y el autor de cada una, que las
licencias CC BY y CC BY-SA exigen citar.

| Grupo | Cantidad | Qué cubre |
|---|---|---|
| `people_*` | 12 | Peatonales con multitudes, gente detrás de un vidrio, una escena nocturna y el chofer de un taxi |
| `street_cars_*` | 14 | Autos, taxis y colectivos a distintas distancias, de día, de noche y con niebla |
| `plate_closeup_*` | 5 | Patentes argentinas de cerca: Mercosur, del formato anterior y de moto |
| `clean_*` | 6 | Baches y calles sin rostros ni patentes |

Hasta el 15/10/2026 este set estuvo versionado en
`urbancheck/anonymization/benchmark/images/`. Se sacó del árbol; **sigue en el
historial de git** (commit `068c0c5`) mientras el equipo no decida reescribirlo.

## Criterio de etiquetado

Los conteos de `faces` y `plates` se hacen a mano, revisando cada foto con las
cajas dibujadas (`benchmark_anonymization --annotate DIR`):

- **Rostro**: una cara que permitiría reconocer a la persona. Cuenta de frente,
  de tres cuartos o de perfil. No cuentan las nucas, las siluetas a contraluz ni
  las caras de unos pocos píxeles al fondo. Sí cuentan las caras de carteles y
  tapas de revistas, porque también son caras de personas.
- **Patente**: una patente cuyos caracteres se pueden leer en la foto. Las que
  ya vienen tapadas en la foto original cuentan igual: miden si el detector
  encuentra la chapa.

La tasa es por conteo: en cada imagen se acreditan como detectados hasta tantos
objetos como tiene etiquetados. Por eso una imagen con más detecciones que
etiquetas se lista como posible falso positivo, y con menos, como falso
negativo.
