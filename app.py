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
from openrouteservice.exceptions import ApiError
from folium.plugins import LocateControl
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from staticmap import StaticMap, Line
from PIL import Image

st.set_page_config(
    page_title='Tu rutilla',
    page_icon='./favicon.ico',
    layout='wide',
    initial_sidebar_state='auto'
)

# Configuración de APIs
t = st.secrets
ORS_API_KEY = t.get("OPENROUTESERVICE_KEY")
OWM_API_KEY = t.get("OPENWEATHERMAP_KEY")
WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
ors_client = openrouteservice.Client(key=ORS_API_KEY)

# Inicializar session_state
for key in [
    'origin', 'route', 'route3d', 'history', 'history_elev',
    'route_generated', 'weather'
]:
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
    return {
        "temp": j["main"]["temp"],
        "condition": j["weather"][0]["main"],
        "wind": j["wind"]["speed"]
    }

def get_forecast(lat, lon, hours=3):
    params = {"lat": lat, "lon": lon, "appid": OWM_API_KEY, "units": "metric"}
    r = requests.get(FORECAST_URL, params=params)
    if r.status_code != 200:
        return None
    data = r.json().get('list', [])[:hours]
    return [
        {
            "time": item['dt_txt'],
            "temp": item['main']['temp'],
            "condition": item['weather'][0]['main']
        }
        for item in data
    ]

def compute_circular_route(origin, distance_m):
    lat0, lon0 = origin
    for attempt in range(5):
        bearing = np.random.uniform(0, 360)
        half_km = distance_m / 2000.0
        dest = geopy_distance.distance(
            kilometers=half_km
        ).destination((lat0, lon0), bearing)
        coords = [(lon0, lat0), (dest.longitude, dest.latitude)]
        try:
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
        except ApiError:
            continue
    raise ApiError("No se pudo generar ruta tras varios intentos.")

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
    pts = coords if N <= max_pts else [
        coords[i]
        for i in np.linspace(0, N-1, max_pts, dtype=int)
    ]
    path = "/".join(f"{lat},{lon}" for lat, lon in pts)
    return f"https://www.google.com/maps/dir/{path}"

# ——— UI ———
st.title("🚴 Tu rutilla de ciclismo + métricas de rendimiento")

# 0. Peso del usuario
weight_kg = st.number_input("¿Cuál es tu peso? (kg)", min_value=40, max_value=150, value=70)

# 1. Selección de origen (siempre visible)
st.subheader("1. Selecciona el punto de inicio (click en el mapa)")
center = (40.4168, -3.7038)
m = folium.Map(location=center, zoom_start=12)
LocateControl(auto_start=True).add_to(m)
m.add_child(folium.LatLngPopup())
map_data = st_folium(m, width=700, height=300)

# Si hace click, actualizamos el origen
if map_data and map_data.get("last_clicked"):
    st.session_state.origin = (
        map_data['last_clicked']['lat'],
        map_data['last_clicked']['lng']
    )

# Si aún no hay origen, detenemos para forzar selección
if not st.session_state.origin:
    st.info("Haz click en el mapa para definir el origen.")
    st.stop()

lat, lon = st.session_state.origin
st.write(f"📍 Origen: ({lat:.6f}, {lon:.6f})")

# 2. Selección de distancia (usar mitad para generar)
d_km = st.slider("2. Distancia deseada (km)", 5, 250, 20)
distance = d_km * 1000 / 2

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
if st.button("4. Generar ruta"):
    try:
        res = compute_circular_route((lat, lon), distance)
    except ApiError as e:
        st.error(f"Error al generar la ruta: {e}")
        st.session_state.route_generated = False
    else:
        st.session_state.route = res['coords']
        st.session_state.route3d = res['coords3d']
        dist = res['distance']; dur = res['duration']
        elevs = [pt[2] for pt in st.session_state.route3d]
        # Cálculo de desnivel positivo y negativo
        ascent = sum(max(elevs[i] - elevs[i-1], 0) for i in range(1, len(elevs)))
        st.session_state.history.append((dist, dur, ascent))
        st.session_state.route_generated = True

