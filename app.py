import os
import io
import streamlit as st
import requests
import numpy as np
import pandas as pd
import folium
import plotly.express as px
from streamlit_folium import st_folium
from geopy import distance as geopy_distance
import openrouteservice
from folium.plugins import LocateControl
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader

# Configuración APIs
t = st.secrets
ORS_API_KEY = t.get("OPENROUTESERVICE_KEY")
OWM_API_KEY = t.get("OPENWEATHERMAP_KEY")
WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
ors_client = openrouteservice.Client(key=ORS_API_KEY)

# Inicializar session_state
for key in ['origin', 'route', 'route3d', 'history', 'history_elev', 'route_generated', 'weather']:
    if key not in st.session_state:
        if key in ['history', 'history_elev']:
            st.session_state[key] = []
        elif key == 'route_generated':
            st.session_state[key] = False
        else:
            st.session_state[key] = None

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
    half_km = distance_m / 2000.0
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


def predict_difficulty(distance_m, ascent_m, weather):
    km = distance_m / 1000.0
    score = km + (ascent_m / 100.0)
    if weather and weather.get('condition') in ['Rain', 'Drizzle', 'Thunderstorm', 'Snow']:
        score += 5
    if weather:
        temp = weather.get('temp', 20)
        if temp < 5:
            score += (5 - temp) / 2
        elif temp > 30:
            score += (temp - 30) / 2
    if score < 10:
        return "Fácil"
    elif score < 20:
        return "Medio"
    elif score < 30:
        return "Difícil"
    else:
        return "Extremo"


def generate_google_maps_url(coords):
    N = len(coords)
    max_pts = 25
    if N <= max_pts:
        pts = coords
    else:
        indices = np.linspace(0, N-1, max_pts, dtype=int)
        pts = [coords[i] for i in indices]
    path = "/".join(f"{lat},{lon}" for lat, lon in pts)
    return f"https://www.google.com/maps/dir/{path}"

# ——— UI ———
st.set_page_config(page_title="🚴 Ruta de Ciclismo Avanzada", layout="wide")
st.title("🚴 Recomienda tu Ruta de Ciclismo con Perfil de Elevación, Desnivel y Google Maps")

# 1. Selección de origen
st.subheader("1. Selecciona el punto de inicio (click en el mapa)")
center = (40.4168, -3.7038)
m = folium.Map(location=center, zoom_start=12)
LocateControl(auto_start=True).add_to(m)
m.add_child(folium.LatLngPopup())
dynamic_height = 600 if st.session_state.origin is None else 800
map_data = st_folium(m, width=700, height=dynamic_height)
if map_data and map_data.get("last_clicked"):
    st.session_state.origin = (map_data['last_clicked']['lat'], map_data['last_clicked']['lng'])
elif not st.session_state.origin:
    st.info("Haz click en el mapa para definir el origen.")
    st.stop()
lat, lon = st.session_state.origin
st.write(f"📍 Origen: ({lat:.6f}, {lon:.6f})")

# 2. Selección de distancia
d_km = st.slider("2. Distancia deseada (km)", 5, 250, 20)
distance = d_km * 1000

# 3. Clima y pronóstico
st.subheader("3. Clima en origen")
w = get_weather(lat, lon)
st.session_state.weather = w
if w:
    st.write(f"🌡️ {w['temp']} °C — {w['condition']} — 💨 {w['wind']} m/s")
    fcast = get_forecast(lat, lon)
    if fcast:
        st.write("🔮 Pronóstico próximo:")
        for f in fcast:
            st.write(f"- {f['time']}: {f['condition']}, {f['temp']}°C")
else:
    st.write("No se pudo obtener clima.")

# 4. Generar ruta
if st.button("4. Generar Ruta"):
    res = compute_circular_route((lat, lon), distance)
    st.session_state.route = res['coords']
    st.session_state.route3d = res['coords3d']
    dist = res['distance']; dur = res['duration']
    elevs = [pt[2] for pt in st.session_state.route3d]
    ascent = sum(max(elevs[i] - elevs[i-1], 0) for i in range(1, len(elevs)))
    st.session_state.history.append((dist, dur))
    st.session_state.history_elev.append(ascent)
    st.session_state.route_generated = True

