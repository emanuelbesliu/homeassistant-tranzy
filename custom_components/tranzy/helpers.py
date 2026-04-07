"""Funcții utilitare pentru integrarea Tranzy.

Include: Haversine, calcul ETA, filtrare vehicule, mapare secvențe stații.
"""

import math
import time
from typing import Any, Optional

from .const import (
    EARTH_RADIUS_M,
    STALE_VEHICLE_THRESHOLD_S,
    STOP_PROXIMITY_THRESHOLD_M,
    DEFAULT_SPEED_MPS,
    ROUTE_TYPE_TRAM,
    ROUTE_TYPE_BUS,
)


def haversine_distance(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Distanța în metri între două puncte GPS (formula Haversine)."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def calculate_eta_minutes(
    distance_m: float, speed_mps: float
) -> Optional[float]:
    """ETA în minute. Returnează None dacă viteza e invalidă."""
    if speed_mps <= 0:
        return None
    return (distance_m / speed_mps) / 60.0


def is_vehicle_active(vehicle: dict[str, Any]) -> bool:
    """Vehicul activ: are GPS valid și date recente (< 5 min)."""
    if vehicle.get("latitude") is None or vehicle.get("longitude") is None:
        return False
    ts = vehicle.get("timestamp")
    if ts is None:
        return False
    return (time.time() - ts) < STALE_VEHICLE_THRESHOLD_S


