"""Constante pentru integrarea Tranzy SCTP Iași."""

DOMAIN = "tranzy"

# Versiunea config entry (pentru migrare)
CONFIG_VERSION = 1

# =========================================================================
# Adresa de bază API
# =========================================================================
API_BASE_URL = "https://api.tranzy.ai/v1/opendata"

# =========================================================================
# Endpoint-uri API — date statice
# =========================================================================
API_PATH_AGENCY = "/agency"
API_PATH_ROUTES = "/routes"
API_PATH_STOPS = "/stops"
API_PATH_TRIPS = "/trips"
API_PATH_STOP_TIMES = "/stop_times"

# =========================================================================
# Endpoint-uri API — date real-time
# =========================================================================
API_PATH_VEHICLES = "/vehicles"

# =========================================================================
# Agenție implicită
# =========================================================================
DEFAULT_AGENCY_ID = "1"  # SCTP Iași

# =========================================================================
# Intervale de actualizare (secunde)
# =========================================================================
STATIC_UPDATE_INTERVAL = 43200  # 12 ore — rute, stații, curse, opriri
VEHICLE_UPDATE_INTERVAL = 30    # 30 secunde — poziții vehicule

# =========================================================================
# Chei de configurare
# =========================================================================
CONF_API_KEY = "api_key"
CONF_AGENCY_ID = "agency_id"
CONF_SELECTED_ROUTES = "selected_routes"
CONF_SELECTED_STOPS = "selected_stops"

# =========================================================================
# Parametri calcul ETA
# =========================================================================
EARTH_RADIUS_M = 6_371_000       # Raza Pământului în metri (Haversine)
STOP_PROXIMITY_THRESHOLD_M = 50  # Vehicul considerat "la stație" dacă < 50m
STALE_VEHICLE_THRESHOLD_S = 300  # Ignoră vehicule cu date > 5 minute
DEFAULT_SPEED_MPS = 5.0          # Viteză implicită ~18 km/h (dacă speed=null)

# =========================================================================
# Tipuri de rute GTFS
# =========================================================================
ROUTE_TYPE_TRAM = 0
ROUTE_TYPE_BUS = 3

# =========================================================================
# Atribuire
# =========================================================================
ATTRIBUTION = "Date furnizate de Tranzy.ai OpenData — SCTP Iași"
