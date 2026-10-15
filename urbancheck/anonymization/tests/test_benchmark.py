"""US-041 — el benchmark reproducible y la integridad de los modelos.

El comando se prueba con un set sintético armado en un temporal: lo que se
verifica es la forma del informe (tasa por tipo, falsos negativos con archivo y
tipo, tiempos), no la calidad del detector, que mide el set de referencia.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from django.core.management import CommandError
from django.core.management import call_command

from urbancheck.anonymization import detectors
from urbancheck.anonymization.detectors import MODEL_SHA256
from urbancheck.anonymization.detectors import ModelIntegrityError
from urbancheck.anonymization.detectors import verified_model_path
from urbancheck.anonymization.tests.images import synthetic_photo


@pytest.fixture
def synthetic_set(tmp_path) -> Path:
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "calle.jpg").write_bytes(synthetic_photo())
    (tmp_path / "images" / "esquina.jpg").write_bytes(synthetic_photo((800, 600)))
    manifest = [
        {"file": "calle.jpg", "faces": 0, "plates": 0},
        # Etiquetada con una patente que la imagen no tiene: tiene que figurar
        # como falso negativo, con su nombre y el tipo.
        {"file": "esquina.jpg", "faces": 0, "plates": 1},
    ]
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    return tmp_path


class TestBenchmarkCommand:
    def test_it_reports_rate_false_negatives_and_times(self, synthetic_set, tmp_path):
        """CP-041-09: informe con tasa por tipo, falsos negativos y tiempos."""
        report = tmp_path / "informe.md"
        out = io.StringIO()

        call_command(
            "benchmark_anonymization",
            str(synthetic_set),
            report=str(report),
            stdout=out,
        )

        text = report.read_text()
        assert text == out.getvalue()
        assert "| Patentes | 0 | 1 | 0.0% |" in text
        assert "| Rostros | 0 | 0 | sin etiquetas |" in text
        assert "| esquina.jpg | Patentes | 0 | 1 |" in text
        assert "Promedio" in text
        assert "p95" in text
        assert "2 imágenes" in text

    def test_it_reads_the_unversioned_folder_from_configuration(
        self,
        synthetic_set,
        settings,
    ):
        """CP-041-10: sin argumento, la carpeta sale de la configuración."""
        settings.ANONYMIZATION_REFERENCE_SET = str(synthetic_set)
        out = io.StringIO()

        call_command("benchmark_anonymization", stdout=out)

        assert "2 imágenes" in out.getvalue()

    def test_without_a_set_it_says_what_is_missing(self, tmp_path):
        """CP-041-11: sin set, un error claro y no un informe vacío."""
        with pytest.raises(CommandError, match=r"manifest\.json"):
            call_command("benchmark_anonymization", str(tmp_path / "vacia"))

    def test_the_reference_set_is_not_versioned(self):
        """CP-041-12: las fotos de referencia nunca entran al repositorio."""
        root = Path(__file__).resolve().parents[3]
        ignored = (root / ".gitignore").read_text()
        docker_ignored = (root / ".dockerignore").read_text()

        assert "benchmark_data/" in ignored.splitlines()
        assert "benchmark_data/" in docker_ignored.splitlines()
        assert not list((root / "urbancheck").rglob("*/benchmark/images/*"))


class TestModelIntegrity:
    def test_the_shipped_weights_match_their_published_checksums(self):
        """CP-041-13: los pesos versionados son los publicados."""
        for path in (detectors.FACE_MODEL_PATH, detectors.PLATE_MODEL_PATH):
            assert verified_model_path(path) == path
        assert set(MODEL_SHA256) == {
            detectors.FACE_MODEL_PATH.name,
            detectors.PLATE_MODEL_PATH.name,
        }

    def test_a_tampered_model_is_refused(self, tmp_path):
        """CP-041-14: un peso alterado no se carga."""
        fake = tmp_path / detectors.FACE_MODEL_PATH.name
        fake.write_bytes(b"no es el modelo")

        with pytest.raises(ModelIntegrityError):
            verified_model_path(fake)
