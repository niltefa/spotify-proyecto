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
    st.write("DEBUG: download_graph() - solicitando grafo con dist=", dist)
    G = ox.graph_from_point(center_point, dist=dist, network_type='bike', simplify=True)
    st.write(f"DEBUG: download_graph() - grafo con {len(G.nodes)} nodos y {len(G.edges)} aristas descargado")
    return G


def add_elevation(G):
    """Anexa elevación a los nodos usando SRTM via osmnx."""
    st.write("DEBUG: add_elevation() - añadiendo elevaciones a nodos")
    G = ox.add_node_elevations_raster(G, max_locations_per_batch=100)
    G = ox.add_edge_grades(G)
    st.write("DEBUG: add_elevation() - elevaciones y grados añadidos")
    return G


def compute_route(G, origin_point, distance, weight='length'):
    """Genera ruta aproximada circular desde origen con distancia objetivo en metros."""
    st.write(f"DEBUG: compute_route() - origen {origin_point}, distancia objetivo {distance}")
    orig_node = ox.distance.nearest_nodes(G, origin_point[1], origin_point[0])
    st.write(f"DEBUG: compute_route() - nodo origen encontrado: {orig_node}")
    lengths = nx.shortest_path_length(G, orig_node, weight=weight)
    candidates = [n for n, d in lengths.items() if abs(d - distance/2) < distance*0.1]
    st.write(f"DEBUG: compute_route() - candidatos encontrados: {len(candidates)}")
    if not candidates:
        st.write("DEBUG: compute_route() - no hay candidatos, retornando ruta vacía")
        return []
    target = candidates[np.random.randint(len(candidates))]
    st.write(f"DEBUG: compute_route() - nodo objetivo seleccionado: {target}")
    path1 = nx.shortest_path(G, orig_node, target, weight=weight)
    st.write(f"DEBUG: compute_route() - longitud ruta ida: {len(path1)} nodos")
    path2 = list(reversed(path1))
    st.write(f"DEBUG: compute_route() - longitud ruta vuelta: {len(path2)} nodos")
    route = path1 + path2
    st.write(f"DEBUG: compute_route() - longitud total ruta: {len(route)} nodos")
    return route


# ——— Función clima ———
def get_weather(lat, lon):
    st.write(f"DEBUG: get_weather() - solicitando clima para ({lat}, {lon})")
    params = {"lat": lat, "lon": lon, "appid": OWM_API_KEY, "units": "metric"}
    r = requests.get(WEATHER_URL, params=params)
    if r.status_code != 200:
        st.write(f"DEBUG: get_weather() - error HTTP {r.status_code}")
        return None
    j = r.json()
    st.write(f"DEBUG: get_weather() - datos recibidos: temp={j['main']['temp']}, condition={j['weather'][0]['main']}, wind={j['wind']['speed']}")
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
    st.write("DEBUG: Botón 'Generar Ruta' presionado")
    with st.spinner("Calculando ruta..."):
        st.write("DEBUG: Iniciando descarga de grafo...")
        G = download_graph((lat, lon), dist=int(distance * 1.2))
        if inc_elev:
            st.write("DEBUG: Añadiendo elevación al grafo...")
            G = add_elevation(G)
        st.write("DEBUG: Calculando ruta con compute_route...")
        route_nodes = compute_route(G, (lat, lon), distance)
        if not route_nodes:
            st.error("No se pudo generar ruta.")
            st.write("DEBUG: route_nodes está vacío")
        else:
            st.write(f"DEBUG: route_nodes contiene {len(route_nodes)} nodos")
            coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in route_nodes]
            st.write("DEBUG: Generando mapa de ruta...")
            m2 = folium.Map(location=[lat, lon], zoom_start=13)
            folium.PolyLine(coords, color='blue', weight=4).add_to(m2)
            st.subheader("🗺️ Ruta generada")
            st_folium(m2, width=700, height=500)
            st.write("DEBUG: Ruta mostrada correctamente")