import os
import base64
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import streamlit as st
import spotipy

# ——— CONFIG ———
CLIENT_ID     = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI  = "https://tu-musiquilla.streamlit.app/callback"
SCOPE         = "user-read-recently-played"
AUTH_URL      = (
    f"https://accounts.spotify.com/authorize"
    f"?client_id={CLIENT_ID}"
    f"&response_type=code"
    f"&redirect_uri={REDIRECT_URI}"
    f"&scope={SCOPE}"
)
TOKEN_URL = "https://accounts.spotify.com/api/token"

# ——— UI ———
st.title("🎧 Tu Huella Emocional Sonora")
code = st.experimental_get_query_params().get("code", [None])[0]

if not CLIENT_ID or not CLIENT_SECRET:
    st.error("❌ Configura CLIENT_ID y CLIENT_SECRET en Streamlit Secrets.")
    st.stop()

if not code:
    st.markdown("### 🔐 Inicia sesión con Spotify para continuar")
    st.markdown(f"[👉 Login con Spotify]({AUTH_URL})")
    st.stop()

# ——— TOKEN EXCHANGE ———
st.info("🔁 Intercambiando código por token...")
b64 = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
resp = requests.post(
    TOKEN_URL,
    headers={"Authorization": f"Basic {b64}"},
    data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI}
)
if resp.status_code != 200:
    st.error("❌ Error al obtener token:")
    st.json(resp.json())
    st.stop()

token = resp.json()["access_token"]
sp = spotipy.Spotify(auth=token)
st.success("✅ Autenticado. Cargando historial…")

# ——— FUNCIONES ———
@st.cache_data
# Función mejorada para obtener audio-features desde AcousticBrainz
# con fallback de búsqueda de ISRC y logs en la UI.
def get_acousticbrainz_features(track_id: str, track_name: str, artist_name: str) -> dict:
    """
    1. Obtiene ISRC de Spotify (sp.track). Si falla, busca con sp.search.
    2. Busca MBID en MusicBrainz por ISRC.
    3. Obtiene high-level de AcousticBrainz.
    """
    # 1. Obtener ISRC
    try:
        tr = sp.track(track_id)
        isrc = tr.get("external_ids", {}).get("isrc")
        if not isrc:
            # Fallback: búsqueda por nombre y artista
            query = f'track:{track_name} artist:{artist_name}'
            results = sp.search(q=query, type="track", limit=1)
            items = results.get("tracks", {}).get("items", [])
            if items:
                isrc = items[0].get("external_ids", {}).get("isrc")
    except Exception as e:
        st.warning(f"Error al obtener ISRC para '{track_name}': {e}")
        return {}

    if not isrc:
        st.warning(f"No se encontró ISRC para '{track_name}' de {artist_name}.")
        return {}
    st.write(f"✅ ISRC {isrc} para '{track_name}'")

    # 2. MusicBrainz: obtener MBID
    mb_headers = {
        "User-Agent": "TuHuellaEmocionalSonora/1.0 (youremail@example.com)",
        "Accept": "application/json"
    }
    mb_params = {"query": f"isrc:{isrc}", "fmt": "json"}
    mb_resp = requests.get("https://musicbrainz.org/ws/2/recording", headers=mb_headers, params=mb_params)
    if mb_resp.status_code != 200:
        st.warning(f"MusicBrainz error {mb_resp.status_code} para ISRC {isrc}.")
        return {}
    recs = mb_resp.json().get("recordings", [])
    if not recs:
        st.warning(f"Ninguna grabación en MusicBrainz para ISRC {isrc}.")
        return {}
    mbid = recs[0]["id"]

    # 3. AcousticBrainz: high-level
    ab_headers = {"Accept": "application/json"}
    ab_resp = requests.get(f"https://acousticbrainz.org/api/v1/{mbid}/high-level", headers=ab_headers)
    if ab_resp.status_code != 200:
        st.warning(f"AcousticBrainz error {ab_resp.status_code} para MBID {mbid}.")
        return {}
    ab_json = ab_resp.json()
    high = ab_json.get("highlevel", {})
    rhythm = ab_json.get("rhythm", {})
    return {
        "danceability": high.get("danceability", {}).get("value"),
        "energy": high.get("energy", {}).get("value"),
        "valence": high.get("valence", {}).get("value"),
        "tempo": rhythm.get("bpm", {}).get("value")
    }

# ——— DATA & ANÁLISIS ———
items = sp.current_user_recently_played(limit=50)["items"]
records = []
for t in items:
    track_id = t["track"]["id"]
    name = t["track"]["name"]
    artist = t["track"]["artists"][0]["name"]
    played_at = t["played_at"]
    feats = get_acousticbrainz_features(track_id, name, artist)
    records.append({
        "track": name,
        "artist": artist,
        "played_at": played_at,
        **feats
    })

df = pd.DataFrame(records)
df["played_at"] = pd.to_datetime(df["played_at"])
df["date"] = df["played_at"].dt.date

# Estados emocionales
conds = [df.valence >= 0.7, (df.valence >= 0.4) & (df.valence < 0.7), df.valence < 0.4]
df["state"] = np.select(conds, ["Feliz", "Neutral", "Triste"], default="Desconocido")

# ——— VISUALIZACIONES ———
st.subheader("🎶 Últimas 50 canciones con audio-features de AcousticBrainz")
st.dataframe(df)

# Evolución diaria
st.subheader("📈 Evolución emocional diaria")
daily = df.groupby("date")[['valence','energy','danceability']].mean().reset_index()
st.plotly_chart(px.line(daily, 'date', 'valence', title='Valence diaria'))

# Radar
st.subheader("🕸️ Radar estados emocionales")
radar = df.groupby('state')[['valence','energy','danceability']].mean().reset_index()
st.plotly_chart(px.line_polar(radar, r='valence', theta='state', line_close=True, title='Perfil emocional'))

# PCA
st.subheader("📊 Clusters de días (PCA)")
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
kmeans = KMeans(3, random_state=42).fit(daily[['valence','energy']])
daily['cluster'] = kmeans.labels_
pca = PCA(2).fit_transform(daily[['valence','energy']])
daily['pca1'], daily['pca2'] = pca[:,0], pca[:,1]
st.plotly_chart(px.scatter(daily, 'pca1', 'pca2', color=daily.cluster.astype(str), title='PCA clusters'))

# Reflexión
st.subheader("🧠 Reflexión rápida")
avg = daily.valence.mean()
msg = "🎉 Semana alegre" if avg>0.6 else ("😌 Semana equilibrada" if avg>0.4 else "🌧️ Semana introspectiva")
st.info(msg)

# Playlist sugerida
st.subheader("🎼 Playlist sugerida")
today_cluster = daily.iloc[-1].cluster
labels = {0:'épico',1:'relajado',2:'emocional'}
st.markdown(f"Hoy un día **{labels[today_cluster]}**, top tracks:")
for _,r in df[df.date==df.date.max()].nlargest(5,'valence').iterrows():
    st.write(f"🎵 {r.track} - {r.artist} (Valence: {r.valence:.2f})")
