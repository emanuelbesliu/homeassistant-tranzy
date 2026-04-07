"""Data Update Coordinators pentru Tranzy.

Două coordinatoare independente:
- TranzyStaticCoordinator: date statice (rute, stații, curse, opriri) — refresh 12h
- TranzyVehicleCoordinator: poziții vehicule + calcul ETA — refresh 30s
"""

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import TranzyAPI, TranzyApiError, TranzyAuthError
from .const import (
    DOMAIN,
    CONF_SELECTED_ROUTES,
    CONF_SELECTED_STOPS,
    STATIC_UPDATE_INTERVAL,
    VEHICLE_UPDATE_INTERVAL,
)
from .helpers import (
    build_stop_sequence_map,
    filter_active_vehicles,
    get_approaching_vehicles,
    get_vehicles_on_route,
)

_LOGGER = logging.getLogger(__name__)


class TranzyStaticCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator pentru date statice: rute, stații, curse, stop_times.

    Refresh la fiecare 12 ore — aceste date se schimbă rar.
    Construiește indexuri (routes_by_id, stops_by_id, trips_by_id,
    stop_sequence_map) pentru acces rapid din VehicleCoordinator.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        api: TranzyAPI,
        entry: ConfigEntry,
    ) -> None:
        self.api = api
        self.entry = entry
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_static",
            update_interval=timedelta(seconds=STATIC_UPDATE_INTERVAL),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            routes, stops, trips, stop_times = await asyncio.gather(
                self.api.async_get_routes(),
                self.api.async_get_stops(),
                self.api.async_get_trips(),
                self.api.async_get_stop_times(),
            )

            routes_by_id: dict[int, dict[str, Any]] = {
                int(r["route_id"]): r for r in routes if "route_id" in r
            }
            stops_by_id: dict[int, dict[str, Any]] = {
                int(s["stop_id"]): s for s in stops if "stop_id" in s
            }
            trips_by_id: dict[str, dict[str, Any]] = {
                str(t["trip_id"]): t for t in trips if "trip_id" in t
            }
            stop_sequence_map = build_stop_sequence_map(stop_times)

            _LOGGER.debug(
                "Tranzy static: %d rute, %d stații, %d curse, %d stop_times",
                len(routes),
                len(stops),
                len(trips),
                len(stop_times),
            )

            return {
                "routes": routes,
                "stops": stops,
                "trips": trips,
                "stop_times": stop_times,
                "routes_by_id": routes_by_id,
                "stops_by_id": stops_by_id,
                "trips_by_id": trips_by_id,
                "stop_sequence_map": stop_sequence_map,
            }

        except TranzyAuthError as err:
            self.entry.async_start_reauth(self.hass)
            raise UpdateFailed(f"Eroare autentificare: {err}") from err
        except TranzyApiError as err:
            raise UpdateFailed(f"Eroare API Tranzy: {err}") from err


class TranzyVehicleCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator pentru poziții vehicule în timp real + calcul ETA.

    Refresh la fiecare 30 secunde.
    Depinde de TranzyStaticCoordinator pentru date de referință
    (rute, stații, secvențe opriri).
    """

    def __init__(
        self,
        hass: HomeAssistant,
        api: TranzyAPI,
        entry: ConfigEntry,
        static_coordinator: TranzyStaticCoordinator,
    ) -> None:
        self.api = api
        self.entry = entry
        self.static_coordinator = static_coordinator
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_vehicles",
            update_interval=timedelta(seconds=VEHICLE_UPDATE_INTERVAL),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        static_data = self.static_coordinator.data
        if not static_data:
            raise UpdateFailed(
                "Date statice indisponibile — așteptăm primul refresh static"
            )

        try:
            raw_vehicles = await self.api.async_get_vehicles()
        except TranzyAuthError as err:
            self.entry.async_start_reauth(self.hass)
            raise UpdateFailed(f"Eroare autentificare: {err}") from err
        except TranzyApiError as err:
            raise UpdateFailed(f"Eroare API Tranzy: {err}") from err

        active_vehicles = filter_active_vehicles(raw_vehicles)

        selected_routes = self.entry.data.get(CONF_SELECTED_ROUTES, [])
        selected_stops = self.entry.data.get(CONF_SELECTED_STOPS, [])

        routes_by_id = static_data["routes_by_id"]
        stops_by_id = static_data["stops_by_id"]
        trips_by_id = static_data["trips_by_id"]
        stop_sequence_map = static_data["stop_sequence_map"]

        # =========================================================================
        # Vehicule per rută
        # =========================================================================
        vehicles_by_route: dict[int, list[dict[str, Any]]] = {}
        for route_id in selected_routes:
            rid = int(route_id)
            vehicles_by_route[rid] = get_vehicles_on_route(active_vehicles, rid)

        # =========================================================================
        # ETA per stație per rută
        # =========================================================================
        stop_etas: dict[str, list[dict[str, Any]]] = {}
        for stop_id in selected_stops:
            sid = int(stop_id)
            stop = stops_by_id.get(sid)
            if not stop:
                continue

            stop_lat = float(stop["stop_lat"])
            stop_lon = float(stop["stop_lon"])

            for route_id in selected_routes:
                rid = int(route_id)
                approaching = get_approaching_vehicles(
                    active_vehicles,
                    sid,
                    stop_lat,
                    stop_lon,
                    stop_sequence_map,
                    stops_by_id,
                    trips_by_id,
                    route_id=rid,
                )
                key = f"{sid}_{rid}"
                stop_etas[key] = approaching

        _LOGGER.debug(
            "Tranzy vehicles: %d total, %d active, %d rute monitorizate",
            len(raw_vehicles),
            len(active_vehicles),
            len(selected_routes),
        )

        return {
            "raw_vehicles": raw_vehicles,
            "active_vehicles": active_vehicles,
            "vehicles_by_route": vehicles_by_route,
            "stop_etas": stop_etas,
        }
