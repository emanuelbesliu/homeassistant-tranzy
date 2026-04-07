"""Senzori pentru integrarea Tranzy SCTP Iași.

Două tipuri de senzori:
- TranzyRouteVehicleCountSensor — vehicule active per rută selectată
- TranzyStopETASensor — ETA per stație per rută (vehicule care se apropie)
"""

import logging
from typing import Any, Optional

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    ATTRIBUTION,
    CONF_SELECTED_ROUTES,
    CONF_SELECTED_STOPS,
    ROUTE_TYPE_TRAM,
    ROUTE_TYPE_BUS,
)
from .coordinator import TranzyVehicleCoordinator, TranzyStaticCoordinator
from .helpers import route_display_name, get_routes_serving_stop

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configurare senzori din config entry."""
    from . import TranzyRuntimeData

    runtime_data: TranzyRuntimeData = hass.data[DOMAIN][entry.entry_id]
    static_coordinator = runtime_data.static_coordinator
    vehicle_coordinator = runtime_data.vehicle_coordinator

    static_data = static_coordinator.data or {}
    routes_by_id = static_data.get("routes_by_id", {})
    stops_by_id = static_data.get("stops_by_id", {})
    trips_by_id = static_data.get("trips_by_id", {})
    stop_sequence_map = static_data.get("stop_sequence_map", {})

    selected_routes = entry.data.get(CONF_SELECTED_ROUTES, [])
    selected_stops = entry.data.get(CONF_SELECTED_STOPS, [])

    entities: list[SensorEntity] = []

    # =========================================================================
    # Senzori vehicule active per rută
    # =========================================================================
    for route_id_str in selected_routes:
        rid = int(route_id_str)
        route = routes_by_id.get(rid, {})
        entities.append(
            TranzyRouteVehicleCountSensor(
                vehicle_coordinator, entry, rid, route,
            )
        )

    # =========================================================================
    # Senzori ETA per stație per rută
    # =========================================================================
    selected_route_ids = [int(r) for r in selected_routes]

    for stop_id_str in selected_stops:
        sid = int(stop_id_str)
        stop = stops_by_id.get(sid, {})

        serving_routes = get_routes_serving_stop(
            sid, stop_sequence_map, trips_by_id, selected_route_ids,
        )

        for rid in serving_routes:
            route = routes_by_id.get(rid, {})
            entities.append(
                TranzyStopETASensor(
                    vehicle_coordinator, entry, sid, stop, rid, route,
                )
            )

    async_add_entities(entities)
    _LOGGER.info("Au fost creați %d senzori Tranzy", len(entities))


# =============================================================================
# Senzor de bază
# =============================================================================


class TranzyBaseSensor(CoordinatorEntity, SensorEntity):
    """Senzor de bază pentru Tranzy SCTP Iași.

    Folosește vehicle_coordinator ca sursă de date (refresh 30s).
    """

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TranzyVehicleCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry

    @property
    def _data(self) -> dict[str, Any]:
        """Shortcut la datele vehicle coordinator-ului."""
        return self.coordinator.data or {}

    @property
    def device_info(self) -> dict[str, Any]:
        """Informații despre device — un singur device per config entry."""
        return {
            "identifiers": {(DOMAIN, self.entry.entry_id)},
            "name": "Tranzy SCTP Iași",
            "manufacturer": "Tranzy.ai",
            "model": "OpenData SCTP Iași",
            "entry_type": DeviceEntryType.SERVICE,
        }


# =============================================================================
# Senzor vehicule active pe o rută
# =============================================================================


class TranzyRouteVehicleCountSensor(TranzyBaseSensor):
    """Număr de vehicule active pe o rută.

    State: număr vehicule active (int)
    Atribute: lista vehiculelor cu label, viteză, coordonate.
    """

    def __init__(
        self,
        coordinator: TranzyVehicleCoordinator,
        entry: ConfigEntry,
        route_id: int,
        route: dict[str, Any],
    ) -> None:
        super().__init__(coordinator, entry)
        self._route_id = route_id
        self._route = route

        short_name = route.get("route_short_name", str(route_id))
        rtype = route.get("route_type", ROUTE_TYPE_BUS)

        self._attr_name = f"{route_display_name(route)} Active"
        self._attr_unique_id = f"{entry.entry_id}_route_{route_id}_vehicles"
        self._attr_icon = "mdi:tram" if rtype == ROUTE_TYPE_TRAM else "mdi:bus"

    @property
    def native_value(self) -> int:
        vehicles_by_route = self._data.get("vehicles_by_route", {})
        return len(vehicles_by_route.get(self._route_id, []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        vehicles_by_route = self._data.get("vehicles_by_route", {})
        vehicles = vehicles_by_route.get(self._route_id, [])

        vehicle_list = []
        for v in vehicles:
            vehicle_list.append({
                "label": v.get("label", ""),
                "speed_kmh": round(float(v.get("speed", 0) or 0) * 3.6, 1),
                "latitude": v.get("latitude"),
                "longitude": v.get("longitude"),
                "trip_id": v.get("trip_id"),
            })

        attrs: dict[str, Any] = {
            "route_id": self._route_id,
            "route_short_name": self._route.get("route_short_name", ""),
            "route_long_name": self._route.get("route_long_name", ""),
            "route_type": "tram" if self._route.get("route_type") == ROUTE_TYPE_TRAM else "bus",
            "vehicles": vehicle_list,
        }
        return attrs


# =============================================================================
# Senzor ETA la stație per rută
# =============================================================================


class TranzyStopETASensor(TranzyBaseSensor):
    """ETA estimat pentru vehiculele care se apropie de o stație pe o rută.

    State: ETA în minute al primului vehicul (float sau None)
    Atribute: detalii vehicul, distanță, viteză, număr vehicule care se apropie.
    """

    _attr_native_unit_of_measurement = "min"
    _attr_icon = "mdi:clock-outline"

    def __init__(
        self,
        coordinator: TranzyVehicleCoordinator,
        entry: ConfigEntry,
        stop_id: int,
        stop: dict[str, Any],
        route_id: int,
        route: dict[str, Any],
    ) -> None:
        super().__init__(coordinator, entry)
        self._stop_id = stop_id
        self._stop = stop
        self._route_id = route_id
        self._route = route

        short_name = route.get("route_short_name", str(route_id))
        stop_name = stop.get("stop_name", f"Stop {stop_id}")
        rtype = route.get("route_type", ROUTE_TYPE_BUS)
        prefix = "Tram" if rtype == ROUTE_TYPE_TRAM else "Bus"

        self._attr_name = f"{prefix} {short_name} → {stop_name}"
        self._attr_unique_id = (
            f"{entry.entry_id}_stop_{stop_id}_route_{route_id}_eta"
        )

    @property
    def native_value(self) -> Optional[float]:
        stop_etas = self._data.get("stop_etas", {})
        key = f"{self._stop_id}_{self._route_id}"
        approaching = stop_etas.get(key, [])
        if approaching:
            return approaching[0].get("eta_minutes")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        stop_etas = self._data.get("stop_etas", {})
        key = f"{self._stop_id}_{self._route_id}"
        approaching = stop_etas.get(key, [])

        attrs: dict[str, Any] = {
            "stop_id": self._stop_id,
            "stop_name": self._stop.get("stop_name", ""),
            "stop_lat": self._stop.get("stop_lat"),
            "stop_lon": self._stop.get("stop_lon"),
            "route_id": self._route_id,
            "route_short_name": self._route.get("route_short_name", ""),
            "vehicles_approaching": len(approaching),
        }

        if approaching:
            first = approaching[0]
            attrs["next_vehicle_label"] = first.get("label", "")
            attrs["next_vehicle_distance_m"] = first.get("distance_m")
            attrs["next_vehicle_speed_kmh"] = first.get("speed_kmh")
            attrs["next_vehicle_headsign"] = first.get("trip_headsign", "")

            # Lista tuturor vehiculelor care se apropie
            if len(approaching) > 1:
                vehicles_list = []
                for v in approaching:
                    vehicles_list.append({
                        "label": v.get("label", ""),
                        "eta_minutes": v.get("eta_minutes"),
                        "distance_m": v.get("distance_m"),
                        "speed_kmh": v.get("speed_kmh"),
                        "headsign": v.get("trip_headsign", ""),
                    })
                attrs["all_approaching"] = vehicles_list

        return attrs
