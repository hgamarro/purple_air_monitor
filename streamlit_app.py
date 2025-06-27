import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
from datetime import datetime, timezone

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
SENSOR_INDICES = [
    270898, 279253, 279251, 133435, 155503, 155501, 155521, 155533,
    155537, 155567, 155569, 155591, 155595, 155597, 155601, 155607,
    155605, 155613, 155629, 155639, 155673, 155679, 155691, 162991,
    163031, 163169
]
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

def get_sensor_data(api_key, sensor_index):
    """Fetch a single sensor’s data and assign status & color."""
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
        return {'sensor_index': sensor_index, 'status': msg, 'name': 'N/A',
                'color': STATUS_COLORS['offline']}
    except requests.exceptions.RequestException:
        return {'sensor_index': sensor_index, 'status': '❌ Request Error',
                'name': 'N/A', 'color': STATUS_COLORS['offline']}

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

# --- Callbacks ---
def do_refresh():
    """Fetch all sensor data (with spinner) and store in session state."""
    with st.spinner("Fetching sensor data... Please wait."):
        api_key = st.secrets["textkey"]
        records = [
            get_sensor_data(api_key, idx)
            for idx in SENSOR_INDICES
        ]
        df = pd.DataFrame(records)
        st.session_state.df     = df
        st.session_state.df_map = df.dropna(subset=["latitude","longitude"]).copy()
    st.success("Finished fetching data!")

def reset_view():
    """Return map to default camera."""
    st.session_state.view_state = DEFAULT_VIEW


col1, col2 = st.columns(2)
with col1:
    st.button("🔄 Refresh Status", on_click=do_refresh)
with col2:
    st.button("🔄 Reset Map View", on_click=reset_view)

# --- Display Table ---
df = st.session_state.df
if not df.empty:
    now_ts = datetime.now(timezone.utc).timestamp()
    df['minutes_since_seen'] = df['last_seen'].apply(
        lambda x: (now_ts - x)/60 if pd.notna(x) else None
    )

    # 1. Add a priority for sorting: red (❌)=0, yellow (⚠️)=1, green (✅)=2
    def status_priority(s):
        if s.startswith('❌'): return 0
        if s.startswith('⚠️'): return 1
        if s.startswith('✅'): return 2
        return 3

    df['__priority'] = df['status'].apply(status_priority)

    # 2. Sort by that priority so red come first
    df = df.sort_values('__priority').drop(columns='__priority')

    # 3. Rename for display
    display_cols = {
        'sensor_index':     'Sensor ID',
        'status':           'Status',
        'name':             'Name',
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
        'Status', 'Sensor ID', 'Name', 'Mins Ago', 'Confidence (%)',
        'WiFi (RSSI)', 'Uptime (min)', 'PM2.5', 'PM2.5 (60m avg)',
        'Temp (°F)', 'Model', 'Lat', 'Lon'
    ] if c in df_disp.columns]

    # 5. Display the sorted table
    st.subheader("Sensor Status Details")
    st.dataframe(
        df_disp[order],
        use_container_width=True,
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
        "html": "<b>{name}</b><br/>ID: {sensor_index}<br/>Status: {status}",
        "style": {"backgroundColor":"steelblue","color":"white"}
    }
    deck = pdk.Deck(
        map_style="mapbox://styles/mapbox/light-v9",
        initial_view_state=st.session_state.view_state,
        layers=[layer],
        tooltip=tooltip
    )
    st.pydeck_chart(deck, use_container_width=True)

elif df_map.empty and not df.empty:
    st.warning("No sensors with location data found.")

with st.expander("Show Raw Data"):
    st.write(st.session_state.df.to_dict('records'))
