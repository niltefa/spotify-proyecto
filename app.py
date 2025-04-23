import os
import streamlit as st
import osmnx as ox
import networkx as nx
import requests
import numpy as np
import folium
from streamlit_folium import st_folium

# Configuración API Clima
OWM_API_KEY = st.secrets.get("OPENWEATHERMAP_KEY")
WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"

# ——— Funciones de Rutas ———
def download_graph(center_point, dist=5000):
    """Descarga grafo de carreteras alrededor de un punto (lat, lon)."""
    return ox.graph_from_point(center_point, dist=dist, network_type='bike', simplify=True)


def add_elevation(G):
    """Anexa elevación a los nodos usando SRTM via osmnx."""
    G = ox.add_node_elevations_raster(G, max_locations_per_batch=100)
    return ox.add_edge_grades(G)


def compute_route(G, origin_point, distance, weight='length'):
    """Genera ruta aproximada circular desde origen con distancia objetivo en metros."""
    orig_node = ox.distance.nearest_nodes(G, origin_point[1], origin_point[0])
    lengths = nx.shortest_path_length(G, orig_node, weight=weight)
    candidates = [n for n, d in lengths.items() if abs(d - distance/2) < distance*0.1]
    if not candidates:
        return []
    target = candidates[np.random.randint(len(candidates))]
    path1 = nx.shortest_path(G, orig_node, target, weight=weight)
    return path1 + list(reversed(path1))  # ida y vuelta


# ——— Función clima ———
def get_weather(lat, lon):
    params = {"lat": lat, "lon": lon, "appid": OWM_API_KEY, "units": "metric"}
    r = requests.get(WEATHER_URL, params=params)
    if r.status_code != 200:
        return None
    j = r.json()
    return {"temp": j["main"]["temp"], "condition": j.get("weather")[0]["main"], "wind": j["wind"]["speed"]}

# ——— INTERFAZ STREAMLIT ———
st.set_page_config(page_title="🚴 Ruta de Ciclismo con Folium", layout="wide")
st.title("🚴 Recomienda tu Ruta de Ciclismo")

# Mapa de Folium para seleccionar inicio
st.subheader("Selecciona el punto de inicio (click en el mapa)")
center = (40.4168, -3.7038)
m = folium.Map(location=center, zoom_start=12)
m.add_child(folium.LatLngPopup())
map_data = st_folium(m, width=700, height=500)

if map_data and map_data.get("last_clicked"):
    lat = map_data["last_clicked"]["lat"]
    lon = map_data["last_clicked"]["lng"]
    st.write(f"📍 Punto seleccionado: ({lat:.6f}, {lon:.6f})")
else:
    st.info("Haz click en el mapa para elegir el punto de inicio.")
    st.stop()

# Parámetros de ruta
d_km = st.slider("Distancia deseada (km)", 5, 50, 20)
distance = d_km * 1000
inc_elev = st.checkbox("Incluir elevación?", True)

# Mostrar clima
w = get_weather(lat, lon)
if w:
    st.write(f"🌡️ {w['temp']} °C — {w['condition']} — 💨 {w['wind']} m/s")
    if w['condition'] in ['Rain', 'Drizzle']:
        st.warning("Está lloviendo, adapta tu ruta.")

# Generar ruta
if st.button("Generar Ruta"):
    with st.spinner("Calculando ruta..."):
        G = download_graph((lat, lon), dist=int(distance * 1.2))
        if inc_elev:
            G = add_elevation(G)
        route_nodes = compute_route(G, (lat, lon), distance)
        if not route_nodes:
            st.error("No se pudo generar ruta.")
        else:
            coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in route_nodes]
            m2 = folium.Map(location=[lat, lon], zoom_start=13)
            folium.PolyLine(coords, color='blue', weight=4).add_to(m2)
            st.subheader("🗺️ Ruta generada")
            st_folium(m2, width=700, height=500)