# 5. Mostrar resultados
if st.session_state.route_generated:
    dist = st.session_state.history[-1][0]
    dur = st.session_state.history[-1][1]
    ascent = st.session_state.history_elev[-1]
    st.subheader("Ruta generada")
    st.write(f"• Distancia (ORS): {dist/1000:.1f} km")
    st.write(f"• Duración estimada (ORS): {dur/60:.1f} min")
    st.write(f"• Desnivel total (ascenso): {ascent:.0f} m")
    dif = predict_difficulty(dist, ascent, st.session_state.weather)
    st.write(f"• Dificultad estimada: **{dif}**")
    url = generate_google_maps_url(st.session_state.route)
    st.markdown(f"[Ver ruta en Google Maps]({url})", unsafe_allow_html=True)

    if len(st.session_state.history) > 1:
        arr = np.array(st.session_state.history)
        coeffs_time = np.polyfit(arr[:,0], arr[:,1], 1)
        pred_time = coeffs_time[0] * distance + coeffs_time[1]
        st.write(f"• Predicción tiempo personalizada: {pred_time/60:.1f} min")
    if len(st.session_state.history_elev) > 1:
        dists = [h[0] for h in st.session_state.history]
        coeffs_elev = np.polyfit(dists, st.session_state.history_elev, 1)
        pred_elev = coeffs_elev[0] * distance + coeffs_elev[1]
        st.write(f"• Predicción desnivel personalizada: {pred_elev:.0f} m")

    # Perfil de elevación gráfico
    coords3d = st.session_state.route3d
    dist_acc = [0.0]
    for i in range(1, len(coords3d)):
        p0, p1 = coords3d[i-1], coords3d[i]
        seg = geopy_distance.distance((p0[0], p0[1]), (p1[0], p1[1])).km * 1000
        dist_acc.append(dist_acc[-1] + seg)
    df_prof = pd.DataFrame({"distance_m": dist_acc, "elevation_m": [pt[2] for pt in coords3d]})
    fig = px.line(df_prof, x="distance_m", y="elevation_m",
                  labels={"distance_m": "Distancia (m)", "elevation_m": "Elevación (m)"},
                  title="Perfil de Elevación")
    st.plotly_chart(fig, use_container_width=True)

    # Generar PNG de mapa estático con OSM StaticMap
    sampled = st.session_state.route
    if len(sampled) > 100:
        idx = np.linspace(0, len(sampled)-1, 100, dtype=int)
        sampled = [sampled[i] for i in idx]
    path_str = "color:blue|weight:4|" + "|".join(f"{lat},{lon}" for lat, lon in sampled)
    osm_url = f"https://staticmap.openstreetmap.de/staticmap.php?size=700x300&path={path_str}"
    resp = requests.get(osm_url)
    map_png = resp.content if resp.status_code == 200 else None

    if map_png:
        # Generación del PDF
        pdf_buffer = io.BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=letter)
        w_pt, h_pt = letter

        c.setFont("Helvetica-Bold", 18)
        c.drawCentredString(w_pt/2, h_pt - 50, "🛣 Detalle de la Ruta de Ciclismo")
        img = ImageReader(io.BytesIO(map_png))
        c.drawImage(img, 50, h_pt - 100 - 300, width=500, height=300)

        y0 = h_pt - 420
        c.setFont("Helvetica", 12)
        c.drawString(50, y0,    f"• Distancia: {dist/1000:.2f} km")
        c.drawString(50, y0-20, f"• Duración: {dur/60:.1f} min")
        c.drawString(50, y0-40, f"• Desnivel: {ascent:.0f} m")
        c.drawString(50, y0-60, f"• Dificultad: {dif}")

        prof_png = fig.to_image(format="png")
        prof_img = ImageReader(io.BytesIO(prof_png))
        c.drawImage(prof_img, 50, y0 - 360, width=500, height=250)

        c.showPage()
        c.save()
        pdf_buffer.seek(0)
        pdf_bytes = pdf_buffer.read()

        st.download_button(
            label="📄 Descargar PDF con la ruta",
            data=pdf_bytes,
            file_name="ruta_ciclismo.pdf",
            mime="application/pdf"
        )
    else:
        st.error("No se pudo obtener la imagen de la ruta para generar el PDF.")
