import os
import streamlit as st
import requests
import numpy as np
import pandas as pd
import folium
import plotly.express as px
from streamlit_folium import st_folium
from geopy import distance as geopy_distance
import openrouteservice

# Configuración APIs
ORS_API_KEY = st.secrets.get("OPENROUTESERVICE_KEY")
OWM_API_KEY = st.secrets.get("OPENWEATHERMAP_KEY")
WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
ors_client = openrouteservice.Client(key=ORS_API_KEY)

# Inicializar session_state
for key in ['origin', 'route', 'route3d', 'history', 'route_generated']:
    if key not in st.session_state:
        # route_generated indica si ya se creó ruta
        default = False if key == 'route_generated' else (None if key != 'history' else [])
        st.session_state[key] = default

# ——— Funciones ———
def get_weather(lat, lon):
    params = {"lat": lat, "lon": lon, "appid": OWM_API_KEY, "units": "metric"}
    r = requests.get(WEATHER_URL, params=params)
    if r.status_code != 200:
        return None
    j = r.json()
    return {"temp": j["main"]["temp"], "condition": j["weather"][0]["main"], "wind": j["wind"]["speed"]}

def get_forecast(lat, lon, hours=3):
    params = {"lat": lat, "lon": lon, "appid": OWM_API_KEY, "units": "metric"}
    r = requests.get(FORECAST_URL, params=params)
    if r.status_code != 200:
        return None
    data = r.json().get('list', [])[:hours]
    return [{"time": item['dt_txt'], "temp": item['main']['temp'], "condition": item['weather'][0]['main']} for item in data]

def compute_circular_route(origin, distance_m):
    lat0, lon0 = origin
    bearing = np.random.uniform(0, 360)
    half_km = distance_m / 2000
    dest = geopy_distance.distance(kilometers=half_km).destination((lat0, lon0), bearing)
    lat1, lon1 = dest.latitude, dest.longitude
    coords = [(lon0, lat0), (lon1, lat1)]
    route = ors_client.directions(
        coords,
        profile='cycling-regular',
        format_out='geojson',
        elevation=True
    )
    feat = route['features'][0]
    summary = feat['properties']['summary']
    geom = feat['geometry']['coordinates']
    coords2d = [(pt[1], pt[0]) for pt in geom]
    coords3d = [(pt[1], pt[0], pt[2]) for pt in geom]
    return {
        "coords": coords2d + list(reversed(coords2d)),
        "coords3d": coords3d + list(reversed(coords3d)),
        "distance": summary['distance'],
        "duration": summary['duration']
    }

# ——— Interfaz ———
st.set_page_config(page_title="🚴 Ruta de Ciclismo Avanzada", layout="wide")
st.title("🚴 Recomienda tu Ruta de Ciclismo con Perfil de Elevación")

# 1. Selección de punto de origen
st.subheader("1. Selecciona el punto de inicio (click en el mapa)")
center = (40.4168, -3.7038)
m = folium.Map(location=center, zoom_start=12)
m.add_child(folium.LatLngPopup())
map_data = st_folium(m, width=700, height=400)
if map_data and map_data.get("last_clicked"):
    st.session_state.origin = (map_data['last_clicked']['lat'], map_data['last_clicked']['lng'])
elif not st.session_state.origin:
    st.info("Haz click en el mapa para definir el origen.")
    st.stop()
lat, lon = st.session_state.origin
st.write(f"📍 Origen: ({lat:.6f}, {lon:.6f})")

# 2. Parámetros de ruta
d_km = st.slider("2. Distancia deseada (km)", 5, 50, 20)
distance = d_km * 1000

# 3. Clima actual
st.subheader("3. Clima en origen")
w = get_weather(lat, lon)
if w:
    st.write(f"🌡️ {w['temp']} °C — {w['condition']} — 💨 {w['wind']} m/s")
fcast = get_forecast(lat, lon)
if fcast:
    st.write("🔮 Pronóstico próximo:")
    for f in fcast:
        st.write(f"- {f['time']}: {f['condition']}, {f['temp']}°C")

# 4. Botón para generar ruta
if st.button("4. Generar Ruta"):
    result = compute_circular_route((lat, lon), distance)
    st.session_state.route = result['coords']
    st.session_state.route3d = result['coords3d']
    st.session_state.history.append((result['distance'], result['duration']))
    st.session_state.route_generated = True

# 5. Mostrar resultados si ya se generó ruta
if st.session_state.route_generated:
    dist = st.session_state.history[-1][0]
    dur = st.session_state.history[-1][1]
    st.subheader("Ruta generada")
    st.write(f"• Distancia (ORS): {dist/1000:.1f} km")
    st.write(f"• Duración estimada (ORS): {dur/60:.1f} min")
    # Predicción basada en histórico
    if len(st.session_state.history) > 1:
        arr = np.array(st.session_state.history)
        coeffs = np.polyfit(arr[:,0], arr[:,1], 1)
        pred = coeffs[0]*distance + coeffs[1]
        st.write(f"• Predicción personalizada: {pred/60:.1f} min")
    # Gráfico perfil de elevación
    if st.session_state.route3d:
        elevs = [pt[2] for pt in st.session_state.route3d]
        dists = [0.0]
        for i in range(1, len(st.session_state.route3d)):
            prev = st.session_state.route3d[i-1]
            curr = st.session_state.route3d[i]
            seg = geopy_distance.distance((prev[0], prev[1]), (curr[0], curr[1])).km * 1000
            dists.append(dists[-1] + seg)
        df_prof = pd.DataFrame({"distance_m": dists, "elevation_m": elevs})
        fig = px.line(
            df_prof,
            x="distance_m",
            y="elevation_m",
            labels={"distance_m": "Distancia (m)", "elevation_m": "Elevación (m)"},
            title="Perfil de Elevación"
        )
        st.plotly_chart(fig, use_container_width=True)
    # Mapa de ruta
    m2 = folium.Map(location=[lat, lon], zoom_start=13)
    folium.PolyLine(st.session_state.route, color='blue', weight=4).add_to(m2)
    st.subheader("🗺️ Mapa de ruta")
    st_folium(m2, width=700, height=400)
