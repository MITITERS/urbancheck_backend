from django.apps import AppConfig


class AnonymizationConfig(AppConfig):
    """Difuminado de rostros y patentes (US-041).

    No tiene modelos: es una app solo para alojar el servicio, su comando de
    benchmark y sus tests.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "urbancheck.anonymization"