def filter_active_vehicles(
    vehicles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Filtrează vehiculele inactive / în depou / cu date vechi."""
    return [v for v in vehicles if is_vehicle_active(v)]


def get_vehicles_on_route(
    vehicles: list[dict[str, Any]], route_id: int
) -> list[dict[str, Any]]:
    """Vehicule active pe o rută specifică."""
    return [
        v
        for v in vehicles
        if is_vehicle_active(v) and str(v.get("route_id")) == str(route_id)
    ]


def build_stop_sequence_map(
    stop_times: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Construiește {trip_id: [{stop_id, stop_sequence}, ...]} sortat după secvență."""
    seq_map: dict[str, list[dict[str, Any]]] = {}
    for st in stop_times:
        trip_id = str(st.get("trip_id", ""))
        if not trip_id:
            continue
        seq_map.setdefault(trip_id, []).append(
            {
                "stop_id": st.get("stop_id"),
                "stop_sequence": st.get("stop_sequence", 0),
            }
        )
    for trip_id in seq_map:
        seq_map[trip_id].sort(key=lambda x: x["stop_sequence"])
    return seq_map


def _find_vehicle_sequence_position(
    vehicle_lat: float,
    vehicle_lon: float,
    trip_stops: list[dict[str, Any]],
    stops_by_id: dict[int, dict[str, Any]],
) -> int:
    """Găsește secvența celei mai apropiate stații de vehicul pe traseul cursei.

    Returnează stop_sequence-ul stației cele mai apropiate.
    Necesar pentru a determina dacă vehiculul a trecut sau nu de o stație.
    """
    min_dist = float("inf")
    closest_seq = 0
    for ts in trip_stops:
        stop = stops_by_id.get(ts["stop_id"])
        if not stop:
            continue
        dist = haversine_distance(
            vehicle_lat,
            vehicle_lon,
            float(stop["stop_lat"]),
            float(stop["stop_lon"]),
        )
        if dist < min_dist:
            min_dist = dist
            closest_seq = ts["stop_sequence"]
    return closest_seq


def get_stop_sequence_for_trip(
    trip_id: str,
    stop_id: int,
    stop_sequence_map: dict[str, list[dict[str, Any]]],
) -> Optional[int]:
    """Returnează stop_sequence pentru un stop_id într-o cursă specifică."""
    trip_stops = stop_sequence_map.get(trip_id, [])
    for ts in trip_stops:
        if ts["stop_id"] == stop_id:
            return ts["stop_sequence"]
    return None


def get_approaching_vehicles(
    vehicles: list[dict[str, Any]],
    stop_id: int,
    stop_lat: float,
    stop_lon: float,
    stop_sequence_map: dict[str, list[dict[str, Any]]],
    stops_by_id: dict[int, dict[str, Any]],
    trips_by_id: dict[str, dict[str, Any]],
    route_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Vehicule care se apropie de o stație, sortate după ETA.

    Logica:
    1. Pentru fiecare vehicul activ cu trip_id valid
    2. Verifică dacă trip-ul deservește stația (stop_id în secvența trip-ului)
    3. Determină dacă vehiculul e ÎNAINTE de stație (secvența vehicul < secvența stație)
    4. Calculează distanța și ETA
    5. Opțional filtrează după route_id

    Returnează liste de dict-uri cu: vehicle + distance_m, eta_minutes, route_id, trip_headsign.
    """
    results: list[dict[str, Any]] = []

    for vehicle in vehicles:
        if not is_vehicle_active(vehicle):
            continue

        v_trip_id = vehicle.get("trip_id")
        if not v_trip_id:
            continue
        v_trip_id = str(v_trip_id)

        # Opțional: filtrează pe ruta selectată
        if route_id is not None:
            v_route_id = str(vehicle.get("route_id", ""))
            if v_route_id != str(route_id):
                continue

        # Verifică dacă cursul servește stația
        target_seq = get_stop_sequence_for_trip(
            v_trip_id, stop_id, stop_sequence_map
        )
        if target_seq is None:
            continue

        v_lat = float(vehicle["latitude"])
        v_lon = float(vehicle["longitude"])

        # Determină poziția vehiculului în secvența cursei
        trip_stops = stop_sequence_map.get(v_trip_id, [])
        vehicle_seq = _find_vehicle_sequence_position(
            v_lat, v_lon, trip_stops, stops_by_id
        )

        # Vehiculul trebuie să fie ÎNAINTE de stație
        if vehicle_seq >= target_seq:
            continue

        distance_m = haversine_distance(v_lat, v_lon, stop_lat, stop_lon)

        speed = vehicle.get("speed")
        speed_mps = float(speed) if speed and float(speed) > 0 else DEFAULT_SPEED_MPS

        eta = calculate_eta_minutes(distance_m, speed_mps)
        if eta is None:
            continue

        trip_info = trips_by_id.get(v_trip_id, {})

        results.append(
            {
                **vehicle,
                "distance_m": round(distance_m, 0),
                "eta_minutes": round(eta, 1),
                "trip_headsign": trip_info.get("trip_headsign", ""),
                "speed_kmh": round(speed_mps * 3.6, 1),
            }
        )

    results.sort(key=lambda x: x["eta_minutes"])
    return results


def get_routes_serving_stop(
    stop_id: int,
    stop_sequence_map: dict[str, list[dict[str, Any]]],
    trips_by_id: dict[str, dict[str, Any]],
    selected_route_ids: Optional[list[int]] = None,
) -> set[int]:
    """Returnează set-ul de route_id-uri care deservesc o stație.

    Parcurge toate trip-urile din stop_sequence_map, verifică dacă stop_id
    apare în secvența lor, și colectează route_id-urile corespunzătoare.
    """
    route_ids: set[int] = set()
    for trip_id, stops in stop_sequence_map.items():
        for ts in stops:
            if ts["stop_id"] == stop_id:
                trip = trips_by_id.get(trip_id, {})
                rid = trip.get("route_id")
                if rid is not None:
                    rid_int = int(rid)
                    if selected_route_ids is None or rid_int in selected_route_ids:
                        route_ids.add(rid_int)
                break
    return route_ids


def route_display_name(route: dict[str, Any]) -> str:
    """Construiește numele afișabil: 'Tram 3' sau 'Bus 101 — Nume Rută'."""
    rtype = route.get("route_type", ROUTE_TYPE_BUS)
    prefix = "Tram" if rtype == ROUTE_TYPE_TRAM else "Bus"
    short_name = route.get("route_short_name", "")
    long_name = route.get("route_long_name", "")
    if long_name:
        return f"{prefix} {short_name} — {long_name}"
    return f"{prefix} {short_name}"
