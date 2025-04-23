import streamlit as st
import osmnx as ox
import networkx as nx
import requests
import folium
from streamlit_folium import st_folium
import numpy as np

# Configuración API Clima
OWM_API_KEY = st.secrets.get("OPENWEATHERMAP_KEY")
WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"

# ——— Funciones de Rutas ———
def download_graph(center_point, dist=5000):
    """Descarga grafo de carreteras alrededor de un punto (lat, lon)."""
    G = ox.graph_from_point(center_point, dist=dist, network_type='bike', simplify=True)
    return G

def add_elevation(G):
    """Anexa elevación a los nodos usando SRTM via osmnx."""
    G = ox.add_node_elevations_raster(G, max_locations_per_batch=100)
    G = ox.add_edge_grades(G)
    return G

def compute_route(G, origin_point, distance, weight='length'):
    """Genera ruta aproximada circular desde origen con distancia objetivo en metros."""
    # Encuentra nodo más cercano
    orig_node = ox.distance.nearest_nodes(G, origin_point[1], origin_point[0])
    # Camino: heurística de vorágine radial + Dijkstra
    # Para MVP: encuentra punto destino al azar en anillo
    nodes = list(G.nodes)
    lengths = nx.shortest_path_length(G, orig_node, weight=weight)
    # Filtrar nodos cerca de distancia
    candidates = [n for n,d in lengths.items() if abs(d - distance/2) < distance*0.1]
    if not candidates:
        return []
    target = candidates[np.random.randint(len(candidates))]
    # Ruta ida
    path1 = nx.shortest_path(G, orig_node, target, weight=weight)
    # Ruta vuelta
    path2 = list(reversed(path1))
    route = path1 + path2
    return route

# ——— Función clima ———
def get_weather(lat, lon):
    params = {"lat": lat, "lon": lon, "appid": OWM_API_KEY, "units": "metric"}
    resp = requests.get(WEATHER_URL, params=params)
    if resp.status_code != 200:
        return None
    data = resp.json()
    return {"temp": data["main"]["temp"], "rain": data.get("weather")[0]["main"], "wind": data["wind"]["speed"]}

# ——— INTERFAZ STREAMLIT ———
st.title("🚴 Recomienda tu Ruta de Ciclismo")

# Selección de ubicación de inicio
lat = st.number_input("Latitud de inicio", format="%.6f", value=40.4168)
lon = st.number_input("Longitud de inicio", format="%.6f", value=-3.7038)
distance = st.slider("Distancia deseada (km)", 5, 50, 20) * 1000

dither = st.checkbox("Incluir elevación?", value=True)
weather = get_weather(lat, lon)
if weather:
    st.write(f"🌡️ {weather['temp']} °C, ☁️ {weather['rain']}, 💨 {weather['wind']} m/s")
    if weather['rain'] in ['Rain','Drizzle']:
        st.warning("¡Está lloviendo! Puedes ajustar tu ruta o posponer el paseo.")

if st.button("Generar Ruta"):
    with st.spinner("Descargando grafo y calculando..."):
        G = download_graph((lat, lon), dist=int(distance*1.2))
        if dither:
            G = add_elevation(G)
        route = compute_route(G, (lat, lon), distance)
        if not route:
            st.error("No se pudo generar una ruta con esos parámetros.")
        else:
            # Visualiza con folium
            m = folium.Map(location=[lat, lon], zoom_start=13)
            coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in route]
            folium.PolyLine(coords, color='blue', weight=5).add_to(m)
            st_folium(m, width=700, height=500)
