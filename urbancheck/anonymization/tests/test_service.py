"""US-041 — servicio de anonimización: escenarios 1 a 5, 8 y 10.

Las imágenes salen del set de benchmark (fotos reales de Wikimedia Commons):
un rostro o una patente dibujados a mano no los detecta un modelo entrenado
con fotos, y un test contra eso no probaría nada.
"""

from __future__ import annotations

import io
import logging

import cv2
import numpy as np
import pytest
from PIL import Image

from urbancheck.anonymization import service
from urbancheck.anonymization.detectors import Box
from urbancheck.anonymization.management.commands.benchmark_anonymization import (
    BENCHMARK_DIR,
)
from urbancheck.anonymization.service import AnonymizationError
from urbancheck.anonymization.service import anonymize
from urbancheck.anonymization.service import blur_regions
from urbancheck.anonymization.service import detect
from urbancheck.anonymization.service import process

MAX_SECONDS = 10

# Cuánta textura puede conservar una región difuminada respecto de la original,
# medida como varianza del laplaciano. Un rostro o una patente legibles tienen
# bordes; lo que queda después del gaussiano es una mancha.
MAX_TEXTURE_RATIO = 0.2

# Error medio por píxel (0-255) que deja solo la recompresión JPEG.
JPEG_TOLERANCE = 2

# Dos cajas se consideran la misma detección desde esta superposición.
SAME_BOX = 0.5

# Lo que el detector encuentra, como mínimo, en cada foto del set.
FACES_AT_THE_SHOP_WINDOW = 8  # people_10
PLATES_ON_THE_AVENUE = 4  # street_cars_05: dos colectivos y dos autos
FACES_IN_MIXED = 2  # street_cars_10
PLATES_IN_MIXED = 2

OPAQUE = 255

# Salto máximo entre dos píxeles vecinos de una región difuminada.
MAX_SMOOTH_STEP = 3


def benchmark_image(name: str) -> bytes:
    return (BENCHMARK_DIR / "images" / name).read_bytes()


def named(data: bytes, name: str = "foto.jpg") -> io.BytesIO:
    file = io.BytesIO(data)
    file.name = name
    return file


def decode(content) -> Image.Image:
    content.seek(0)
    return Image.open(io.BytesIO(content.read()))


