# Set de prueba de la anonimización (US-041, escenario 9)

Son 37 fotos urbanas de Wikimedia Commons, todas con licencia libre (CC0, CC BY
o CC BY-SA). Están reducidas a 1600 px de lado mayor y sin EXIF. En
`manifest.json` figuran, por imagen, la página de origen, la licencia y el
autor, que las licencias CC BY y CC BY-SA exigen citar.

| Grupo | Cantidad | Qué cubre |
|---|---|---|
| `people_*` | 12 | Peatonales con multitudes, gente detrás de un vidrio, una escena nocturna y el chofer de un taxi |
| `street_cars_*` | 14 | Autos, taxis y colectivos a distintas distancias, de día, de noche y con niebla |
| `plate_closeup_*` | 5 | Patentes argentinas de cerca: Mercosur, del formato anterior y de moto |
| `clean_*` | 6 | Baches y calles sin rostros ni patentes |

## Criterio de etiquetado

Los conteos de `faces` y `plates` se hicieron a mano, revisando cada foto con
las cajas dibujadas (`benchmark_anonymization --annotate DIR`):

- **Rostro**: una cara que permitiría reconocer a la persona. Cuenta de frente,
  de tres cuartos o de perfil. No cuentan las nucas, las siluetas a contraluz ni
  las caras de unos pocos píxeles al fondo. Sí cuentan las caras de carteles y
  tapas de revistas, porque también son caras de personas.
- **Patente**: una patente cuyos caracteres se pueden leer en la foto. Las que
  en la foto de Commons ya vienen tapadas cuentan igual: miden si el detector
  encuentra la chapa.

La tasa es por conteo: en cada imagen se acreditan como detectados hasta tantos
objetos como tiene etiquetados. Por eso una imagen con más detecciones que
etiquetas se lista como posible falso positivo, y con menos, como falso
negativo.
