"""Provincias y localidades argentinas, vía el servicio Georef del Estado.

`apis.datos.gob.ar/georef` es la fuente autoritativa de la división política
argentina: devuelve el listado oficial de provincias y de localidades con su
centroide. Se usa para que el alta de una municipalidad sea elegir de una lista
en vez de escribir un nombre a mano y buscar el punto en el mapa.

Mismo criterio que el proxy de Nominatim: este módulo es el **único** punto de
salida hacia el servicio, cachea todo y nunca propaga un error de red. Si Georef
no responde, el panel cae a cargar el centro haciendo clic en el mapa.
"""

import logging

import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)

GEOREF_URL = "https://apis.datos.gob.ar/georef/api"
_TIMEOUT = 8  # segundos

# La división política no cambia: vale la pena cachearla largo.
_PROVINCES_TTL = 60 * 60 * 24 * 30
_LOCALITIES_TTL = 60 * 60 * 24 * 7
_PROVINCES_KEY = "georef:provinces"
_LOCALITIES_KEY = "georef:localities:"

# Georef acota la página; una provincia no llega a este número de localidades.
_MAX_LOCALITIES = 5000

#: Respaldo para cuando Georef no responde. Son los códigos INDEC, estables.
#: Sin esto el formulario quedaría inutilizable ante un corte del servicio.
FALLBACK_PROVINCES: list[dict] = [
    {"id": "02", "name": "Ciudad Autónoma de Buenos Aires"},
    {"id": "06", "name": "Buenos Aires"},
    {"id": "10", "name": "Catamarca"},
    {"id": "22", "name": "Chaco"},
    {"id": "26", "name": "Chubut"},
    {"id": "14", "name": "Córdoba"},
    {"id": "18", "name": "Corrientes"},
    {"id": "30", "name": "Entre Ríos"},
    {"id": "34", "name": "Formosa"},
    {"id": "38", "name": "Jujuy"},
    {"id": "42", "name": "La Pampa"},
    {"id": "46", "name": "La Rioja"},
    {"id": "50", "name": "Mendoza"},
    {"id": "54", "name": "Misiones"},
    {"id": "58", "name": "Neuquén"},
    {"id": "62", "name": "Río Negro"},
    {"id": "66", "name": "Salta"},
    {"id": "70", "name": "San Juan"},
    {"id": "74", "name": "San Luis"},
    {"id": "78", "name": "Santa Cruz"},
    {"id": "82", "name": "Santa Fe"},
    {"id": "86", "name": "Santiago del Estero"},
    {"id": "94", "name": "Tierra del Fuego, Antártida e Islas del Atlántico Sur"},
    {"id": "90", "name": "Tucumán"},
]


def _get(path: str, params: dict) -> dict | None:
    try:
        response = requests.get(
            f"{GEOREF_URL}/{path}",
            params=params,
            timeout=_TIMEOUT,
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
    except requests.RequestException:
        logger.warning("Georef no respondió para %s", path)
        return None
    try:
        return response.json()
    except ValueError:
        logger.warning("Georef devolvió una respuesta ilegible para %s", path)
        return None


def list_provinces() -> list[dict]:
    """Las 24 provincias, ordenadas alfabéticamente."""
    cached = cache.get(_PROVINCES_KEY)
    if cached is not None:
        return cached

    payload = _get("provincias", {"campos": "id,nombre", "max": 30})
    if payload is None:
        # No se cachea el respaldo: el próximo pedido vuelve a intentar Georef.
        return FALLBACK_PROVINCES

    provinces = sorted(
        (
            {"id": item["id"], "name": item["nombre"]}
            for item in payload.get("provincias", [])
        ),
        key=lambda item: item["name"],
    )
    if not provinces:
        return FALLBACK_PROVINCES

    cache.set(_PROVINCES_KEY, provinces, _PROVINCES_TTL)
    return provinces


def list_localities(province_id: str) -> list[dict]:
    """Localidades de una provincia, con su centroide.

    El centroide es lo que hace que elegir una ciudad ya deje el centro del área
    de cobertura puesto: el administrador solo ajusta el radio.
    """
    province_id = (province_id or "").strip()
    if not province_id:
        return []

    cache_key = f"{_LOCALITIES_KEY}{province_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    payload = _get(
        "localidades",
        {
            "provincia": province_id,
            "campos": "id,nombre,centroide",
            "max": _MAX_LOCALITIES,
        },
    )
    if payload is None:
        return []

    localities = sorted(
        (
            {
                "id": item["id"],
                "name": item["nombre"],
                "latitude": item["centroide"]["lat"],
                "longitude": item["centroide"]["lon"],
            }
            for item in payload.get("localidades", [])
            if item.get("centroide")
        ),
        key=lambda item: item["name"],
    )
    if localities:
        cache.set(cache_key, localities, _LOCALITIES_TTL)
    return localities
