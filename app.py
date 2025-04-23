import os
import streamlit as st
import requests
import numpy as np
import folium
from streamlit_folium import st_folium
from geopy import distance as geopy_distance
import openrouteservice

# Configuración de APIs
t = st.secrets
temp = st.secrets
ORS_API_KEY = st.secrets.get("OPENROUTESERVICE_KEY")
OWM_API_KEY = st.secrets.get("OPENWEATHERMAP_KEY")
WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"

# Inicializar cliente ORS
ors_client = openrouteservice.Client(key=ORS_API_KEY)

# ——— Funciones ———
def get_weather(lat, lon):
    st.write("DEBUG: get_weather() - solicitando clima")
    params = {"lat": lat, "lon": lon, "appid": OWM_API_KEY, "units": "metric"}
    r = requests.get(WEATHER_URL, params=params)
    if r.status_code != 200:
        st.write(f"DEBUG: get_weather() - error {r.status_code}")
        return None
    j = r.json()
    st.write(f"DEBUG: get_weather() - recibido data: {j}")
    return {"temp": j["main"]["temp"], "condition": j["weather"][0]["main"], "wind": j["wind"]["speed"]}


def compute_circular_route(origin, distance_m):
    """
    Genera una ruta ida y vuelta con OpenRouteService vía 2 puntos:
    1) origen
    2) punto destino calculado a mitad de distancia con bearing aleatorio
    """
    st.write(f"DEBUG: compute_circular_route() - origin={origin}, distance={distance_m}")
    lat0, lon0 = origin
    # elegir bearing aleatorio
    bearing = np.random.uniform(0, 360)
    st.write(f"DEBUG: compute_circular_route() - bearing aleatorio: {bearing}")
    # calcular punto destino a mitad de la distancia
    half_km = distance_m / 2 / 1000  # en km
    dest = geopy_distance.distance(kilometers=half_km).destination((lat0, lon0), bearing)
    lat1, lon1 = dest.latitude, dest.longitude
    st.write(f"DEBUG: compute_circular_route() - destino calculado: ({lat1}, {lon1})")
    # solicitar ruta ORS
    coords = [(lon0, lat0), (lon1, lat1)]
    st.write(f"DEBUG: compute_circular_route() - solicitando ORS directions con coords {coords}")
    route = ors_client.directions(coords, profile='cycling-regular', format_out='geojson')
    geom = route['features'][0]['geometry']['coordinates']
    st.write(f"DEBUG: compute_circular_route() - recibida ruta con {len(geom)} puntos")
    # geom: lista de [lon, lat]
    # construimos ida + vuelta (invertida)
    return [(pt[1], pt[0]) for pt in geom] + [(pt[1], pt[0]) for pt in reversed(geom)]

# ——— Streamlit UI ———
st.set_page_config(page_title="🚴 Recomendador de Ruta con ORS", layout="wide")
st.title("🚴 Recomienda tu Ruta de Ciclismo")

# Selección de punto origen con Folium
st.subheader("Haz click en el mapa para elegir punto de inicio")
center = (40.4168, -3.7038)
m = folium.Map(location=center, zoom_start=12)
m.add_child(folium.LatLngPopup())
map_data = st_folium(m, width=700, height=500)
if map_data and map_data.get("last_clicked"):
    lat = map_data["last_clicked"]["lat"]
    lon = map_data["last_clicked"]["lng"]
    st.write(f"📍 Punto seleccionado: ({lat:.6f}, {lon:.6f})")
else:
    st.info("Selecciona un punto para continuar.")
    st.stop()

# Parámetros
d_km = st.slider("Distancia deseada (km)", 5, 50, 20)
distance = d_km * 1000
st.write(f"DEBUG: distancia solicitada {distance} m")

# Clima
w = get_weather(lat, lon)
if w:
    st.write(f"🌡️ {w['temp']} °C — {w['condition']} — 💨 {w['wind']} m/s")
    if w['condition'] in ['Rain', 'Drizzle']:
        st.warning("Está lloviendo, adapta tu plan.")

if st.button("Generar Ruta"):
    st.write("DEBUG: Generar Ruta pulsado")
    with st.spinner("Obteniendo ruta vía ORS..."):
        route = compute_circular_route((lat, lon), distance)
        if not route:
            st.error("No se obtuvo ruta.")
            st.write("DEBUG: ruta vacía")
        else:
            st.write(f"DEBUG: ruta generada con {len(route)} puntos")
            m2 = folium.Map(location=[lat, lon], zoom_start=13)
            folium.PolyLine(route, color='blue', weight=4).add_to(m2)
            st.subheader("🗺️ Ruta generada")
            st_folium(m2, width=700, height=500)
            st.write("DEBUG: ruta mostrada correctamente")