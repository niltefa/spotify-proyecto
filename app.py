import os
import base64
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import streamlit as st
import spotipy

# Herramientas de audio
import tempfile

def extract_local_features(preview_url: str) -> dict:
    """
    Descarga el preview de Spotify y extrae características con librosa:
    - tempo (BPM)
    - energy (RMS)
    - danceability (media del onset strength)
    - spectral_centroid (proxy de brillantez)
    """
    try:
        import librosa
    except ImportError:
        st.warning("librosa no está instalado: instala librosa para extracción local.")
        return {}

    if not preview_url:
        return {}

    # Descarga preview a archivo temporal
    r = requests.get(preview_url)
    if r.status_code != 200:
        return {}
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tmp.write(r.content)
    tmp.flush()

    # Carga audio
    y, sr = librosa.load(tmp.name, sr=None)

    # Tempo
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    # Energy (RMS)
    rms = np.mean(librosa.feature.rms(y=y))
    # Danceability proxy (onset strength)
    onset = librosa.onset.onset_strength(y=y, sr=sr)
    dance = float(np.mean(onset))
    # Brillo proxy (centroid)
    centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))

    return {
        "danceability": dance,
        "energy": rms,
        "valence": None,
        "tempo": tempo,
        "spectral_centroid": centroid
    }

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
st.set_page_config(page_title="🎧 Tu Huella Emocional Sonora")
st.title("🎧 Tu Huella Emocional Sonora")
code = st.experimental_get_query_params().get("code", [None])[0]

if not CLIENT_ID or not CLIENT_SECRET:
    st.error("❌ Configura CLIENT_ID y CLIENT_SECRET en Streamlit Secrets.")
    st.stop()
if not code:
    st.markdown("### 🔐 Inicia sesión con Spotify para continuar")
    st.markdown(f"[👉 Login con Spotify]({AUTH_URL})")
    st.stop()

# ——— TOKEN ———
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

token = resp.json().get("access_token")
sp = spotipy.Spotify(auth=token)
st.success("✅ Autenticado. Cargando historial…")

# ——— DATOS & EXTRACCIÓN ———
items = sp.current_user_recently_played(limit=50)["items"]
records = []

for t in items:
    tr = t["track"]
    track_id = tr["id"]
    name = tr["name"]
    artist = tr["artists"][0]["name"]
    played_at = t["played_at"]
    # Intento de preview local
    preview_url = tr.get("preview_url")
    feats = extract_local_features(preview_url)
    records.append({
        "track": name,
        "artist": artist,
        "played_at": played_at,
        **feats
    })

df = pd.DataFrame(records)
df["played_at"] = pd.to_datetime(df["played_at"])
df["date"] = df["played_at"].dt.date

# ——— VISUALIZACIÓN ———
st.subheader("🎶 Últimas 50 canciones con features locales")
st.dataframe(df)

st.subheader("📈 Evolución diaria (tempo)")
daily = df.groupby("date")[['tempo','energy','danceability']].mean().reset_index()
st.plotly_chart(px.line(daily, 'date', 'tempo', title='Tempo diario'))

st.subheader("🕸️ Radar energética")
radar = df[['energy','danceability','spectral_centroid']].mean().to_frame().T
radar['state'] = ['Global']
st.plotly_chart(px.line_polar(radar, r='energy', theta='state', line_close=True, title='Perfil energético'))

st.subheader("🧠 Reflexión rápida")
avg_tempo = daily['tempo'].mean()
msg = f"🎵 Tempo medio: {avg_tempo:.1f} BPM"
st.info(msg)

# Playlist simple
st.subheader("🎼 Playlist (preview)")
for _,r in df.nlargest(5, 'tempo').iterrows():
    st.write(f"🎵 {r['track']} - {r['artist']} (Tempo: {r['tempo']:.1f})")
