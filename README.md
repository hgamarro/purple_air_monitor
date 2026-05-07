# purple_air_monitor

## Sensor configuration

The app can read PurpleAir sensor IDs from a published Google Sheet CSV URL.
If that URL is not configured, unavailable, or invalid, the app falls back to
the checked-in `sensors.csv` backup.

### Google Sheet setup

Create a Google Sheet with a `sensor_index` column:

```csv
name,sensor_index,location,notes
Van Buskirk Community Center,270898,South Stockton,
Example Monitor,279253,Little Manila,
```

Only `sensor_index` is required. `name`, `location`, and `notes` are optional
fields for the team to organize the sensor list. If `name` is filled in, the
app uses it as the display name; otherwise it uses the name from PurpleAir.

Publish the sheet as CSV, then add the published CSV URL to Streamlit secrets:

```toml
sensor_csv_url = "https://docs.google.com/spreadsheets/d/e/.../pub?output=csv"
```

The sheet should only contain public sensor IDs. Do not publish private sensor
read keys in a public CSV.

### Local backup

To add or remove monitored sensors, edit `sensors.csv` and keep one sensor
per row:

```csv
name,sensor_index,location,notes
Van Buskirk Community Center,270898,South Stockton,
Example Monitor,279253,Little Manila,
```

The PurpleAir API key is still read from Streamlit secrets using `textkey`.
