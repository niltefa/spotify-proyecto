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
from folium.plugins import LocateControl
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

# Configuración APIs
t = st.secrets
ORS_API_KEY = t.get("OPENROUTESERVICE_KEY")
OWM_API_KEY = t.get("OPENWEATHERMAP_KEY")
WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
ors_client = openrouteservice.Client(key=ORS_API_KEY)

# Inicializar session_state
for key in ['origin','route','route3d','history','history_elev','route_generated','weather']:
    if key not in st.session_state:
        if key in ['history','history_elev']:
            st.session_state[key]=[]
        elif key=='route_generated':
            st.session_state[key]=False
        else:
            st.session_state[key]=None

# ——— Funciones ———
def get_weather(lat, lon):
    params={"lat":lat,"lon":lon,"appid":OWM_API_KEY,"units":"metric"}
    r=requests.get(WEATHER_URL,params=params)
    if r.status_code!=200: return None
    j=r.json()
    return {"temp":j["main"]["temp"],"condition":j["weather"][0]["main"],"wind":j["wind"]["speed"]}

def get_forecast(lat, lon, hours=3):
    params={"lat":lat,"lon":lon,"appid":OWM_API_KEY,"units":"metric"}
    r=requests.get(FORECAST_URL,params=params)
    if r.status_code!=200: return None
    data=r.json().get('list',[])[:hours]
    return [{"time":item['dt_txt'],"temp":item['main']['temp'],"condition":item['weather'][0]['main']} for item in data]

def compute_circular_route(origin, distance_m):
    lat0,lon0=origin
    bearing=np.random.uniform(0,360)
    half_km=distance_m/2000.0
    dest=geopy_distance.distance(kilometers=half_km).destination((lat0,lon0),bearing)
    lat1,lon1=dest.latitude,dest.longitude
    coords=[(lon0,lat0),(lon1,lat1)]
    route=ors_client.directions(coords,profile='cycling-regular',format_out='geojson',elevation=True)
    feat=route['features'][0]
    summary=feat['properties']['summary']
    geom=feat['geometry']['coordinates']
    coords2d=[(pt[1],pt[0]) for pt in geom]
    coords3d=[(pt[1],pt[0],pt[2]) for pt in geom]
    return {"coords":coords2d+list(reversed(coords2d)),"coords3d":coords3d+list(reversed(coords3d)),"distance":summary['distance'],"duration":summary['duration']}

def predict_difficulty(distance_m, ascent_m, weather):
    km=distance_m/1000.0
    score=km+(ascent_m/100.0)
    if weather and weather.get('condition') in ['Rain','Drizzle','Thunderstorm','Snow']: score+=5
    if weather:
        temp=weather.get('temp',20)
        if temp<5: score+=(5-temp)/2
        elif temp>30: score+=(temp-30)/2
    if score<10: return "Fácil"
    elif score<20: return "Medio"
    elif score<30: return "Difícil"
    else: return "Extremo"

def generate_google_maps_url(coords):
    N=len(coords);max_pts=25
    pts=coords if N<=max_pts else [coords[i] for i in np.linspace(0,N-1,max_pts,dtype=int)]
    path="/".join(f"{lat},{lon}" for lat,lon in pts)
    return f"https://www.google.com/maps/dir/{path}"

def generate_pdf(info):
    buffer=BytesIO()
    c=canvas.Canvas(buffer,pagesize=A4)
    width,height=A4
    y=height-20*mm
    c.setFont('Helvetica-Bold',14);c.drawString(15*mm,y,'Resumen de Ruta de Ciclismo')
    y-=10*mm
    for line in info:
        c.setFont('Helvetica',10);c.drawString(15*mm,y,line)
        y-=6*mm
        if y<20*mm:
            c.showPage();y=height-20*mm
    c.save();buffer.seek(0)
    return buffer

# ——— UI ———
st.set_page_config(page_title='🚴 Ruta de Ciclismo',layout='wide')
st.title('🚴 Ruta de Ciclismo con Descarga de PDF')
# Origen
st.subheader('1. Selecciona origen (mapa)')
center=(40.4168,-3.7038)
m=folium.Map(location=center,zoom_start=12)
LocateControl(auto_start=True).add_to(m)
m.add_child(folium.LatLngPopup())
dh=200 if st.session_state.origin is None else 300
map_data=st_folium(m,width=700,height=dh)
if map_data and map_data.get('last_clicked'):
    st.session_state.origin=(map_data['last_clicked']['lat'],map_data['last_clicked']['lng'])
elif not st.session_state.origin:
    st.info('Haz click en el mapa para definir el origen.');st.stop()
lat,lon=st.session_state.origin
st.write(f'📍 Origen: ({lat:.6f},{lon:.6f})')
# Distancia
d_km=st.slider('2. Distancia (km)',5,50,20);distance=d_km*1000
# Clima
st.subheader('3. Clima')
w=get_weather(lat,lon);st.session_state.weather=w
if w: st.write(f"🌡️ {w['temp']}°C — {w['condition']} — 💨 {w['wind']} m/s")
# Generar
if st.button('4. Generar Ruta'):
    res=compute_circular_route((lat,lon),distance)
    st.session_state.route=res['coords'];st.session_state.route3d=res['coords3d']
    dist=res['distance'];dur=res['duration']
    elevs=[pt[2] for pt in st.session_state.route3d]
    ascent=sum(max(elevs[i]-elevs[i-1],0) for i in range(1,len(elevs)))
    st.session_state.history.append((dist,dur));st.session_state.history_elev.append(ascent)
    st.session_state.route_generated=True

# Mostrar
if st.session_state.route_generated:
    dist=st.session_state.history[-1][0];dur=st.session_state.history[-1][1]
    ascent=st.session_state.history_elev[-1]
    st.subheader('Ruta generada')
    st.write(f"• Distancia: {dist/1000:.1f} km")
    st.write(f"• Duración: {dur/60:.1f} min")
    st.write(f"• Desnivel: {ascent:.0f} m")
    dif=predict_difficulty(dist,ascent,st.session_state.weather)
    st.write(f"• Dificultad: {dif}")
    url=generate_google_maps_url(st.session_state.route)
    st.markdown(f"[Ver en Google Maps]({url})")
    # Recopilar info para PDF
    info=[
        f"Origen: {lat:.6f},{lon:.6f}",
        f"Distancia: {dist/1000:.1f} km",f"Duración: {dur/60:.1f} min",f"Desnivel: {ascent:.0f} m",f"Dificultad: {dif}",
        f"Clima: {w.get('condition','-')} {w.get('temp','-')}°C" if w else 'Clima: -'
    ]
    buf=generate_pdf(info)
    st.download_button('📥 Descargar PDF',data=buf, file_name='ruta.pdf',mime='application/pdf')
    # Perfil gráfico
    df_prof=pd.DataFrame({'distance_m':[0]+[geopy_distance.distance((st.session_state.route3d[i-1][0],st.session_state.route3d[i-1][1]),(st.session_state.route3d[i][0],st.session_state.route3d[i][1])).km*1000 for i in range(1,len(st.session_state.route3d))],'elevation_m':[pt[2] for pt in st.session_state.route3d]})
    fig=px.line(df_prof,x='distance_m',y='elevation_m',title='Perfil')
    st.plotly_chart(fig)
    m2=folium.Map(location=[lat,lon],zoom_start=13)
    folium.PolyLine(st.session_state.route,color='blue',weight=4).add_to(m2)
    st.subheader('Mapa')
    st_folium(m2,width=700,height=300,returned_objects=[])
