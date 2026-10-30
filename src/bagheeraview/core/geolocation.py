"""Coordinate parsing and place-name geocoding services for Bagheera.

The module recognizes decimal coordinates, degrees/minutes/seconds (DMS), and
complete Google Open Location Codes (Plus Codes). Text that is not one of
these formats can be resolved through Nominatim.

Nominatim requests run on a Qt worker thread so callers can use them from the
GUI without blocking the event loop. They are rate-limited to comply with the
public service's usage policy.

The public API is :func:`parse_coordinates` and
:func:`search_nominatim_async`. GPS metadata remains the responsibility of
``metadatamanager``.
"""
import re
from typing import Callable, Optional, Tuple

from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim
from PySide6.QtCore import QThread, Signal


__all__ = ["parse_coordinates", "search_nominatim_async"]

Coordinates = Tuple[float, float]
SearchCallback = Callable[[str, Optional[Coordinates], str], None]


_nominatim_geocode = RateLimiter(
    Nominatim(user_agent="Bagheera/1.0", timeout=10).geocode,
    min_delay_seconds=1,
    max_retries=0,
    swallow_exceptions=False)
_active_geocoding_threads = set()


def parse_coordinates(value: str) -> Optional[Coordinates]:
    """Parse a coordinate string into decimal latitude and longitude.

    Accepted formats are ``latitude, longitude`` in decimal degrees, DMS
    pairs such as ``38°11'56.7"N 128°28'00.3"E``, and complete Plus Codes.
    Latitude and longitude are range-checked. A string that does not match a
    supported coordinate format returns ``None`` so the caller may try a
    place-name lookup.

    Args:
        value: User-entered coordinate text.

    Returns:
        A ``(latitude, longitude)`` pair in decimal degrees, or ``None`` if
        the input is not a valid supported coordinate format.
    """
    value = value.strip()
    plus_code_coordinates = _decode_plus_code(value)
    if plus_code_coordinates is not None:
        return plus_code_coordinates

    decimal_match = re.fullmatch(
        r"\s*([+-]?\d+(?:\.\d+)?)\s*,\s*"
        r"([+-]?\d+(?:\.\d+)?)\s*", value)
    if decimal_match:
        lat, lon = map(float, decimal_match.groups())
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
        return None

    dms_pattern = (
        r"\s*(\d{1,3})\s*°\s*(\d{1,2})\s*['′]\s*"
        r"(\d{1,2}(?:\.\d+)?)\s*[\"″]\s*([NSEW])\s+"
        r"(\d{1,3})\s*°\s*(\d{1,2})\s*['′]\s*"
        r"(\d{1,2}(?:\.\d+)?)\s*[\"″]\s*([NSEW])\s*"
    )
    dms_match = re.fullmatch(dms_pattern, value, re.IGNORECASE)
    if not dms_match:
        return None

    parts = dms_match.groups()

    def to_decimal(degrees, minutes, seconds, hemisphere, maximum,
                   valid_hemispheres, positive_hemispheres):
        degrees = int(degrees)
        minutes = int(minutes)
        seconds = float(seconds)
        hemisphere = hemisphere.upper()
        if (hemisphere not in valid_hemispheres or
                minutes >= 60 or seconds >= 60 or
                degrees > maximum or
                (degrees == maximum and (minutes or seconds))):
            return None
        coordinate = degrees + minutes / 60 + seconds / 3600
        return coordinate if hemisphere in positive_hemispheres \
            else -coordinate

    latitude = to_decimal(*parts[:4], 90, {"N", "S"}, {"N"})
    longitude = to_decimal(*parts[4:], 180, {"E", "W"}, {"E"})
    if latitude is None or longitude is None:
        return None
    return latitude, longitude


def _decode_plus_code(value: str) -> Optional[Coordinates]:
    """Decode a complete Open Location Code to the center of its cell."""
    alphabet = "23456789CFGHJMPQRVWX"
    match = re.fullmatch(
        r"([23456789CFGHJMPQRVWX]{8})\+"
        r"(?:[23456789CFGHJMPQRVWX]{2,7})?",
        value.strip().upper())
    if not match:
        return None

    code = match.group(1) + value.strip().upper().split("+", 1)[1]
    latitude, longitude = -90.0, -180.0
    resolution = 20.0
    try:
        pair_length = min(len(code), 10)
        for index in range(0, pair_length, 2):
            latitude += alphabet.index(code[index]) * resolution
            longitude += alphabet.index(code[index + 1]) * resolution
            if index < 8:
                resolution /= 20

        latitude_size = longitude_size = resolution
        for character in code[10:]:
            grid_index = alphabet.index(character)
            latitude_size /= 5
            longitude_size /= 4
            latitude += (grid_index // 4) * latitude_size
            longitude += (grid_index % 4) * longitude_size
    except (IndexError, ValueError):
        return None

    latitude += latitude_size / 2
    longitude += longitude_size / 2
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    return latitude, longitude


class _NominatimGeocodeThread(QThread):
    """Run one Nominatim lookup without blocking the Qt GUI thread."""

    completed = Signal(str, object, str)

    def __init__(self, query: str):
        """Create a worker for a place-name query."""
        super().__init__()
        self.query = query

    def run(self):
        """Emit ``(query, coordinates, error)`` when the lookup completes."""
        try:
            location = _nominatim_geocode(self.query)
            coordinates = (
                (location.latitude, location.longitude) if location else None)
            self.completed.emit(self.query, coordinates, "")
        except Exception as exc:
            self.completed.emit(self.query, None, str(exc))


def _release_geocoding_thread(thread):
    _active_geocoding_threads.discard(thread)
    thread.deleteLater()


def search_nominatim_async(
        query: str, completed_callback: SearchCallback) -> QThread:
    """Start an asynchronous Nominatim place-name lookup.

    The callback is invoked in the Qt event loop with three arguments:
    ``query``, ``coordinates``, and ``error``. ``coordinates`` is a decimal
    ``(latitude, longitude)`` pair when a match is found, or ``None`` when
    there is no match or the request fails. In the latter case, ``error`` is
    empty for no match and contains the exception message for request errors.

    Keep the returned thread reference while it is running. The module retains
    active workers until they finish, and then schedules them for deletion.

    Args:
        query: Place name or address to resolve.
        completed_callback: Callable receiving the query, optional coordinate
            pair, and an error string.

    Returns:
        The running ``QThread`` performing the request.
    """
    thread = _NominatimGeocodeThread(query)
    thread.completed.connect(completed_callback)
    _active_geocoding_threads.add(thread)
    thread.finished.connect(
        lambda worker=thread: _release_geocoding_thread(worker))
    thread.start()
    return thread
