"""Servicio de anonimización de imágenes (US-041, RN-11, Ley 25.326).

``anonymize`` es la **única** puerta de entrada: recibe la foto tal como la
subió el usuario y devuelve otra, con los rostros y las patentes detectados
cubiertos por un desenfoque gaussiano. El servicio en sí trabaja todo en
memoria y no escribe nada.

El desenfoque es irreversible y destructivo por decisión de producto. No es
pixelado: el pixelado de bloque se revierte en parte con superresolución.

**Cambio de US-042**: hasta US-041 la original no tocaba el disco en ningún
momento, porque el difuminado corría dentro del request. Con la publicación
diferida la original se escribe en un storage privado —fuera de ``MEDIA_ROOT``,
sin URL, borrada apenas termina el procesamiento— hasta que la tarea la toma.
Esa garantía se movió: ya no la da el servicio, la da ``anonymization.storage``.

Un fallo se propaga como ``AnonymizationError``, y la distinción importa para
los reintentos de US-042: ``TransientAnonymizationError`` vale la pena
reintentarla, ``PermanentAnonymizationError`` no. Ante la duda, la foto no se
publica.
"""

from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass
from dataclasses import field
from functools import cache
from pathlib import PurePath
from typing import IO

import cv2
import numpy as np
from django.core.files.base import ContentFile
from PIL import Image
from PIL import ImageOps
from PIL import UnidentifiedImageError

from .detectors import Box
from .detectors import FaceDetector
from .detectors import PlateDetector

logger = logging.getLogger(__name__)

#: Cuánto se agranda cada caja por lado antes de difuminar. La caja de YuNet va
#: de cejas a mentón y deja afuera frente, orejas y pelo.
FACE_MARGIN = 0.25
PLATE_MARGIN = 0.15

#: Hasta qué sigma el gaussiano se aplica directo sobre la región (ver ``_gaussian``).
_MAX_DIRECT_SIGMA = 12.0

#: Desde qué lado mayor se buscan patentes también por cuadrantes. El detector
#: trabaja a 608 px: en una foto de calle grande una patente lejana queda de
#: pocos píxeles al reducirla, y en un cuadrante recupera el tamaño.
PLATE_TILING_MIN_SIDE = 1200
PLATE_TILE_FRACTION = 0.6

#: Formato de entrada -> formato de salida. MPO es como Pillow abre las JPEG de
#: iPhone. Cualquier otro formato que Pillow acepte sale como JPEG.
OUTPUT_FORMATS = {"JPEG": "JPEG", "MPO": "JPEG", "PNG": "PNG", "WEBP": "WEBP"}
EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
JPEG_QUALITY = 90


class AnonymizationError(Exception):
    """La imagen no se pudo anonimizar y por lo tanto no se puede publicar.

    Es la base de la jerarquía y sigue sirviendo para atrapar cualquier fallo
    sin distinguir el motivo. ``code`` es lo que queda registrado para
    diagnóstico (US-042): nunca el mensaje original del detector, que puede
    traer datos de la imagen.
    """

    code = "anonymization_failed"


class TransientAnonymizationError(AnonymizationError):
    """Falló el detector, no la imagen: el mismo archivo puede salir bien.

    Un modelo ONNX que no carga, memoria que no alcanzó, un worker que se quedó
    sin recursos. Es lo único que US-042 reintenta.
    """

    code = "detector_unavailable"


class PermanentAnonymizationError(AnonymizationError):
    """El archivo no se puede procesar, y reintentarlo da siempre lo mismo.

    Reintentar acá es gastar cola para llegar al mismo resultado: se falla de
    una y el ciudadano recibe el aviso enseguida en lugar de esperar los
    reintentos completos.
    """

    code = "undecodable_image"


@dataclass
class Detections:
    faces: list[Box] = field(default_factory=list)
    plates: list[Box] = field(default_factory=list)

    @property
    def boxes(self) -> list[Box]:
        return self.faces + self.plates


@dataclass
class AnonymizationResult:
    content: ContentFile
    detections: Detections
    elapsed_ms: float


def anonymize(file: IO[bytes]) -> ContentFile:
    """Devuelve la versión anonimizada de ``file``, lista para guardar.

    Conserva formato, resolución y orientación; descarta el EXIF, que además
    puede traer la ubicación GPS y el modelo del teléfono. El nombre se
    mantiene salvo la extensión, si el formato cambió.
    """
    return process(file).content


