"""Catálogo de provincias y localidades para el alta de municipalidades."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from urbancheck.municipalities.georef import list_localities
from urbancheck.municipalities.georef import list_provinces


class ProvinceListView(APIView):
    """Las 24 provincias argentinas."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"results": list_provinces()})


class LocalityListView(APIView):
    """Localidades de una provincia, con su centroide.

    Devuelve la provincia entera de una sola vez —ninguna pasa de unas pocas
    centenas— y el panel filtra mientras se escribe. Es lo que evita una request
    por tecla y hace que la lista responda al instante.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, province_id: str):
        return Response({"results": list_localities(province_id)})
