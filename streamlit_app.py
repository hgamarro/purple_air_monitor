import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
from datetime import datetime, timezone
from pathlib import Path

# streamlit run streamlit_app.py    
# --- App Configuration ---
st.set_page_config(
    page_title="PurpleAir Sensor Status",
    page_icon="💨",
    layout="wide"
)

# --- App Title and Description ---
st.title('💨 PurpleAir Sensor Status Checker')
st.markdown("""
This app checks the status of PurpleAir sensors. Click “Refresh Status”.
The app will display each sensor’s operational status on a map and in a detailed table.

- **Green:** ✅ Online and reporting good data.
- **Yellow:** ⚠️ Online, but with low data confidence.
- **Red:** ❌ Offline or has an error.
""")

# --- Sensor and API Configuration ---
SENSOR_CSV_PATH = Path("sensors.csv")
SENSOR_CSV_URL_SECRET = "sensor_csv_url"
API_BASE_URL = "https://api.purpleair.com/v1/sensors/"
FIELDS_TO_REQUEST = (
    "name,model,hardware,last_seen,confidence,rssi,uptime,"
    "latitude,longitude,pm2.5,pm2.5_60minute,temperature_a"
)

# --- Status thresholds and colors ---
STALE_THRESHOLD_SECONDS = 600   # 10 minutes
LOW_CONFIDENCE_THRESHOLD = 75   # percent
STATUS_COLORS = {
    'online':         [0, 255, 0, 160],
    'low_confidence': [255, 255, 0, 160],
    'offline':        [255, 0, 0, 160],
}

def extract_sensor_registry(sensors_df, source_name):
    """Validate a sensor table and return community-maintained sensor metadata."""
    if "sensor_index" not in sensors_df.columns:
        st.error(f"{source_name} must include a 'sensor_index' column.")
        return pd.DataFrame()

    sensors_df = sensors_df.copy()
    sensors_df["sensor_index"] = pd.to_numeric(
        sensors_df["sensor_index"],
        errors="coerce"
    )
    sensors_df = sensors_df.dropna(subset=["sensor_index"])
    sensors_df["sensor_index"] = sensors_df["sensor_index"].astype(int)
    sensors_df = sensors_df.drop_duplicates(subset=["sensor_index"])

    if "name" in sensors_df.columns:
        sensors_df = sensors_df.rename(columns={"name": "community_name"})

    optional_columns = ["community_name", "location", "notes"]
    for column in optional_columns:
        if column not in sensors_df.columns:
            sensors_df[column] = ""

    registry_columns = ["sensor_index", *optional_columns]
    sensor_registry = sensors_df[registry_columns]

    if sensor_registry.empty:
        st.error(f"{source_name} does not contain any valid sensor indices.")

    return sensor_registry

def load_local_sensor_registry(csv_path=SENSOR_CSV_PATH):
    """Load the checked-in CSV backup."""
    if not csv_path.exists():
        st.error(f"Missing backup sensor configuration file: {csv_path}")
        return pd.DataFrame(), "missing local backup"

    try:
        sensors_df = pd.read_csv(csv_path)
    except Exception as exc:
        st.error(f"Could not read backup sensor CSV {csv_path}: {exc}")
        return pd.DataFrame(), "unreadable local backup"

    return extract_sensor_registry(sensors_df, str(csv_path)), f"local backup: {csv_path}"

def load_sensor_registry():
    """Load sensors from Google Sheets CSV URL, falling back to local CSV."""
    sensor_csv_url = st.secrets.get(SENSOR_CSV_URL_SECRET)
    if sensor_csv_url:
        try:
            sensors_df = pd.read_csv(sensor_csv_url)
            sensor_registry = extract_sensor_registry(
                sensors_df,
                "Google Sheet sensor CSV"
            )
            if not sensor_registry.empty:
                return sensor_registry, "Google Sheet"
        except Exception as exc:
            st.warning(
                "Could not load Google Sheet sensor CSV. "
                f"Using local backup instead. Error: {exc}"
            )

    return load_local_sensor_registry()