def process(file: IO[bytes]) -> AnonymizationResult:
    """``anonymize`` más lo que encontró y cuánto tardó, para el benchmark."""
    started = time.perf_counter()
    image, output_format = _open(file)
    pixels = np.asarray(image)
    detections = detect(pixels)
    if detections.boxes:
        pixels = blur_regions(pixels, detections.boxes)

    content = _encode(Image.fromarray(pixels), image.info, output_format)
    elapsed_ms = (time.perf_counter() - started) * 1000
    # Sin nombre ni ruta del archivo: el log no puede señalar la original.
    logger.info(
        "Imagen anonimizada: %d rostros, %d patentes, %.0f ms",
        len(detections.faces),
        len(detections.plates),
        elapsed_ms,
    )
    name = _output_name(getattr(file, "name", None), output_format)
    return AnonymizationResult(ContentFile(content, name=name), detections, elapsed_ms)


def strip_metadata(file: IO[bytes]) -> ContentFile:
    """La misma imagen sin EXIF, XMP ni IPTC, y con la orientación aplicada.

    Es el tratamiento de las fotos que no pasan por el difuminado —la de
    perfil— (Sprint 5, punto 5.2): no se buscan rostros, pero el GPS, el modelo
    del teléfono y la fecha se descartan igual. Mismas reglas de formato que
    ``anonymize``.
    """
    image, output_format = _open(file)
    content = _encode(image, image.info, output_format)
    name = _output_name(getattr(file, "name", None), output_format)
    return ContentFile(content, name=name)


def detect(pixels: np.ndarray) -> Detections:
    """Rostros y patentes de una imagen RGB o RGBA, sin tocarla."""
    bgr = cv2.cvtColor(np.ascontiguousarray(pixels[:, :, :3]), cv2.COLOR_RGB2BGR)
    try:
        faces = _face_detector().detect(bgr)
        plates = _detect_plates(bgr)
    except (cv2.error, RuntimeError) as error:
        # onnxruntime levanta subclases de RuntimeError. Sin el mensaje: puede
        # incluir datos de la imagen y el log no tiene por qué verlos.
        msg = "El detector falló al analizar la imagen."
        raise TransientAnonymizationError(msg) from error
    return Detections(faces=_dedupe(faces), plates=_dedupe(plates))


def blur_regions(pixels: np.ndarray, boxes: list[Box]) -> np.ndarray:
    """Desenfoque gaussiano sobre la unión de ``boxes``, en una sola pasada.

    El sigma es un cuarto del lado mayor de la caja: a esa escala desaparece
    todo detalle del tamaño de un ojo o un carácter, y lo que queda es una
    mancha de color. Cada región se difumina sobre la imagen *original*, así
    dos cajas superpuestas no se componen entre sí.
    """
    height, width = pixels.shape[:2]
    result = pixels.copy()
    for box in boxes:
        margin = FACE_MARGIN if box.kind == "face" else PLATE_MARGIN
        region = box.expanded(margin, width, height)
        if region.w <= 0 or region.h <= 0:
            continue
        sigma = max(8.0, max(region.w, region.h) / 4)
        pad = int(sigma * 3)
        x1, y1 = max(0, region.x - pad), max(0, region.y - pad)
        x2 = min(width, region.x + region.w + pad)
        y2 = min(height, region.y + region.h + pad)
        blurred = _gaussian(pixels[y1:y2, x1:x2], sigma)
        inner_y, inner_x = region.y - y1, region.x - x1
        result[region.y : region.y + region.h, region.x : region.x + region.w] = (
            blurred[
                inner_y : inner_y + region.h,
                inner_x : inner_x + region.w,
            ]
        )
    return result


