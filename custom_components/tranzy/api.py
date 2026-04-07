"""Client API async pentru Tranzy.ai OpenData (SCTP Iași).

Toate endpoint-urile sunt GET cu autentificare prin header X-API-KEY.
Folosește aiohttp (via HA async_get_clientsession).
"""

import logging
from typing import Any

import aiohttp

from .const import (
    API_BASE_URL,
    API_PATH_AGENCY,
    API_PATH_ROUTES,
    API_PATH_STOPS,
    API_PATH_TRIPS,
    API_PATH_STOP_TIMES,
    API_PATH_VEHICLES,
)

_LOGGER = logging.getLogger(__name__)


class TranzyApiError(Exception):
    """Eroare generală API Tranzy."""


class TranzyAuthError(TranzyApiError):
    """Eroare de autentificare (API key invalid)."""


class TranzyAPI:
    """Client API async pentru Tranzy.ai OpenData."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        agency_id: str = "1",
    ) -> None:
        self._session = session
        self._api_key = api_key
        self._agency_id = agency_id

    def _headers(self, include_agency: bool = True) -> dict[str, str]:
        h: dict[str, str] = {
            "X-API-KEY": self._api_key,
            "Accept": "application/json",
        }
        if include_agency:
            h["X-Agency-Id"] = self._agency_id
        return h

    # =========================================================================
    # Endpoint-uri publice
    # =========================================================================

    async def async_get_agencies(self) -> list[dict[str, Any]]:
        """GET /agency — lista agențiilor (fără X-Agency-Id)."""
        return await self._get_request(
            API_PATH_AGENCY,
            include_agency=False,
            description="GET agencies",
        )

    async def async_get_routes(self) -> list[dict[str, Any]]:
        """GET /routes — definiții rute."""
        return await self._get_request(
            API_PATH_ROUTES,
            description="GET routes",
        )

    async def async_get_stops(self) -> list[dict[str, Any]]:
        """GET /stops — stații cu coordonate GPS."""
        return await self._get_request(
            API_PATH_STOPS,
            description="GET stops",
        )

    async def async_get_trips(self) -> list[dict[str, Any]]:
        """GET /trips — curse (trip_id → route_id, headsign, direction)."""
        return await self._get_request(
            API_PATH_TRIPS,
            description="GET trips",
        )

    async def async_get_stop_times(self) -> list[dict[str, Any]]:
        """GET /stop_times — secvența stațiilor per cursă."""
        return await self._get_request(
            API_PATH_STOP_TIMES,
            description="GET stop_times",
        )

    async def async_get_vehicles(self) -> list[dict[str, Any]]:
        """GET /vehicles — poziții vehicule în timp real."""
        return await self._get_request(
            API_PATH_VEHICLES,
            description="GET vehicles",
        )

    # =========================================================================
    # Request intern
    # =========================================================================

    async def _get_request(
        self,
        path: str,
        include_agency: bool = True,
        description: str = "",
    ) -> list[dict[str, Any]]:
        url = f"{API_BASE_URL}{path}"
        headers = self._headers(include_agency=include_agency)

        _LOGGER.debug("Tranzy API: %s (%s)", path, description)

        try:
            async with self._session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 403:
                    raise TranzyAuthError(
                        f"API key invalid sau acces refuzat: {response.status}"
                    )
                if response.status == 429:
                    raise TranzyApiError(
                        "Rate limit depășit — prea multe cereri"
                    )
                if response.status != 200:
                    text = await response.text()
                    raise TranzyApiError(
                        f"Eroare la {description}: {response.status} — {text}"
                    )
                return await response.json()

        except aiohttp.ClientError as err:
            raise TranzyApiError(
                f"Eroare de conexiune la {description}: {err}"
            ) from err