def merge_sensor_metadata(sensor_data, sensor_row):
    """Attach community-maintained sheet fields to PurpleAir API results."""
    for column in ["community_name", "location", "notes"]:
        value = sensor_row.get(column, "")
        if pd.notna(value) and str(value).strip():
            sensor_data[column] = str(value).strip()

    api_name = sensor_data.get("name", "")
    community_name = sensor_data.get("community_name", "")
    sensor_data["display_name"] = community_name or api_name
    return sensor_data

def get_map_dataframe(df):
    """Return only rows that have usable map coordinates."""
    location_columns = ["latitude", "longitude"]
    if df.empty or not set(location_columns).issubset(df.columns):
        return pd.DataFrame()

    return df.dropna(subset=location_columns).copy()

def get_error_sensor_record(sensor_index, status):
    """Return a complete row shape for sensors that fail to fetch."""
    return {
        'sensor_index': sensor_index,
        'status': status,
        'name': 'N/A',
        'last_seen': None,
        'latitude': None,
        'longitude': None,
        'color': STATUS_COLORS['offline'],
    }

def get_sensor_data(api_key, sensor_index):
    """Fetch a single sensor’s data and assign status & color."""
    sensor_index = int(sensor_index)
    headers = {"X-API-Key": api_key}
    url = f"{API_BASE_URL}{sensor_index}?fields={FIELDS_TO_REQUEST}"
    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json().get('sensor', {})
        data['sensor_index'] = sensor_index

        last_seen = data.get('last_seen', 0)
        age_sec   = datetime.now(timezone.utc).timestamp() - last_seen
        conf      = data.get('confidence', 0)

        if age_sec > STALE_THRESHOLD_SECONDS:
            hrs = int(age_sec // 3600)
            data['status'] = f'❌ Offline ({hrs} hr ago)'
            data['color']  = STATUS_COLORS['offline']
        elif conf < LOW_CONFIDENCE_THRESHOLD:
            data['status'] = f'⚠️ Low Confidence ({conf}%)'
            data['color']  = STATUS_COLORS['low_confidence']
        else:
            data['status'] = '✅ Online'
            data['color']  = STATUS_COLORS['online']

        return data

    except requests.exceptions.HTTPError as e:
        code = e.response.status_code
        msg  = f"❌ HTTP {code}"
        if code == 403: msg += " (Invalid API Key?)"
        if code == 404: msg += " (Not Found)"
        return get_error_sensor_record(sensor_index, msg)
    except requests.exceptions.RequestException:
        return get_error_sensor_record(sensor_index, '❌ Request Error')

# --- Default map view ---
DEFAULT_VIEW = pdk.ViewState(
    latitude=37.9577,
    longitude=-121.2908,
    zoom=10,
    pitch=0
)

# --- Session state init ---
if 'df'        not in st.session_state: st.session_state.df        = pd.DataFrame()
if 'df_map'    not in st.session_state: st.session_state.df_map    = pd.DataFrame()
if 'view_state' not in st.session_state: st.session_state.view_state = DEFAULT_VIEW
if 'sensor_source' not in st.session_state: st.session_state.sensor_source = "not loaded yet"
if 'sensor_count'  not in st.session_state: st.session_state.sensor_count  = 0

# --- Callbacks ---
def do_refresh():
    """Fetch all sensor data (with spinner) and store in session state."""
    with st.spinner("Fetching sensor data... Please wait."):
        api_key = st.secrets["textkey"]
        sensor_registry, sensor_source = load_sensor_registry()
        st.session_state.sensor_source = sensor_source
        st.session_state.sensor_count = len(sensor_registry)
        if sensor_registry.empty:
            st.session_state.df = pd.DataFrame()
            st.session_state.df_map = pd.DataFrame()
            return

        records = [
            merge_sensor_metadata(
                get_sensor_data(api_key, int(row["sensor_index"])),
                row
            )
            for _, row in sensor_registry.iterrows()
        ]
        df = pd.DataFrame(records)
        st.session_state.df     = df
        st.session_state.df_map = get_map_dataframe(df)
    st.success("Finished fetching data!")

def reset_view():
    """Return map to default camera."""
    st.session_state.view_state = DEFAULT_VIEW


col1, col2 = st.columns(2)
with col1:
    st.button("🔄 Refresh Status", on_click=do_refresh)
with col2:
    st.button("🔄 Reset Map View", on_click=reset_view)

st.caption(
    f"Sensor list source: {st.session_state.sensor_source} "
    f"({st.session_state.sensor_count} sensors)"
)

# --- Display Table ---
df = st.session_state.df
if not df.empty:
    now_ts = datetime.now(timezone.utc).timestamp()
    if "last_seen" in df.columns:
        df['minutes_since_seen'] = df['last_seen'].apply(
            lambda x: (now_ts - x)/60 if pd.notna(x) else None
        )
    else:
        df['minutes_since_seen'] = None

    # 1. Add a priority for sorting: red (❌)=0, yellow (⚠️)=1, green (✅)=2
    def status_priority(s):
        s = str(s)
        if s.startswith('❌'): return 0
        if s.startswith('⚠️'): return 1
        if s.startswith('✅'): return 2
        return 3

    df['__priority'] = df['status'].apply(status_priority)

    # 2. Sort by that priority so red come first
    df = df.sort_values('__priority').drop(columns='__priority')

    # 3. Rename for display
    display_cols = {
        'display_name':     'Name',
        'sensor_index':     'Sensor ID',
        'status':           'Status',
        'name':             'PurpleAir Name',
        'location':         'Location',
        'notes':            'Notes',
        'minutes_since_seen':'Mins Ago',
        'confidence':       'Confidence (%)',
        'rssi':             'WiFi (RSSI)',
        'uptime':           'Uptime (min)',
        'pm2.5':            'PM2.5',
        'pm2.5_60minute':   'PM2.5 (60m avg)',
        'temperature_a':    'Temp (°F)',
        'model':            'Model',
        'latitude':         'Lat',
        'longitude':        'Lon'
    }
    df_disp = df.rename(columns=display_cols)

    # 4. Keep your original column order
    order = [c for c in [
        'Name', 'Sensor ID', 'Status', 'Location', 'Notes', 'Mins Ago', 'Confidence (%)',
        'WiFi (RSSI)', 'Uptime (min)', 'PM2.5', 'PM2.5 (60m avg)',
        'Temp (°F)', 'PurpleAir Name', 'Model', 'Lat', 'Lon'
    ] if c in df_disp.columns]

    # 5. Display the sorted table
    st.subheader("Sensor Status Details")
    st.dataframe(
        df_disp[order],
        width="stretch",
        column_config={
            "Mins Ago":     st.column_config.NumberColumn(format="%.1f"),
            "WiFi (RSSI)":  st.column_config.NumberColumn(format="%d dBm"),
        }
    )
# --- Display Map ---
df_map = st.session_state.df_map
if not df_map.empty:
    st.subheader("Sensor Location and Status Map")
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_map,
        get_position=["longitude","latitude"],
        get_color="color",
        get_radius=200,
        pickable=True,
        auto_highlight=True,
    )
    tooltip = {
        "html": "<b>{display_name}</b><br/>ID: {sensor_index}<br/>Status: {status}",
        "style": {"backgroundColor":"steelblue","color":"white"}
    }
    deck = pdk.Deck(
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        initial_view_state=st.session_state.view_state,
        layers=[layer],
        tooltip=tooltip
    )
    st.pydeck_chart(deck, width="stretch")

elif df_map.empty and not df.empty:
    st.warning("No sensors with location data found.")

with st.expander("Show Raw Data"):
    st.write(st.session_state.df.to_dict('records'))
