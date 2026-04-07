"""Config flow pentru Tranzy.

Pași:
1. API key — validare prin GET /agency
2. Selecție rute favorite (multi-select din /routes)
3. Selecție stații favorite (multi-select din /stops, filtrate pe rutele selectate)
"""

import logging
from typing import Any, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    SelectOptionDict,
)

from .api import TranzyAPI, TranzyAuthError, TranzyApiError
from .const import (
    DOMAIN,
    CONFIG_VERSION,
    CONF_API_KEY,
    CONF_AGENCY_ID,
    CONF_SELECTED_ROUTES,
    CONF_SELECTED_STOPS,
    DEFAULT_AGENCY_ID,
    ROUTE_TYPE_TRAM,
)
from .helpers import (
    build_stop_sequence_map,
    get_routes_serving_stop,
    route_display_name,
)

_LOGGER = logging.getLogger(__name__)


class TranzyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow pentru Tranzy SCTP Iași."""

    VERSION = CONFIG_VERSION

    def __init__(self) -> None:
        self._api_key: Optional[str] = None
        self._api: Optional[TranzyAPI] = None
        self._routes: list[dict[str, Any]] = []
        self._stops: list[dict[str, Any]] = []
        self._trips: list[dict[str, Any]] = []
        self._stop_times: list[dict[str, Any]] = []
        self._selected_routes: list[str] = []

    # =========================================================================
    # Pas 1: API Key
    # =========================================================================

    async def async_step_user(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._api_key = user_input[CONF_API_KEY]

            try:
                session = async_get_clientsession(self.hass)
                self._api = TranzyAPI(
                    session=session,
                    api_key=self._api_key,
                    agency_id=DEFAULT_AGENCY_ID,
                )
                agencies = await self._api.async_get_agencies()
                if not agencies:
                    errors["base"] = "no_agencies"
                else:
                    self._routes = await self._api.async_get_routes()
                    if not self._routes:
                        errors["base"] = "no_routes"
                    else:
                        return await self.async_step_select_routes()

            except TranzyAuthError:
                errors["base"] = "invalid_auth"
            except TranzyApiError:
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.error("Eroare la validarea API key Tranzy: %s", err)
                errors["base"] = "unknown"

        data_schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    # =========================================================================
    # Pas 2: Selecție rute
    # =========================================================================

    async def async_step_select_routes(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> FlowResult:
        if user_input is not None:
            self._selected_routes = user_input.get(CONF_SELECTED_ROUTES, [])
            if not self._selected_routes:
                return self.async_show_form(
                    step_id="select_routes",
                    data_schema=self._routes_schema(),
                    errors={"base": "no_selection"},
                )

            assert self._api is not None
            self._stops = await self._api.async_get_stops()
            self._trips = await self._api.async_get_trips()
            self._stop_times = await self._api.async_get_stop_times()
            return await self.async_step_select_stops()

        return self.async_show_form(
            step_id="select_routes",
            data_schema=self._routes_schema(),
        )

    def _routes_schema(self) -> vol.Schema:
        sorted_routes = sorted(
            self._routes,
            key=lambda r: (r.get("route_type", 99), r.get("route_short_name", "")),
        )
        route_options = [
            SelectOptionDict(
                value=str(r["route_id"]),
                label=route_display_name(r),
            )
            for r in sorted_routes
        ]
        return vol.Schema(
            {
                vol.Required(CONF_SELECTED_ROUTES): SelectSelector(
                    SelectSelectorConfig(
                        options=route_options,
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

    # =========================================================================
    # Pas 3: Selecție stații
    # =========================================================================

    async def async_step_select_stops(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> FlowResult:
        if user_input is not None:
            selected_stops = user_input.get(CONF_SELECTED_STOPS, [])
            if not selected_stops:
                return self.async_show_form(
                    step_id="select_stops",
                    data_schema=self._stops_schema(),
                    errors={"base": "no_selection"},
                )
            return await self._create_entry(selected_stops)

        return self.async_show_form(
            step_id="select_stops",
            data_schema=self._stops_schema(),
        )

    def _stops_schema(self) -> vol.Schema:
        trips_by_id = {str(t["trip_id"]): t for t in self._trips if "trip_id" in t}
        stop_sequence_map = build_stop_sequence_map(self._stop_times)
        selected_route_ids = [int(r) for r in self._selected_routes]

        served_stop_ids: set[int] = set()
        stops_by_id = {int(s["stop_id"]): s for s in self._stops if "stop_id" in s}
        for sid in stops_by_id:
            serving = get_routes_serving_stop(
                sid, stop_sequence_map, trips_by_id, selected_route_ids
            )
            if serving:
                served_stop_ids.add(sid)

        served_stops = [
            s for s in self._stops if int(s.get("stop_id", 0)) in served_stop_ids
        ]
        served_stops.sort(key=lambda s: s.get("stop_name", ""))

        stop_options = [
            SelectOptionDict(
                value=str(s["stop_id"]),
                label=s.get("stop_name", f"Stop {s['stop_id']}"),
            )
            for s in served_stops
        ]

        return vol.Schema(
            {
                vol.Required(CONF_SELECTED_STOPS): SelectSelector(
                    SelectSelectorConfig(
                        options=stop_options,
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

    # =========================================================================
    # Creare entry
    # =========================================================================

    async def _create_entry(self, selected_stops: list[str]) -> FlowResult:
        await self.async_set_unique_id(f"tranzy_{self._api_key[:8]}")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title="Tranzy SCTP Iași",
            data={
                CONF_API_KEY: self._api_key,
                CONF_AGENCY_ID: DEFAULT_AGENCY_ID,
                CONF_SELECTED_ROUTES: self._selected_routes,
                CONF_SELECTED_STOPS: selected_stops,
            },
        )

    # =========================================================================
    # Reauth flow
    # =========================================================================

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            try:
                session = async_get_clientsession(self.hass)
                api = TranzyAPI(session=session, api_key=api_key)
                await api.async_get_agencies()

                if self._reauth_entry:
                    new_data = {**self._reauth_entry.data}
                    new_data[CONF_API_KEY] = api_key
                    self.hass.config_entries.async_update_entry(
                        self._reauth_entry, data=new_data
                    )
                    await self.hass.config_entries.async_reload(
                        self._reauth_entry.entry_id
                    )
                    return self.async_abort(reason="reauth_successful")

            except TranzyAuthError:
                errors["base"] = "invalid_auth"
            except TranzyApiError:
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.error("Eroare la reautentificare Tranzy: %s", err)
                errors["base"] = "unknown"

        data_schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
            }
        )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=data_schema,
            errors=errors,
        )

    # =========================================================================
    # Options flow
    # =========================================================================

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return TranzyOptionsFlowHandler()


class TranzyOptionsFlowHandler(config_entries.OptionsFlow):
    """Permite modificarea rutelor și stațiilor favorite."""

    def __init__(self) -> None:
        self._routes: list[dict[str, Any]] = []
        self._stops: list[dict[str, Any]] = []
        self._trips: list[dict[str, Any]] = []
        self._stop_times: list[dict[str, Any]] = []
        self._selected_routes: list[str] = []

    async def async_step_init(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> FlowResult:
        session = async_get_clientsession(self.hass)
        api = TranzyAPI(
            session=session,
            api_key=self.config_entry.data[CONF_API_KEY],
            agency_id=self.config_entry.data.get(CONF_AGENCY_ID, DEFAULT_AGENCY_ID),
        )

        try:
            self._routes = await api.async_get_routes()
        except (TranzyApiError, TranzyAuthError) as err:
            _LOGGER.error("Eroare la obținerea rutelor: %s", err)
            return self.async_abort(reason="cannot_connect")

        current_routes = self.config_entry.data.get(CONF_SELECTED_ROUTES, [])

        if user_input is not None:
            self._selected_routes = user_input.get(CONF_SELECTED_ROUTES, current_routes)

            try:
                self._stops = await api.async_get_stops()
                self._trips = await api.async_get_trips()
                self._stop_times = await api.async_get_stop_times()
            except (TranzyApiError, TranzyAuthError) as err:
                _LOGGER.error("Eroare la obținerea stațiilor: %s", err)
                return self.async_abort(reason="cannot_connect")

            return await self.async_step_select_stops()

        sorted_routes = sorted(
            self._routes,
            key=lambda r: (r.get("route_type", 99), r.get("route_short_name", "")),
        )
        route_options = [
            SelectOptionDict(
                value=str(r["route_id"]),
                label=route_display_name(r),
            )
            for r in sorted_routes
        ]

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_SELECTED_ROUTES, default=current_routes
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=route_options,
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
        )

    async def async_step_select_stops(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> FlowResult:
        if user_input is not None:
            selected_stops = user_input.get(CONF_SELECTED_STOPS, [])
            new_data = {
                **self.config_entry.data,
                CONF_SELECTED_ROUTES: self._selected_routes,
                CONF_SELECTED_STOPS: selected_stops,
            }
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )
            return self.async_create_entry(title="", data={})

        trips_by_id = {str(t["trip_id"]): t for t in self._trips if "trip_id" in t}
        stop_sequence_map = build_stop_sequence_map(self._stop_times)
        selected_route_ids = [int(r) for r in self._selected_routes]

        served_stop_ids: set[int] = set()
        stops_by_id = {int(s["stop_id"]): s for s in self._stops if "stop_id" in s}
        for sid in stops_by_id:
            serving = get_routes_serving_stop(
                sid, stop_sequence_map, trips_by_id, selected_route_ids
            )
            if serving:
                served_stop_ids.add(sid)

        served_stops = [
            s for s in self._stops if int(s.get("stop_id", 0)) in served_stop_ids
        ]
        served_stops.sort(key=lambda s: s.get("stop_name", ""))

        current_stops = self.config_entry.data.get(CONF_SELECTED_STOPS, [])

        stop_options = [
            SelectOptionDict(
                value=str(s["stop_id"]),
                label=s.get("stop_name", f"Stop {s['stop_id']}"),
            )
            for s in served_stops
        ]

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_SELECTED_STOPS, default=current_stops
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=stop_options,
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="select_stops",
            data_schema=data_schema,
        )
