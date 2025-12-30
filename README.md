# Southpool Integration for Home Assistant

A Home Assistant custom integration that provides real-time electricity market data from the Southpool energy exchange for Hungary, Serbia, and Slovenia.

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

---

*This integration is not affiliated with Southpool or HUPX. All data is provided by their [public APIs](https://labs.hupx.hu/). Users are responsible for compliance with data provider terms.*

[hacs]: https://hacs.xyz
[hacs_shield]: https://img.shields.io/badge/HACS-Custom-blue.svg
[releases-shield]: https://img.shields.io/github/release/MysteriousWolf/southpool-hacs.svg
[releases]: https://github.com/MysteriousWolf/southpool-hacs/releases
[commits-shield]: https://img.shields.io/github/commit-activity/y/MysteriousWolf/southpool-hacs.svg
[commits]: https://github.com/MysteriousWolf/southpool-hacs/commits/main