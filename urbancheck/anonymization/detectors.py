"""Detectores preentrenados de rostros y patentes (US-041).

Los dos corren localmente sobre CPU con pesos versionados en ``weights/``: el
despliegue es on-premise y la anonimización es una obligación legal, así que no
puede depender de bajar un modelo de Internet en tiempo de ejecución.

Este módulo es interno del servicio. Nadie fuera de ``service.py`` debería
importarlo: la interfaz de la anonimización es ``anonymize``.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

WEIGHTS_DIR = Path(__file__).resolve().parent / "weights"
FACE_MODEL_PATH = WEIGHTS_DIR / "face_detection_yunet_2023mar.onnx"
PLATE_MODEL_PATH = WEIGHTS_DIR / "yolo-v9-s-608-license-plates-end2end.onnx"

#: SHA-256 publicados de cada modelo (ver ``weights/README.md``). Se verifican
#: al cargarlos y al construir la imagen de producción: un peso corrupto o
#: reemplazado haría que el detector no encuentre nada, y "nada" publicaría la
#: foto sin difuminar.
MODEL_SHA256 = {
    FACE_MODEL_PATH.name: (
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
    ),
    PLATE_MODEL_PATH.name: (
        "2b878b38d9aa07b6ddc3ea75c4ffcb39869bc5c218e0a14002f60ab2f7b0be9a"
    ),
}


class ModelIntegrityError(RuntimeError):
    """El archivo del modelo no es el publicado. Es un ``RuntimeError`` a
    propósito: el servicio lo trata como fallo del detector, que reintenta y,
    si persiste, deja la foto sin publicar."""


def verified_model_path(path: Path) -> Path:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != MODEL_SHA256[path.name]:
        msg = f"El modelo {path.name} no coincide con su checksum publicado."
        raise ModelIntegrityError(msg)
    return path


@dataclass(frozen=True)
class Box:
    """Caja alineada a los ejes, en píxeles de la imagen original."""

    x: int
    y: int
    w: int
    h: int
    kind: str

    def expanded(self, margin: float, width: int, height: int) -> Box:
        """La misma caja agrandada ``margin`` por lado y recortada a la imagen.

        Un recorte exacto a la detección suele dejar a la vista el borde de la
        cara o el primer carácter de la patente.
        """
        dx = round(self.w * margin)
        dy = round(self.h * margin)
        x1 = max(0, self.x - dx)
        y1 = max(0, self.y - dy)
        x2 = min(width, self.x + self.w + dx)
        y2 = min(height, self.y + self.h + dy)
        return Box(x1, y1, x2 - x1, y2 - y1, self.kind)


class FaceDetector:
    """YuNet (OpenCV Zoo, licencia MIT).

    Pesa ~230 KB y detecta desde caras de unos 10 px. El detector de OpenCV
    guarda el tamaño de entrada como estado, así que cada llamada va bajo lock.

    Las fotos de celular llegan a 12 MP o más; YuNet sobre la imagen entera
    tarda varios segundos. Se analiza una copia con el lado mayor en
    ``max_side`` y las cajas se reescalan: por debajo de ese tamaño una cara ya
    no es reconocible de todos modos.
    """

    def __init__(self, *, score_threshold: float = 0.6, max_side: int = 2048):
        self.score_threshold = score_threshold
        self.max_side = max_side
        self._detector = cv2.FaceDetectorYN.create(
            str(verified_model_path(FACE_MODEL_PATH)),
            "",
            (320, 320),
            score_threshold,
            0.3,
            5000,
        )
        self._lock = threading.Lock()

    def detect(self, bgr: np.ndarray) -> list[Box]:
        height, width = bgr.shape[:2]
        scale = min(1.0, self.max_side / max(height, width))
        scaled = bgr
        if scale < 1.0:
            size = (round(width * scale), round(height * scale))
            scaled = cv2.resize(bgr, size, interpolation=cv2.INTER_AREA)

        with self._lock:
            self._detector.setInputSize((scaled.shape[1], scaled.shape[0]))
            _, faces = self._detector.detect(scaled)

        if faces is None:
            return []
        boxes = []
        for face in faces:
            x, y, w, h = (float(v) / scale for v in face[:4])
            boxes.append(Box(round(x), round(y), round(w), round(h), "face"))
        return boxes


class PlateDetector:
    """YOLOv9-s 608 de open-image-models (licencia MIT), exportado *end2end*.

    El ONNX ya trae el NMS: la salida es una fila por detección con la forma
    ``[batch, x1, y1, x2, y2, clase, score]`` en coordenadas de la entrada
    letterboxeada. El pre y posprocesado se hace acá y no con el paquete
    ``open-image-models``, que ante un error de inferencia lo registra y
    devuelve «sin detecciones»: acá eso significaría publicar una patente sin
    difuminar. Un error del detector tiene que propagarse.
    """

    def __init__(self, *, score_threshold: float = 0.25):
        self.score_threshold = score_threshold
        options = ort.SessionOptions()
        options.log_severity_level = 3
        self._session = ort.InferenceSession(
            str(verified_model_path(PLATE_MODEL_PATH)),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        model_input = self._session.get_inputs()[0]
        self._input_name = model_input.name
        self._size = int(model_input.shape[2])

    def detect(self, bgr: np.ndarray) -> list[Box]:
        tensor, ratio, (pad_x, pad_y) = self._letterbox(bgr)
        predictions = self._session.run(None, {self._input_name: tensor})[0]
        height, width = bgr.shape[:2]

        boxes = []
        for row in np.asarray(predictions).reshape(-1, 7):
            if row[6] < self.score_threshold:
                continue
            x1 = max(0, round((row[1] - pad_x) / ratio))
            y1 = max(0, round((row[2] - pad_y) / ratio))
            x2 = min(width, round((row[3] - pad_x) / ratio))
            y2 = min(height, round((row[4] - pad_y) / ratio))
            if x2 > x1 and y2 > y1:
                boxes.append(Box(x1, y1, x2 - x1, y2 - y1, "plate"))
        return boxes

    def _letterbox(
        self,
        bgr: np.ndarray,
    ) -> tuple[np.ndarray, float, tuple[float, float]]:
        """Redimensiona conservando proporción y rellena hasta el cuadrado."""
        height, width = bgr.shape[:2]
        ratio = min(self._size / height, self._size / width)
        new_w, new_h = round(width * ratio), round(height * ratio)
        resized = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        pad_x = (self._size - new_w) / 2
        pad_y = (self._size - new_h) / 2
        top, left = round(pad_y - 0.1), round(pad_x - 0.1)
        bottom, right = self._size - new_h - top, self._size - new_w - left
        padded = cv2.copyMakeBorder(
            resized,
            top,
            bottom,
            left,
            right,
            cv2.BORDER_CONSTANT,
            value=(114, 114, 114),
        )
        # HWC BGR 0-255 -> NCHW RGB 0-1, como se entrenó el modelo.
        tensor = (
            padded[:, :, ::-1].transpose(2, 0, 1)[np.newaxis].astype(np.float32) / 255.0
        )
        return np.ascontiguousarray(tensor), ratio, (left, top)
