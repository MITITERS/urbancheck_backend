# Pesos de los detectores (US-041)

Van versionados en el repositorio y en la imagen de Docker: el servicio no baja
nada de Internet en tiempo de ejecución.

| Archivo | Origen | Licencia | SHA-256 |
|---|---|---|---|
| `face_detection_yunet_2023mar.onnx` | [OpenCV Zoo — YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) | MIT | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` |
| `yolo-v9-s-608-license-plates-end2end.onnx` | [open-image-models](https://github.com/ankandrew/open-image-models/releases/tag/assets) | MIT | `2b878b38d9aa07b6ddc3ea75c4ffcb39869bc5c218e0a14002f60ab2f7b0be9a` |

Los checksums se verifican en tres lugares: al cargar cada modelo
(`detectors.MODEL_SHA256`; si no coincide, el detector falla y la foto no se
publica), al construir la imagen de producción (`sha256sum -c` en
`compose/production/django/Dockerfile`) y en un test
(`test_benchmark.py::TestModelIntegrity`). Para verificar a mano:
`shasum -a 256 *.onnx`.

| Modelo | Versión | Tamaño |
|---|---|---|
| YuNet | `2023mar` (OpenCV Zoo) | 227 KiB (232.589 bytes) |
| YOLOv9-s 608, patentes, end-to-end | release `assets` de open-image-models | 27,3 MiB (28.612.350 bytes) |

Se eligió el YOLOv9-s 608 y no el `t-640` ni el `t-384`, más livianos, porque
en las fotos de prueba detectó patentes que los otros dos perdían (una de moto
y otra cortada por el borde). Aun así, el tiempo queda muy por debajo del límite
de 10 s.