def texture(pixels: np.ndarray, box: Box) -> float:
    region = pixels[box.y : box.y + box.h, box.x : box.x + box.w]
    gray = cv2.cvtColor(np.ascontiguousarray(region), cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


@pytest.fixture(scope="module")
def processed():
    """Cada imagen se procesa una sola vez para todo el módulo."""
    cache: dict[str, tuple[np.ndarray, service.AnonymizationResult, np.ndarray]] = {}

    def get(name: str):
        if name not in cache:
            data = benchmark_image(name)
            result = process(named(data, name))
            before = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
            after = np.asarray(decode(result.content).convert("RGB"))
            cache[name] = (before, result, after)
        return cache[name]

    return get


def largest_step(region: np.ndarray) -> int:
    values = region.astype(int)
    return int(
        max(
            np.abs(np.diff(values, axis=0)).max(),
            np.abs(np.diff(values, axis=1)).max(),
        ),
    )


def pixelate(region: np.ndarray, block: int) -> np.ndarray:
    height, width, channels = region.shape
    blocks = region.reshape(height // block, block, width // block, block, channels)
    means = blocks.mean(axis=(1, 3)).astype(np.uint8)
    return means.repeat(block, axis=0).repeat(block, axis=1)


def assert_all_blurred(before: np.ndarray, after: np.ndarray, boxes: list[Box]) -> None:
    assert boxes
    for box in boxes:
        original = texture(before, box)
        if original < 1:
            # Una región ya lisa (una patente que en la foto de Commons vino
            # tapada) no tiene textura que perder.
            continue
        assert texture(after, box) < original * MAX_TEXTURE_RATIO, box


class TestFaces:
    def test_a_single_face_is_blurred(self, processed):
        """Escenario 1."""
        before, result, after = processed("people_12.jpg")

        assert len(result.detections.faces) == 1
        assert_all_blurred(before, after, result.detections.faces)

    def test_the_blurred_face_is_no_longer_a_face(self, processed):
        """Lo que queda en la caja no lo reconoce ni el mismo detector."""
        _, result, after = processed("people_10.jpg")

        remaining = detect(after).faces
        for face in result.detections.faces:
            assert not any(
                service.overlap_ratio(face, other) > SAME_BOX for other in remaining
            )

    def test_every_face_is_blurred_not_only_the_largest(self, processed):
        """Escenario 3: una multitud frente a una vidriera."""
        before, result, after = processed("people_10.jpg")

        assert len(result.detections.faces) >= FACES_AT_THE_SHOP_WINDOW
        assert_all_blurred(before, after, result.detections.faces)


class TestPlates:
    def test_a_single_plate_is_blurred(self, processed):
        """Escenario 2: patente Mercosur de cerca."""
        before, result, after = processed("plate_closeup_02.jpg")

        assert len(result.detections.plates) == 1
        assert_all_blurred(before, after, result.detections.plates)

    def test_every_plate_is_blurred(self, processed):
        """Escenario 3: dos colectivos y dos autos a distintas distancias."""
        before, result, after = processed("street_cars_05.jpg")

        assert len(result.detections.plates) >= PLATES_ON_THE_AVENUE
        assert_all_blurred(before, after, result.detections.plates)


class TestMixedAndClean:
    def test_faces_and_plates_in_the_same_image(self, processed):
        """Escenario 3: los dos detectores sobre la misma imagen, una sola pasada."""
        before, result, after = processed("street_cars_10.jpg")

        assert len(result.detections.faces) >= FACES_IN_MIXED
        assert len(result.detections.plates) >= PLATES_IN_MIXED
        assert_all_blurred(before, after, result.detections.boxes)

    def test_the_rest_of_the_image_is_left_alone(self, processed):
        """Escenario 1: fuera de las cajas, la imagen es la misma."""
        before, result, after = processed("street_cars_10.jpg")

        mask = np.ones(before.shape[:2], dtype=bool)
        for box in result.detections.boxes:
            margin = service.FACE_MARGIN if box.kind == "face" else service.PLATE_MARGIN
            region = box.expanded(margin, before.shape[1], before.shape[0])
            # Holgura por el bloque de 8 px de la recompresión JPEG.
            mask[
                max(0, region.y - 8) : region.y + region.h + 8,
                max(0, region.x - 8) : region.x + region.w + 8,
            ] = False
        difference = np.abs(before.astype(int) - after.astype(int))[mask]
        assert difference.mean() < JPEG_TOLERANCE

    def test_a_clean_image_comes_back_unaltered(self, processed):
        """Escenario 4: un bache sin nadie alrededor."""
        before, result, after = processed("clean_03.jpg")

        assert result.detections.boxes == []
        assert after.shape == before.shape
        # Solo la recompresión JPEG.
        assert np.abs(before.astype(int) - after.astype(int)).mean() < JPEG_TOLERANCE


class TestIrreversibleBlur:
    """Escenario 5: desenfoque gaussiano, nunca pixelado de bloque."""

    @pytest.fixture
    def noise(self):
        rng = np.random.default_rng(41)
        return rng.integers(0, 256, size=(200, 300, 3), dtype=np.uint8)

    def test_the_region_loses_all_detail(self, noise):
        box = Box(100, 60, 60, 60, "face")

        result = blur_regions(noise, [box])

        assert texture(result, box) < texture(noise, box) * 0.01

    def test_it_is_not_block_pixelation(self, noise):
        """El pixelado deja bloques con saltos bruscos entre uno y otro; el
        gaussiano, una variación continua sin bordes."""
        box = Box(100, 60, 60, 60, "face")

        blurred = blur_regions(noise, [box])[60:120, 100:160]
        pixelated = pixelate(noise[60:120, 100:160], block=10)

        assert largest_step(blurred) <= MAX_SMOOTH_STEP
        # Control: la métrica sí distingue un pixelado.
        assert largest_step(pixelated) > MAX_SMOOTH_STEP

    def test_the_box_is_expanded_with_a_safety_margin(self, noise):
        """Un recorte exacto deja a la vista el borde de la cara."""
        box = Box(100, 60, 60, 60, "face")
        margin = int(60 * service.FACE_MARGIN)

        result = blur_regions(noise, [box])

        ring = Box(100 - margin, 60 - margin, margin, 60 + 2 * margin, "face")
        assert not np.array_equal(
            result[ring.y : ring.y + ring.h, ring.x : ring.x + ring.w],
            noise[ring.y : ring.y + ring.h, ring.x : ring.x + ring.w],
        )

    def test_nothing_outside_the_expanded_box_changes(self, noise):
        box = Box(100, 60, 60, 60, "face")
        region = box.expanded(service.FACE_MARGIN, 300, 200)

        result = blur_regions(noise, [box])

        outside = np.ones(noise.shape[:2], dtype=bool)
        outside[region.y : region.y + region.h, region.x : region.x + region.w] = False
        assert np.array_equal(result[outside], noise[outside])


class TestFormat:
    """Escenario 10: formato, orientación y resolución se conservan."""

    @staticmethod
    def encode(image: Image.Image, fmt: str, **options) -> bytes:
        buffer = io.BytesIO()
        image.save(buffer, format=fmt, **options)
        return buffer.getvalue()

    def test_jpeg_keeps_format_resolution_and_name(self):
        data = benchmark_image("clean_03.jpg")
        original = Image.open(io.BytesIO(data))

        content = anonymize(named(data, "bache.jpg"))

        output = decode(content)
        assert content.name == "bache.jpg"
        assert output.format == "JPEG"
        assert output.size == original.size

    @pytest.mark.parametrize(
        ("fmt", "name"),
        [("PNG", "foto.png"), ("WEBP", "foto.webp")],
    )
    def test_png_and_webp_keep_their_format(self, fmt, name):
        data = self.encode(Image.new("RGB", (120, 80), (30, 90, 150)), fmt)

        content = anonymize(named(data, name))

        assert decode(content).format == fmt
        assert content.name == name

    def test_transparency_survives(self):
        image = Image.new("RGBA", (40, 40), (200, 0, 0, 0))
        image.paste((0, 0, 200, 255), (10, 10, 30, 30))

        content = anonymize(named(self.encode(image, "PNG"), "logo.png"))

        output = decode(content)
        assert output.mode == "RGBA"
        alpha = np.asarray(output)[:, :, 3]
        assert alpha[0, 0] == 0
        assert alpha[20, 20] == OPAQUE

    def test_an_unusual_format_comes_out_as_jpeg(self):
        data = self.encode(Image.new("RGB", (40, 40), (10, 10, 10)), "BMP")

        content = anonymize(named(data, "scan.bmp"))

        assert decode(content).format == "JPEG"
        assert content.name == "scan.jpg"

    def test_the_exif_orientation_is_applied(self):
        """Un celular guarda la foto acostada y la marca como rotada en el EXIF.
        Como el EXIF se descarta, la rotación tiene que quedar en los píxeles."""
        exif = Image.Exif()
        exif[0x0112] = 6  # Rotar 90° en sentido horario al mostrar.
        data = self.encode(Image.new("RGB", (60, 20), (80, 80, 80)), "JPEG", exif=exif)

        output = decode(anonymize(named(data)))

        assert output.size == (20, 60)

    def test_exif_metadata_is_dropped(self):
        """El EXIF de un celular trae la ubicación GPS y el modelo del equipo."""
        exif = Image.Exif()
        exif[0x0110] = "Moto G"  # Modelo.
        exif[0x8825] = {1: "S", 2: (32.0, 24.0, 36.0)}  # GPSInfo.
        data = self.encode(Image.new("RGB", (40, 40), (80, 80, 80)), "JPEG", exif=exif)

        output = decode(anonymize(named(data)))

        assert len(output.getexif()) == 0


class TestFailures:
    def test_a_file_that_is_not_an_image_is_rejected(self):
        with pytest.raises(AnonymizationError):
            anonymize(named(b"esto no es una imagen"))

    def test_a_detector_failure_is_not_published_silently(self, monkeypatch):
        """Ante un error del detector no se devuelve la foto sin difuminar."""

        class BrokenDetector:
            def detect(self, bgr):
                msg = "onnxruntime error"
                raise RuntimeError(msg)

        monkeypatch.setattr(service, "_plate_detector", BrokenDetector)

        with pytest.raises(AnonymizationError):
            anonymize(named(benchmark_image("clean_03.jpg")))


class TestPerformance:
    def test_a_twelve_megapixel_photo_takes_less_than_ten_seconds(self):
        """Escenario 8: el tamaño de una foto de celular actual."""
        source = Image.open(io.BytesIO(benchmark_image("people_09.jpg"))).convert("RGB")
        buffer = io.BytesIO()
        source.resize((4000, 3000)).save(buffer, format="JPEG", quality=92)

        result = process(named(buffer.getvalue()))

        assert result.elapsed_ms < MAX_SECONDS * 1000


class TestLogging:
    def test_the_log_never_names_the_file(self, caplog):
        """Ni el nombre ni la ruta del original en logs o trazas."""
        caplog.set_level(logging.INFO, logger="urbancheck.anonymization")

        anonymize(named(benchmark_image("clean_03.jpg"), "vecino-dni-30111222.jpg"))

        assert caplog.records
        assert all("vecino-dni" not in record.getMessage() for record in caplog.records)
