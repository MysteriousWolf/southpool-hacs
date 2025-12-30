# Southpool Integration for Home Assistant

A Home Assistant custom integration that provides real-time electricity market data from the Southpool energy exchange. Monitor current and forecasted electricity prices for Hungary, Serbia, and Slovenia power markets.

[![HACS Custom][hacs_shield]][hacs]
[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]

## Features

- **Real-time Price Monitoring**: Track current electricity prices in EUR/MWh
- **48-Hour Forecast**: Get today's and tomorrow's price data
- **Multi-Region Support**: Support for Hungary (HU), Serbia (RS), and Slovenia (SI)
- **15-Minute Intervals**: Detailed quarter-hour price breakdowns (96 periods per day)
- **Trading Volume Data**: Monitor traded volumes alongside prices
- **Smart Scheduling**: Data refreshes precisely at quarter-hour marks (00, 15, 30, 45 minutes past each hour)
- **Timezone Consistency**: All timestamps are handled in Central European Time (CET/UTC+1)
- **Efficient Updates**: Separate scheduling for sensor updates (every 15 mins) and API fetches (hourly)

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
| `sensor.southpool_{region}_timestamp` | Current data timestamp (in CET) | - |
| `sensor.southpool_{region}_quarter_hour` | Current quarter-hour period (1-96) | - |
| `sensor.southpool_{region}_price` | Current electricity price | EUR/MWh |
| `sensor.southpool_{region}_traded_volume` | Current traded volume | MW |
| `sensor.southpool_{region}_baseload_price` | Baseload electricity price | EUR/MWh |
| `sensor.southpool_{region}_status` | Data status (final/preliminary/deleted) | - |

*Note: Replace `{region}` with your selected region code (HU, RS, or SI)*

## Forecast Data

Each sensor includes a 48-hour forecast as state attributes:

- **`forecast_48h`**: Array of forecast values for the next 48 hours (192 quarter-hour periods)
- **`forecast_count`**: Number of forecast periods available

### Accessing Forecast Data

You can access forecast data in automations and templates:

```yaml
# Template sensor for next hour average price
template:
  - sensor:
      - name: "Next Hour Average Price"
        unit_of_measurement: "EUR/MWh"
        state: >
          {% set forecast = state_attr('sensor.southpool_hu_price', 'forecast_48h') %}
          {% if forecast and forecast|length >= 4 %}
            {{ (forecast[:4] | map('float') | sum / 4) | round(2) }}
          {% else %}
            unavailable
          {% endif %}
```

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
        entity_id: sensor.southpool_hu_price  # Replace HU with your region
        above: 100
    action:
      - service: notify.mobile_app
        data:
          message: "Electricity price is high: {{ states('sensor.southpool_hu_price') }} EUR/MWh"

  - alias: "Start Heavy Load During Low Prices"
    trigger:
      - platform: numeric_state
        entity_id: sensor.southpool_hu_price
        below: 50
    condition:
      - condition: time
        after: "06:00:00"
        before: "22:00:00"
    action:
      - service: switch.turn_on
        entity_id: switch.heavy_appliance
      - service: notify.mobile_app
        data:
          message: "Low electricity price: {{ states('sensor.southpool_hu_price') }} EUR/MWh - Starting heavy appliances"
```

## Data Source

This integration fetches data from the [Hungarian Power Exchange (HUPX) Labs API](https://labs.hupx.hu/), which provides official Southpool market data for the supported regions.

## Timezone Information

The integration uses **Central European Time (CET)** consistently:
- All timestamps are in CET (UTC+1) regardless of your system timezone
- Data updates occur at exact quarter-hour marks in CET (00, 15, 30, 45 minutes)
- API data from Southpool is provided in CET timezone
- This ensures consistent timing across different Home Assistant deployments

## Troubleshooting

### No Data Available

- Check your internet connection
- Verify the selected region is correct
- Check the Home Assistant logs for API errors

### Outdated Data

- The integration updates at quarter-hour intervals (00, 15, 30, 45 minutes past each hour)
- Market data may have delays during maintenance periods
- Check the timestamp sensor to see when data was last updated

### Timezone Issues

- If you experience timing mismatches, verify your system's timezone configuration
- The integration always uses CET (UTC+1) for consistency with Southpool API data
- All quarter-hour calculations are based on CET time

## Technical Notes

### Architecture

The integration uses a dual-scheduling approach for optimal performance:

- **Quarter-hour Updates**: Sensor data refreshes precisely at quarter-hour marks (00, 15, 30, 45 minutes)
- **Hourly API Fetches**: Fresh data is fetched from the Southpool API once per hour
- **Cached Data Processing**: Between API calls, sensors are updated using cached data with recalculated timestamps

### Timezone Handling

- **Consistent CET Usage**: All internal calculations use Central European Time (UTC+1)
- **API Compatibility**: Matches the timezone of Southpool API data
- **System Independence**: Works correctly regardless of Home Assistant system timezone
- **DST Considerations**: Currently uses literal CET (UTC+1) year-round for predictability

### Data Structure

- **Quarter Hours**: Numbered 1-96 representing 15-minute intervals throughout the day
- **Timestamps**: ISO 8601 format with CET timezone offset (+01:00)
- **Forecast Arrays**: 192 periods representing the next 48 hours of quarter-hour data

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
