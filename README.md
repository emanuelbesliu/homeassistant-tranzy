# Tranzy SCTP Iași — Home Assistant Integration

[![HACS Validation](https://github.com/emanuelbesliu/homeassistant-tranzy/actions/workflows/validate.yml/badge.svg)](https://github.com/emanuelbesliu/homeassistant-tranzy/actions/workflows/validate.yml)
[![GitHub Release](https://img.shields.io/github/v/release/emanuelbesliu/homeassistant-tranzy)](https://github.com/emanuelbesliu/homeassistant-tranzy/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1+-blue.svg)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Custom Home Assistant integration for **real-time public transport tracking** in **Iași, Romania** (SCTP Iași) via the [Tranzy.ai OpenData API](https://tranzy.ai).

Track active vehicles on your favorite tram and bus routes, and get estimated arrival times (ETAs) at your favorite stops — all updated every 30 seconds.

---

## Features

### Route Monitoring

One sensor per selected route showing the number of active vehicles currently on that route.

| Sensor | State | Attributes |
|--------|-------|------------|
| `Tram 3 — Tg. Cucu - Tudor V. Active` | `4` (vehicles) | Vehicle list with label, speed, GPS coordinates |
| `Bus 101 — CUG - Copou Active` | `2` (vehicles) | Vehicle list with label, speed, GPS coordinates |

### Stop ETA

One sensor per stop × route combination, showing when the next vehicle will arrive.

| Sensor | State | Attributes |
|--------|-------|------------|
| `Tram 3 → Piața Unirii` | `4.2` (min) | Next vehicle label, distance, speed, headsign |
| `Bus 101 → Gara` | `12.8` (min) | Next vehicle label, distance, speed, headsign |

### Key Capabilities

- **Real-time vehicle tracking** — positions update every 30 seconds
- **Calculated ETAs** — based on GPS distance, vehicle speed, and stop sequence ordering
- **Multi-route & multi-stop** — monitor as many routes and stops as you want
- **Two-tier data refresh** — static data (routes, stops, trips) refreshes every 12 hours; vehicle positions every 30 seconds
- **Tram + Bus support** — SCTP Iași trams (routes 1–8) and buses (100+)
- **Config flow UI** — 3-step setup: API key → select routes → select stops
- **Options flow** — change your monitored routes and stops at any time
- **Reauth flow** — seamless re-authentication if your API key expires

---

## Installation

### HACS (Recommended)

1. Open **HACS** in Home Assistant
2. Click **⋮** → **Custom repositories**
3. Add URL: `https://github.com/emanuelbesliu/homeassistant-tranzy`
4. Category: **Integration**
5. Search for "**Tranzy**" and install
6. Restart Home Assistant

### Manual

1. Download the [latest release](https://github.com/emanuelbesliu/homeassistant-tranzy/releases)
2. Copy `custom_components/tranzy/` to your `config/custom_components/` directory
3. Restart Home Assistant

---

## Configuration

### Prerequisites

You need a **Tranzy.ai OpenData API key**. Get one at [tranzy.ai](https://tranzy.ai).

### Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for "**Tranzy SCTP Iași**"
3. **Step 1**: Enter your API key
4. **Step 2**: Select which routes to monitor (trams listed first, then buses)
5. **Step 3**: Select your favorite stops (only stops served by the selected routes are shown)

### Changing Routes & Stops

Go to **Settings → Devices & Services → Tranzy SCTP Iași → Configure** to change your monitored routes and favorite stops at any time.

---

## Entities

### Route Vehicle Count Sensor

| Property | Value |
|----------|-------|
| State | Number of active vehicles on the route |
| Unit | — |
| Icon | `mdi:tram` (trams) / `mdi:bus` (buses) |
| Update interval | 30 seconds |

**Attributes:**

| Attribute | Description |
|-----------|-------------|
| `route_id` | Numeric route identifier |
| `route_short_name` | Route number (e.g., "3", "101") |
| `route_long_name` | Full route name |
| `route_type` | `tram` or `bus` |
| `vehicles` | List of active vehicles with `label`, `speed_kmh`, `latitude`, `longitude`, `trip_id` |

### Stop ETA Sensor

| Property | Value |
|----------|-------|
| State | ETA in minutes of the nearest approaching vehicle (or `unknown` if none) |
| Unit | `min` |
| Icon | `mdi:clock-outline` |
| Update interval | 30 seconds |

**Attributes:**

| Attribute | Description |
|-----------|-------------|
| `stop_id` | Stop identifier |
| `stop_name` | Human-readable stop name |
| `stop_lat` / `stop_lon` | Stop GPS coordinates |
| `route_id` | Route this ETA is calculated for |
| `route_short_name` | Route number |
| `vehicles_approaching` | Count of vehicles heading toward this stop |
| `next_vehicle_label` | Label/number of the nearest vehicle |
| `next_vehicle_distance_m` | Distance in meters |
| `next_vehicle_speed_kmh` | Speed in km/h |
| `next_vehicle_headsign` | Trip destination |
| `all_approaching` | List of all approaching vehicles (when >1) |

---

## How ETAs Are Calculated

The Tranzy API does not provide scheduled arrival times. ETAs are **calculated in real-time** using:

1. **GPS position** — vehicle coordinates vs. stop coordinates (Haversine formula)
2. **Vehicle speed** — reported in m/s by the API, converted to km/h
3. **Stop sequence ordering** — determines if a vehicle is *before* or *after* a stop on its trip
4. **Filtering** — only vehicles that are *approaching* the stop (not already past it) are included

Vehicles with stale data (>5 minutes old), no GPS, or zero speed use a default speed of ~18 km/h.

---

## Automation Examples

### Notify When Bus Is 5 Minutes Away

```yaml
alias: "Bus 101 Aproape de Stație"
triggers:
  - entity_id: sensor.tranzy_bus_101_piata_unirii
    below: 5
    trigger: numeric_state
actions:
  - action: notify.mobile_app_phone
    data:
      title: "Bus 101 vine!"
      message: >-
        Autobuzul 101 ajunge la Piața Unirii în
        {{ states('sensor.tranzy_bus_101_piata_unirii') }} minute.
```

### Dashboard Card — Next Arrivals

```yaml
type: entities
title: Stația Piața Unirii
entities:
  - entity: sensor.tranzy_tram_3_piata_unirii
    name: Tram 3
    icon: mdi:tram
  - entity: sensor.tranzy_bus_101_piata_unirii
    name: Bus 101
    icon: mdi:bus
```

### Dashboard Card — Route Map Data

```yaml
type: map
entities:
  - entity: sensor.tranzy_tram_3_active
dark_mode: true
```

---

## Architecture

```
custom_components/tranzy/
├── __init__.py          # Entry point, coordinators setup, platform forwarding
├── api.py               # Async aiohttp client for Tranzy.ai OpenData
├── config_flow.py       # 3-step config flow + reauth + options flow
├── const.py             # Constants, API endpoints, config keys
├── coordinator.py       # TranzyStaticCoordinator (12h) + TranzyVehicleCoordinator (30s)
├── helpers.py           # Haversine, ETA calculation, vehicle filtering
├── manifest.json        # Integration metadata
├── sensor.py            # Route vehicle count + Stop ETA sensors
├── strings.json         # Translation keys
└── translations/
    ├── en.json           # English
    └── ro.json           # Romanian (Română)
```

### Data Flow

```
Tranzy.ai API
     │
     ├── /routes, /stops, /trips, /stop_times  →  TranzyStaticCoordinator (12h)
     │                                              ├── routes_by_id
     │                                              ├── stops_by_id
     │                                              ├── trips_by_id
     │                                              └── stop_sequence_map
     │
     └── /vehicles  →  TranzyVehicleCoordinator (30s)
                         ├── active_vehicles (filtered: GPS + fresh)
                         ├── vehicles_by_route
                         └── stop_etas (calculated ETAs per stop×route)
                              │
                              └──→ Sensor Entities
```

---

## API Usage

This integration uses the [Tranzy.ai OpenData API](https://tranzy.ai) with these endpoints:

| Endpoint | Refresh | Purpose |
|----------|---------|---------|
| `GET /routes` | 12h | Route definitions |
| `GET /stops` | 12h | Stop names + GPS |
| `GET /trips` | 12h | Trip → route mapping |
| `GET /stop_times` | 12h | Stop sequence per trip |
| `GET /vehicles` | 30s | Real-time vehicle positions |

Estimated API usage: ~2,880 vehicle calls/day + ~4 static calls/day ≈ **~2,884 calls/day** (well within the ~5,000/day limit).

---

## Troubleshooting

### Sensors showing "Unknown"

- During off-hours (late night), no vehicles may be active — the route sensor shows `0` and ETA sensors show `unknown`
- Verify your API key is valid at [tranzy.ai](https://tranzy.ai)
- Check HA logs: **Settings → System → Logs**, filter for "tranzy"

### ETAs seem inaccurate

- ETAs are straight-line distance estimates, not route-following — actual arrival may differ
- Low vehicle speed or GPS jitter can affect calculations
- Vehicles with `speed=0` use a default ~18 km/h estimate

### No stops shown during setup

- Only stops served by your selected routes are displayed
- If a route has no trips in the current schedule, its stops won't appear

### Debug logging

Add to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.tranzy: debug
```

---

## Contributing

Contributions welcome! Open an issue or pull request on GitHub.

1. Fork the repository
2. Create a branch: `git checkout -b feature/my-feature`
3. Commit: `git commit -m 'Add my feature'`
4. Push: `git push origin feature/my-feature`
5. Open a Pull Request

---

## License

MIT License — Copyright (c) 2026 Emanuel Besliu. See [LICENSE](LICENSE) for details.

---

## Disclaimer

This integration uses data from the Tranzy.ai OpenData API for SCTP Iași. It is not officially affiliated with Tranzy.ai or SCTP Iași. Data accuracy depends on the API provider.

---

## Support

- **Issues**: [GitHub Issues](https://github.com/emanuelbesliu/homeassistant-tranzy/issues)
- **Discussions**: [GitHub Discussions](https://github.com/emanuelbesliu/homeassistant-tranzy/discussions)

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://buymeacoffee.com/emanuelbesliu)

---

*Developed by Emanuel Besliu ([@emanuelbesliu](https://github.com/emanuelbesliu))*
