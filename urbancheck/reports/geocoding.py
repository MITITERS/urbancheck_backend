"""Geocodificación de direcciones escritas a mano vía Nominatim (OpenStreetMap).

Nominatim es gratuito y no requiere API key, pero su política de uso exige:
- Enviar un User-Agent identificable (configurado en ``NOMINATIM_USER_AGENT``).
- No superar 1 request/segundo contra el servidor público.
- Cachear resultados para no repetir consultas.

Por eso este módulo actúa como único punto de salida hacia Nominatim: cachea cada
consulta y centraliza el User-Agent, en lugar de que cada dispositivo móvil pegue
directo contra OSM.
"""

import hashlib
import logging

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Nominatim recomienda cachear; guardamos cada búsqueda 24h.
_CACHE_TTL = 60 * 60 * 24
_CACHE_PREFIX = "geocode:"
_TIMEOUT = 5  # segundos


def search_addresses(query: str, *, limit: int = 5) -> list[dict]:
    """Devuelve sugerencias de direcciones para ``query``.

    Cada resultado es ``{"display_name": str, "latitude": float, "longitude": float}``.
    Ante cualquier error (timeout, red, respuesta inválida) devuelve ``[]`` en vez de
    propagar la excepción: la geocodificación es best-effort y nunca debe romper el
    flujo de creación de un reporte.
    """
    query = (query or "").strip()
    if len(query) < 3:
        return []

    # Hasheamos la consulta para que la clave no tenga espacios ni acentos (que
    # rompen backends como memcached).
    digest = hashlib.sha1(query.lower().encode("utf-8")).hexdigest()
    cache_key = f"{_CACHE_PREFIX}{limit}:{digest}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    params = {
        "q": query,
        "format": "jsonv2",
        "limit": limit,
        "addressdetails": 0,
    }
    countrycodes = getattr(settings, "NOMINATIM_COUNTRYCODES", "")
    if countrycodes:
        params["countrycodes"] = countrycodes

    try:
        response = requests.get(
            settings.NOMINATIM_URL,
            params=params,
            headers={"User-Agent": settings.NOMINATIM_USER_AGENT},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        raw = response.json()
    except (requests.RequestException, ValueError):
        logger.warning("Nominatim geocode failed for query=%r", query, exc_info=True)
        return []

    results = []
    for item in raw:
        try:
            results.append(
                {
                    "display_name": item["display_name"],
                    "latitude": float(item["lat"]),
                    "longitude": float(item["lon"]),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue

    cache.set(cache_key, results, _CACHE_TTL)
    return results


def geocode_one(query: str) -> dict | None:
    """Devuelve la mejor coincidencia para ``query`` o ``None``.

    Se usa como fallback al crear un reporte con dirección pero sin coordenadas.
    """
    results = search_addresses(query, limit=1)
    return results[0] if results else None


def reverse_geocode(latitude, longitude) -> str:
    """Devuelve la dirección de unas coordenadas, o ``""`` si no se pudo resolver.

    Es la operación inversa de ``geocode_one``: hace falta porque un reporte
    creado con GPS llega solo con lat/lng, y sin texto de dirección la búsqueda
    por calle, barrio o localidad (US-020) no puede encontrarlo.

    Best-effort, igual que el resto del módulo: ante cualquier error devuelve
    cadena vacía en vez de romper el alta del reporte.
    """
    if latitude is None or longitude is None:
        return ""

    digest = hashlib.sha1(f"{latitude},{longitude}".encode()).hexdigest()
    cache_key = f"{_CACHE_PREFIX}rev:{digest}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        response = requests.get(
            settings.NOMINATIM_REVERSE_URL,
            params={
                "lat": str(latitude),
                "lon": str(longitude),
                "format": "jsonv2",
                # Nivel de detalle: calle y numeración, sin bajar a cada edificio.
                "zoom": 18,
                "addressdetails": 0,
            },
            headers={"User-Agent": settings.NOMINATIM_USER_AGENT},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        raw = response.json()
    except (requests.RequestException, ValueError):
        logger.warning(
            "Nominatim reverse failed for lat=%r lon=%r",
            latitude,
            longitude,
            exc_info=True,
        )
        return ""

    address = raw.get("display_name", "") if isinstance(raw, dict) else ""
    if address:
        cache.set(cache_key, address, _CACHE_TTL)
    return address
