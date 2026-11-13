"""Municipalidad de respaldo para un reporte sin coordenadas (US-034).

``get_active_municipality`` es el camino que se toma cuando el reporte no tiene
punto contra el cual evaluar cobertura: el vecino escribió una dirección y la
geocodificación falló. Sin coordenadas no hay cercanía que calcular, así que se
usa la municipalidad configurada —o la única registrada, si hay una sola.

Los tres desenlaces son deliberadamente distintos: una municipalidad clara, un
error de configuración por ausencia y un error de configuración por ambigüedad.
Fallar ruidosamente es lo correcto acá: asignar el reporte a cualquiera lo
mandaría a un municipio que no le corresponde.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ImproperlyConfigured

from urbancheck.municipalities.models import Municipality
from urbancheck.municipalities.services import AMBIGUOUS_MESSAGE
from urbancheck.municipalities.services import MISSING_MESSAGE
from urbancheck.municipalities.services import get_active_municipality
from urbancheck.municipalities.tests.factories import MunicipalityFactory

pytestmark = pytest.mark.django_db


def test_it_returns_the_configured_municipality(settings):
    configured = MunicipalityFactory.create()
    MunicipalityFactory.create()
    settings.ACTIVE_MUNICIPALITY_ID = configured.pk

    assert get_active_municipality() == configured


def test_without_configuration_the_only_registered_one_is_used(settings):
    """El caso normal de una instalación de un solo municipio."""
    settings.ACTIVE_MUNICIPALITY_ID = None
    Municipality.objects.all().delete()
    only = MunicipalityFactory.create()

    assert get_active_municipality() == only


def test_a_deactivated_municipality_does_not_count_as_the_only_one(settings):
    settings.ACTIVE_MUNICIPALITY_ID = None
    Municipality.objects.all().delete()
    active = MunicipalityFactory.create()
    MunicipalityFactory.create(is_active=False)

    assert get_active_municipality() == active


def test_without_any_municipality_it_refuses_to_guess(settings):
    settings.ACTIVE_MUNICIPALITY_ID = None
    Municipality.objects.all().delete()

    with pytest.raises(ImproperlyConfigured, match=MISSING_MESSAGE):
        get_active_municipality()


def test_with_several_and_none_configured_it_refuses_to_guess(settings):
    """Elegir una al azar mandaría el reporte a un municipio ajeno."""
    settings.ACTIVE_MUNICIPALITY_ID = None
    Municipality.objects.all().delete()
    MunicipalityFactory.create()
    MunicipalityFactory.create()

    with pytest.raises(ImproperlyConfigured) as excinfo:
        get_active_municipality()

    assert AMBIGUOUS_MESSAGE in str(excinfo.value)


def test_a_configured_id_that_does_not_exist_fails_loudly(settings):
    """Un id mal escrito en el entorno no puede degradar en silencio."""
    settings.ACTIVE_MUNICIPALITY_ID = 999999

    with pytest.raises(Municipality.DoesNotExist):
        get_active_municipality()
