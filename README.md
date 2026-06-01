# Southpool Integration for Home Assistant

A Home Assistant custom integration that provides real-time electricity market data from the Southpool energy exchange for Hungary, Serbia, and Slovenia.

![BSP SouthPool logo](https://raw.githubusercontent.com/MysteriousWolf/southpool-hacs/main/resources/logo.svg)

[![HACS Custom][hacs_shield]][hacs]
[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]

## Features

- Real-time electricity prices in EUR/MWh
- 48-hour price forecasts
- Multiple regions: Hungary (HU), Serbia (RS), Slovenia (SI)
- Both 15-minute and hourly data intervals
- Trading volume monitoring
- Central European Time (CET/UTC+1)

## Installation

### HACS (Recommended)

1. HACS → Integrations → ⋮ → Custom repositories
2. Add: `https://github.com/MysteriousWolf/southpool-hacs`
3. Download "Southpool Energy Exchange Integration"
4. Restart Home Assistant

### Manual

Copy `custom_components/southpool` to your HA `custom_components` directory and restart.

## Setup

**Settings** → **Devices & Services** → **Add Integration** → Search "Southpool" → Select region

## Sensors

Each region provides both 15-minute and hourly sensors:

| Data Type | 15-minute Sensor | Hourly Sensor | Unit |
|-----------|------------------|---------------|------|
| Price | `southpool_{region}_price` | `southpool_{region}_hourly_price` | EUR/MWh |
| Period | `southpool_{region}_quarter_hour` | `southpool_{region}_hourly_hour` | 1-96 / 1-24 |
| Volume | `southpool_{region}_traded_volume` | `southpool_{region}_hourly_traded_volume` | MW |
| Timestamp | `southpool_{region}_timestamp` | `southpool_{region}_hourly_timestamp` | CET |
| Baseload | `southpool_{region}_baseload_price` | `southpool_{region}_hourly_baseload_price` | EUR/MWh |
| Status | `southpool_{region}_status` | `southpool_{region}_hourly_status` | - |

*Replace `{region}` with: `hu`, `rs`, or `si`*

## Forecast Data

All price sensors include 48-hour forecasts in their `forecast_48h` attribute:
- 15-minute sensors: 192 periods (15min × 96)
- Hourly sensors: 48 periods (1h × 48)

## Updates

- **Sensors**: Every 15 minutes (00, 15, 30, 45)
- **API Data**: Every hour

## Support

- [Issues](https://github.com/MysteriousWolf/southpool-hacs/issues)
- [Discussions](https://github.com/MysteriousWolf/southpool-hacs/discussions)

## License

MIT License - See [LICENSE](LICENSE) file.

## Data provider and terms

The data displayed by this integration is sourced from the public APIs of:

- **BSP Energy Exchange LLC** (Slovenia) — Dunajska 156, 1000 Ljubljana, Slovenija
- **SEEPEX** (Serbia)
- **HUPX Hungarian Power Exchange Limited by Shares** (Hungary)

The brand assets shown in this repository are the property of their respective
rights holders and are used solely to identify the data source. See
[`resources/README.md`](resources/README.md) for full attribution and disclaimers.

The full Terms of Use of the source website (`labs.hupx.hu`) are published by
HUPX at <https://labs.hupx.hu/about_us/website_terms>. Use of the integration
is subject to those terms; in particular, the website and its data are
provided for personal and non-commercial use only.

This project is an independent, unofficial integration and is **not**
affiliated with, endorsed by, or sponsored by BSP Energy Exchange LLC,
SEEPEX, or HUPX.

---

[hacs]: https://hacs.xyz
[hacs_shield]: https://img.shields.io/badge/HACS-Custom-blue.svg
[releases-shield]: https://img.shields.io/github/release/MysteriousWolf/southpool-hacs.svg
[releases]: https://github.com/MysteriousWolf/southpool-hacs/releases
[commits-shield]: https://img.shields.io/github/commit-activity/y/MysteriousWolf/southpool-hacs.svg
[commits]: https://github.com/MysteriousWolf/southpool-hacs/commits/main