def _gaussian(crop: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussiano de ``sigma`` sobre ``crop``, en tiempo acotado.

    El costo del gaussiano crece con el kernel, y el kernel con la caja: una
    patente fotografiada de cerca ocupa la imagen entera y pide un sigma de
    cientos de píxeles, que tarda decenas de segundos. Por encima de
    ``_MAX_DIRECT_SIGMA`` se difumina una versión reducida con el sigma
    equivalente y se vuelve al tamaño original con interpolación bilineal: el
    resultado es igual de suave —no hay bloques— y cuesta lo mismo que una caja
    chica.
    """
    if sigma <= _MAX_DIRECT_SIGMA:
        return cv2.GaussianBlur(
            crop,
            (0, 0),
            sigmaX=sigma,
            borderType=cv2.BORDER_REPLICATE,
        )

    height, width = crop.shape[:2]
    scale = _MAX_DIRECT_SIGMA / sigma
    small = cv2.resize(
        crop,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    small = cv2.GaussianBlur(
        small,
        (0, 0),
        sigmaX=_MAX_DIRECT_SIGMA,
        borderType=cv2.BORDER_REPLICATE,
    )
    return cv2.resize(small, (width, height), interpolation=cv2.INTER_LINEAR)


@cache
def _face_detector() -> FaceDetector:
    return FaceDetector()


@cache
def _plate_detector() -> PlateDetector:
    return PlateDetector()


def _detect_plates(bgr: np.ndarray) -> list[Box]:
    detector = _plate_detector()
    plates = detector.detect(bgr)
    height, width = bgr.shape[:2]
    if max(height, width) < PLATE_TILING_MIN_SIDE:
        return plates

    tile_h = int(height * PLATE_TILE_FRACTION)
    tile_w = int(width * PLATE_TILE_FRACTION)
    for top in (0, height - tile_h):
        for left in (0, width - tile_w):
            tile = bgr[top : top + tile_h, left : left + tile_w]
            plates.extend(
                Box(box.x + left, box.y + top, box.w, box.h, box.kind)
                for box in detector.detect(tile)
            )
    return plates


def _dedupe(boxes: list[Box], overlap: float = 0.5) -> list[Box]:
    """Une detecciones repetidas (la misma patente vista entera y por cuadrante).

    Dos cajas son la misma si la intersección cubre la mitad de la más chica;
    se queda la más grande, que es la que más tapa.
    """
    kept: list[Box] = []
    for box in sorted(boxes, key=lambda b: b.w * b.h, reverse=True):
        if not any(overlap_ratio(box, other) >= overlap for other in kept):
            kept.append(box)
    return kept


def overlap_ratio(a: Box, b: Box) -> float:
    ix = max(0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))
    iy = max(0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))
    smaller = min(a.w * a.h, b.w * b.h)
    return (ix * iy) / smaller if smaller else 0.0


def _open(file: IO[bytes]) -> tuple[Image.Image, str]:
    if hasattr(file, "seek"):
        file.seek(0)
    try:
        with Image.open(file) as source:
            source_format = source.format or ""
            image = ImageOps.exif_transpose(source)
            mode = (
                "RGBA"
                if "A" in image.getbands() or "transparency" in image.info
                else "RGB"
            )
            converted = image.convert(mode)
            converted.info = {
                k: v for k, v in source.info.items() if k == "icc_profile"
            }
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
    ) as error:
        msg = "El archivo no es una imagen que se pueda procesar."
        raise PermanentAnonymizationError(msg) from error

    output_format = OUTPUT_FORMATS.get(source_format, "JPEG")
    if output_format == "JPEG" and converted.mode == "RGBA":
        converted = converted.convert("RGB")
    return converted, output_format


def _encode(image: Image.Image, info: dict, output_format: str) -> bytes:
    """Reencodea sin EXIF. Solo se conserva el perfil de color."""
    options: dict = {}
    if info.get("icc_profile"):
        options["icc_profile"] = info["icc_profile"]
    if output_format in {"JPEG", "WEBP"}:
        options["quality"] = JPEG_QUALITY
    buffer = io.BytesIO()
    try:
        image.save(buffer, format=output_format, **options)
    except (OSError, ValueError) as error:
        # Reencodear lo que ya se abrió casi nunca falla, pero si falla es por
        # el contenido y no por el detector: reintentarlo da siempre lo mismo.
        msg = "La imagen no se pudo reencodear."
        raise PermanentAnonymizationError(msg) from error
    return buffer.getvalue()


def _output_name(name: str | None, output_format: str) -> str:
    path = PurePath(PurePath(name).name if name else "photo")
    extension = EXTENSIONS[output_format]
    if path.suffix.lower() in {".jpg", ".jpeg"} and extension == ".jpg":
        return path.name
    return str(path.with_suffix(extension))
