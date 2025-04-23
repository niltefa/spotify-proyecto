import os
import streamlit as st
import requests
import numpy as np
import folium
from streamlit_folium import st_folium
from geopy import distance as geopy_distance
import openrouteservice

# Configuración APIs
ORS_API_KEY = st.secrets.get("OPENROUTESERVICE_KEY")
OWM_API_KEY = st.secrets.get("OPENWEATHERMAP_KEY")
WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
ors_client = openrouteservice.Client(key=ORS_API_KEY)

# ——— Inicializar session_state ———
if 'origin' not in st.session_state:
    st.session_state.origin = None
if 'route' not in st.session_state:
    st.session_state.route = None

# ——— Funciones ———
def get_weather(lat, lon):
    st.write("DEBUG: solicitando clima...")
    params = {"lat": lat, "lon": lon, "appid": OWM_API_KEY, "units": "metric"}
    r = requests.get(WEATHER_URL, params=params)
    if r.status_code != 200:
        st.write(f"DEBUG: error clima {r.status_code}")
        return None
    j = r.json()
    st.write(f"DEBUG: clima recibido {j}")
    return {"temp": j["main"]["temp"], "condition": j["weather"][0]["main"], "wind": j["wind"]["speed"]}


def compute_circular_route(origin, distance_m):
    st.write(f"DEBUG: computando ruta circular desde {origin}, distancia {distance_m}")
    lat0, lon0 = origin
    bearing = np.random.uniform(0, 360)
    half_km = distance_m / 2 / 1000
    dest = geopy_distance.distance(kilometers=half_km).destination((lat0, lon0), bearing)
    lat1, lon1 = dest.latitude, dest.longitude
    st.write(f"DEBUG: destino calculado ({lat1},{lon1}) bearing {bearing}")
    coords = [(lon0, lat0), (lon1, lat1)]
    st.write(f"DEBUG: solicitando ORS con coords {coords}")
    route = ors_client.directions(coords, profile='cycling-regular', format_out='geojson')
    geom = route['features'][0]['geometry']['coordinates']
    st.write(f"DEBUG: ORS geom puntos {len(geom)}")
    pts = [(pt[1], pt[0]) for pt in geom]
    return pts + pts[::-1]

# ——— UI ———
st.set_page_config(page_title="🚴 Ruta Ciclismo Persistente", layout="wide")
st.title("🚴 Recomienda tu Ruta de Ciclismo")

# Selección de origen
st.subheader("1. Selecciona el punto de inicio")
center = (40.4168, -3.7038)
m = folium.Map(location=center, zoom_start=12)
m.add_child(folium.LatLngPopup())
map_data = st_folium(m, width=700, height=400)
if map_data and map_data.get("last_clicked"):
    lat = map_data["last_clicked"]["lat"]
    lon = map_data["last_clicked"]["lng"]
    st.session_state.origin = (lat, lon)
    st.write(f"📍 Origen guardado: {st.session_state.origin}")
elif st.session_state.origin:
    lat, lon = st.session_state.origin
    st.write(f"📍 Origen previo: {st.session_state.origin}")
else:
    st.info("Haz click en el mapa para definir el origen.")
    st.stop()

# Parámetros
d_km = st.slider("2. Distancia deseada (km)", 5, 50, 20)
distance = d_km * 1000
inc_elev = st.checkbox("Incluir elevación? (no aplica con ORS)", False)

# Clima
w = get_weather(lat, lon)
if w:
    st.write(f"🌡️ {w['temp']} °C — {w['condition']} — 💨 {w['wind']} m/s")
    if w['condition'] in ['Rain', 'Drizzle']:
        st.warning("Está lloviendo: considera otro día o ruta.")

# Generar ruta
if st.button("3. Generar Ruta"):  # step 3
    st.write("DEBUG: Botón Generar Ruta pulsado")
    st.session_state.route = compute_circular_route(st.session_state.origin, distance)

# Mostrar ruta si existe
if st.session_state.route:
    st.subheader("🗺️ Ruta generada")
    m2 = folium.Map(location=st.session_state.origin, zoom_start=13)
    folium.PolyLine(st.session_state.route, color='blue', weight=4).add_to(m2)
    st_folium(m2, width=700, height=400)
    st.write(f"DEBUG: Mostrando ruta con {len(st.session_state.route)} puntos")