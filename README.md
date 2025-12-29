# Southpool Integration for Home Assistant

A Home Assistant custom integration that provides real-time electricity market data from the Southpool energy exchange. Monitor current and forecasted electricity prices for Hungary, Serbia, and Slovenia power markets.

[![HACS Custom][hacs_shield]][hacs]
[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]

## Features

- **Real-time Price Monitoring**: Track current electricity prices in EUR/MWh
- **48-Hour Forecast**: Get today's and tomorrow's price data
- **Multi-Region Support**: Support for Hungary (HU), Serbia (RS), and Slovenia (SI)
- **15-Minute Intervals**: Detailed quarter-hour price breakdowns
- **Trading Volume Data**: Monitor traded volumes alongside prices
- **Automated Updates**: Data refreshes every 15 minutes

## Installation

### HACS (Recommended)

This integration is available in HACS (Home Assistant Community Store).

1. Open HACS in your Home Assistant instance
2. Go to "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL: `https://github.com/MysteriousWolf/southpool-hacs`
6. Select category: "Integration"
7. Click "ADD"
8. Find "Southpool Energy Exchange Integration" and click "Download"
9. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/southpool` directory to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Add the integration through the UI

## Configuration

1. Go to **Settings** > **Devices & Services**
2. Click **Add Integration**
3. Search for "Southpool"
4. Select your region:
   - **Hungary (HU)**
   - **Serbia (RS)**  
   - **Slovenia (SI)**
5. Click **Submit**

## Sensors

The integration provides the following sensors for your selected region:

| Sensor | Description | Unit |
|--------|-------------|------|
| `sensor.southpool_timestamp` | Current data timestamp | - |
| `sensor.southpool_quarter_hour` | Current quarter-hour period | - |
| `sensor.southpool_price` | Current electricity price | EUR/MWh |
| `sensor.southpool_traded_volume` | Current traded volume | MW |

## Usage Examples

### Energy Dashboard

Add the price sensor to your Energy Dashboard to track electricity costs over time.

### Automation Example

Create automations based on electricity prices:

```yaml
automation:
  - alias: "High Electricity Price Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.southpool_price
        above: 100
    action:
      - service: notify.mobile_app
        data:
          message: "Electricity price is high: {{ states('sensor.southpool_price') }} EUR/MWh"
```

## Data Source

This integration fetches data from the [Hungarian Power Exchange (HUPX) Labs API](https://labs.hupx.hu/), which provides official Southpool market data for the supported regions.

## Troubleshooting

### No Data Available

- Check your internet connection
- Verify the selected region is correct
- Check the Home Assistant logs for API errors

### Outdated Data

- The integration updates every 15 minutes
- Market data may have delays during maintenance periods
- Check the timestamp sensor to see when data was last updated

## Support

- [Report Issues](https://github.com/MysteriousWolf/southpool-hacs/issues)
- [Feature Requests](https://github.com/MysteriousWolf/southpool-hacs/discussions)

## Contributing

Contributions are welcome! Please read our [contributing guidelines](CONTRIBUTING.md) before submitting pull requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

*This integration is not affiliated with Southpool or HUPX. All data is provided by their public APIs.*

[hacs]: https://hacs.xyz
[hacs_shield]: https://img.shields.io/badge/HACS-Custom-blue.svg
[releases-shield]: https://img.shields.io/github/release/MysteriousWolf/southpool-hacs.svg
[releases]: https://github.com/MysteriousWolf/southpool-hacs/releases
[commits-shield]: https://img.shields.io/github/commit-activity/y/MysteriousWolf/southpool-hacs.svg
[commits]: https://github.com/MysteriousWolf/southpool-hacs/commits/main
