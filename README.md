# purple_air_monitor

## Sensor configuration

The app reads PurpleAir sensor IDs from `sensors.csv` instead of hardcoding
them in `streamlit_app.py`.

To add or remove monitored sensors, edit `sensors.csv` and keep one sensor
index per row under the `sensor_index` column:

```csv
sensor_index
270898
279253
```

The PurpleAir API key is still read from Streamlit secrets using `textkey`.
