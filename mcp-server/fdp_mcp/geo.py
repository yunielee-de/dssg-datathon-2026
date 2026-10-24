"""Distance helpers. Pure functions, no I/O."""

import math

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometres."""

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bounding_box(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """Return (south, north, west, east) enclosing a circle of radius_km around the point."""

    d_lat = math.degrees(radius_km / EARTH_RADIUS_KM)
    d_lon = math.degrees(radius_km / (EARTH_RADIUS_KM * math.cos(math.radians(lat))))
    return lat - d_lat, lat + d_lat, lon - d_lon, lon + d_lon
