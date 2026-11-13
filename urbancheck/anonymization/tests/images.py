"""Imágenes para los tests de la anonimización y de los puntos de carga.

Hay dos clases de imagen y no se mezclan:

- **Sintéticas** (``synthetic_photo``): se arman acá, no muestran a nadie y
  traen metadatos conocidos —modelo del teléfono, fecha, GPS, XMP— para poder
  afirmar que no sobreviven. Alcanzan para todo lo que no depende de que el
  detector encuentre algo: formato, orientación, metadatos, almacenamiento,
  tiempos.
- **Del set de referencia** (``reference_image``): fotos reales con rostros y
  patentes, porque un modelo entrenado con fotos no detecta una cara dibujada.
  Viven en una carpeta **no versionada** (``ANONYMIZATION_REFERENCE_SET``) y el
  test que las pide se saltea si no está, con el motivo a la vista.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from django.conf import settings
from PIL import Image

#: Etiquetas EXIF que no pueden llegar a ningún archivo guardado.
GPS_INFO_TAG = 0x8825  # 34853
MODEL_TAG = 0x0110
DATETIME_TAG = 0x0132

#: Lo que se escribe en el GPS de las fotos sintéticas: Villa María.
KNOWN_GPS = {
    1: "S",
    2: (32.0, 24.0, 36.0),
    3: "W",
    4: (63.0, 14.0, 24.0),
}

XMP_PACKET = (
    b'<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>'
    b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
    b'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
    b'<rdf:Description xmlns:exif="http://ns.adobe.com/exif/1.0/" '
    b'exif:GPSLatitude="32,24.6S"/></rdf:RDF></x:xmpmeta>'
    b'<?xpacket end="w"?>'
)


def synthetic_photo(
    size: tuple[int, int] = (640, 480),
    *,
    fmt: str = "JPEG",
    orientation: int | None = None,
) -> bytes:
    """Una "foto" de calle sin nadie, con los metadatos de un celular.

    Degradé con ruido suave: tiene textura de foto para que el JPEG se comporte
    como con una real, y ninguna forma que un detector confunda con una cara o
    una patente.
    """
    width, height = size
    rng = np.random.default_rng(seed=width * height)
    gradient = np.linspace(60, 190, width, dtype=np.float32)[None, :, None]
    sky = np.linspace(0.8, 1.1, height, dtype=np.float32)[:, None, None]
    pixels = gradient * sky * np.array([1.0, 0.95, 0.85], dtype=np.float32)
    pixels = pixels + rng.normal(0, 4, (height, width, 3))
    image = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8), "RGB")

    exif = Image.Exif()
    exif[MODEL_TAG] = "Moto G (2026)"
    exif[DATETIME_TAG] = "2026:10:01 09:30:00"
    exif[GPS_INFO_TAG] = KNOWN_GPS
    if orientation is not None:
        exif[0x0112] = orientation

    buffer = io.BytesIO()
    options: dict = {"exif": exif}
    if fmt == "JPEG":
        options["xmp"] = XMP_PACKET
    image.save(buffer, format=fmt, **options)
    return buffer.getvalue()


def assert_no_metadata(data: bytes) -> None:
    """Ni EXIF (GPS incluido), ni XMP, ni IPTC en el archivo guardado.

    Se mira de dos formas: lo que Pillow entiende y los bytes crudos, por si un
    bloque quedara escrito en un segmento que Pillow no expone.
    """
    image = Image.open(io.BytesIO(data))
    exif = image.getexif()
    assert GPS_INFO_TAG not in exif
    assert len(exif) == 0
    assert not exif.get_ifd(GPS_INFO_TAG)
    for key in ("exif", "xmp", "XML:com.adobe.xmp", "photoshop", "iptc"):
        assert key not in image.info, key
    assert b"Exif\x00\x00" not in data
    assert b"http://ns.adobe.com/" not in data
    assert b"Photoshop 3.0" not in data


def reference_set_dir() -> Path:
    return Path(settings.ANONYMIZATION_REFERENCE_SET)


def reference_image(name: str) -> bytes:
    path = reference_set_dir() / "images" / name
    if not path.exists():
        pytest.skip(
            f"Falta el set de referencia no versionado de US-041 ({path}). "
            "Ver urbancheck/anonymization/benchmark/README.md.",
        )
    return path.read_bytes()
