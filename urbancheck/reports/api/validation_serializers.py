"""Serializers de la bandeja de validación (US-037)."""

from rest_framework import serializers

from urbancheck.reports.models import Report

from .serializers import AuthorSerializer


class PendingValidationSerializer(serializers.ModelSerializer):
    """Lo que la lista de pendientes necesita mostrar, y nada más.

    ``distance_meters`` viene de la anotación del queryset; viaja nulo cuando el
    validador no compartió su ubicación, que es un caso esperado.
    """

    author = AuthorSerializer(read_only=True)
    distance_meters = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = [
            "id",
            "photo",
            "category",
            "description",
            "address",
            "latitude",
            "longitude",
            "status",
            "created_at",
            "distance_meters",
            "author",
        ]
        read_only_fields = fields

    def get_distance_meters(self, obj) -> float | None:
        """Prefiere la anotación; si no está, no hay distancia que informar.

        Es un ``SerializerMethodField`` y no un campo declarativo a propósito:
        un ``read_only`` alimentado por una anotación ausente se omite en
        silencio del JSON, y el cliente no puede distinguir "sin ubicación" de
        "campo que no llegó".
        """
        distance = getattr(obj, "distance_meters", None)
        return round(distance, 1) if distance is not None else None