# 5. Mostrar resultados y métricas
if st.session_state.route_generated:
    dist, dur, ascent = st.session_state.history[-1]

    st.subheader("Ruta generada y métricas")
    st.write(f"• Distancia: **{dist/1000:.1f} km**")
    st.write(f"• Duración estimada: **{dur/60:.1f} min**")
    st.write(f"• Desnivel positivo: **{ascent:.0f} m**")
    
    # → Velocidad media
    dur_h = dur / 3600.0
    avg_speed = (dist/1000.0) / dur_h if dur_h > 0 else 0
    st.write(f"• Velocidad media: **{avg_speed:.1f} km/h**")

    # → Calorías estimadas
    if avg_speed < 16:
        MET = 6
    elif avg_speed < 20:
        MET = 8
    else:
        MET = 10
    calories = MET * weight_kg * dur_h
    st.write(f"• Calorías estimadas: **{calories:.0f} kcal**")

    # Dificultad
    dif = predict_difficulty(dist, ascent, st.session_state.weather)
    st.write(f"• Dificultad: **{dif}**")

    # Enlace a Google Maps
    st.markdown(
        f"[➡️ Ver ruta en Google Maps]({generate_google_maps_url(st.session_state.route)})",
        unsafe_allow_html=True
    )

    # Perfil de elevación
    coords3d = st.session_state.route3d
    dist_acc = [0.0]
    for i in range(1, len(coords3d)):
        p0, p1 = coords3d[i-1], coords3d[i]
        seg = geopy_distance.distance((p0[0], p0[1]), (p1[0], p1[1]))
        dist_acc.append(dist_acc[-1] + seg.km * 1000)
    df_prof = pd.DataFrame({
        "distance_m": dist_acc,
        "elevation_m": [pt[2] for pt in coords3d]
    })
    fig = px.line(
        df_prof,
        x="distance_m",
        y="elevation_m",
        labels={"distance_m": "Distancia (m)", "elevation_m": "Elevación (m)"},
        title="Perfil de Elevación"
    )
    st.plotly_chart(fig, use_container_width=True)

    # Mapa de ruta
    st.subheader("🗺️ Mapa de ruta")
    m2 = folium.Map(location=[lat, lon], zoom_start=13)
    folium.PolyLine(st.session_state.route, color='blue', weight=4).add_to(m2)
    st_folium(m2, width=700, height=300, returned_objects=[])

    # Generar y descargar PDF
    m_static = StaticMap(700, 300)
    m_static.add_line(Line([(lon, lat) for lat, lon in st.session_state.route], 'blue', 4))
    img_static = m_static.render()
    buf = io.BytesIO()
    img_static.save(buf, format='PNG')
    map_png = buf.getvalue()

    pdf_buf = io.BytesIO()
    c = canvas.Canvas(pdf_buf, pagesize=letter)
    w_pt, h_pt = letter
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(w_pt/2, h_pt - 50, "Detalle de la ruta de ciclismo")
    c.drawImage(ImageReader(io.BytesIO(map_png)), 50, h_pt - 400, width=500, height=300)
    y0 = h_pt - 420
    c.setFont("Helvetica", 12)
    c.drawString(50, y0, f"• Distancia: {dist/1000:.2f} km")
    c.drawString(50, y0-20, f"• Duración: {dur/60:.1f} min")
    c.drawString(50, y0-40, f"• Desnivel total : {ascent:.0f} m")
    c.drawString(50, y0-80, f"• Velocidad media: {avg_speed:.1f} km/h")
    c.drawString(50, y0-100, f"• Calorías: {calories:.0f} kcal")
    c.drawString(50, y0-120, f"• Dificultad: {dif}")
    prof_png = fig.to_image(format="png")
    c.drawImage(ImageReader(io.BytesIO(prof_png)), 50, y0-380, width=500, height=250)
    c.showPage()
    c.save()
    pdf_buf.seek(0)
    st.download_button(
        "📄 Descargar PDF con la ruta y métricas",
        data=pdf_buf.read(),
        file_name="ruta_ciclismo_metrics.pdf",
        mime="application/pdf"
    )
