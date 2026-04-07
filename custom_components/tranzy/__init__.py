"""Integrarea Tranzy pentru Home Assistant.

Gestionează:
- Setup/teardown per config entry
- Două coordinatoare (static 12h + vehicule 30s)
- Runtime data typed (TranzyRuntimeData dataclass)
"""

import logging
from dataclasses import dataclass
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .api import TranzyAPI, TranzyApiError, TranzyAuthError
from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_AGENCY_ID,
    DEFAULT_AGENCY_ID,
)
from .coordinator import TranzyStaticCoordinator, TranzyVehicleCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


@dataclass
class TranzyRuntimeData:
    """Typed runtime data pentru Tranzy integration."""

    api: TranzyAPI
    static_coordinator: TranzyStaticCoordinator
    vehicle_coordinator: TranzyVehicleCoordinator


CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.debug("Tranzy: setup entry %s", entry.entry_id)

    session = async_get_clientsession(hass)
    api = TranzyAPI(
        session=session,
        api_key=entry.data[CONF_API_KEY],
        agency_id=entry.data.get(CONF_AGENCY_ID, DEFAULT_AGENCY_ID),
    )

    try:
        await api.async_get_agencies()
    except TranzyAuthError as err:
        entry.async_start_reauth(hass)
        return False
    except TranzyApiError as err:
        raise ConfigEntryNotReady(f"Eroare API Tranzy: {err}") from err
    except (TimeoutError, aiohttp.ClientError, OSError) as err:
        raise ConfigEntryNotReady(
            f"Serverul Tranzy nu răspunde: {err}"
        ) from err

    static_coordinator = TranzyStaticCoordinator(hass, api, entry)
    try:
        await static_coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(
            f"Eroare la încărcarea datelor statice: {err}"
        ) from err

    vehicle_coordinator = TranzyVehicleCoordinator(
        hass, api, entry, static_coordinator
    )
    try:
        await vehicle_coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.warning(
            "Primul refresh vehicule a eșuat (va reîncerca): %s", err
        )

    runtime_data = TranzyRuntimeData(
        api=api,
        static_coordinator=static_coordinator,
        vehicle_coordinator=vehicle_coordinator,
    )
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = runtime_data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.debug("Tranzy: setup completat cu succes")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
