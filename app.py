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

# ——— ALTERNATIVA: AcousticBrainz ———

HEADERS_MB = {"User-Agent": "TuHuellaEmocionalSonora/1.0 (youremail@example.com)"}

@st.cache_data
 def get_acousticbrainz_features(track_id: str) -> dict:
    """
    Dado un track_id de Spotify:
      1. Obtiene ISRC vía sp.track
      2. Busca grabación en MusicBrainz por ISRC
      3. Recupera high-level desde AcousticBrainz
    """
    # 1. Obtener ISRC
    try:
        track = sp.track(track_id)
        isrc = track.get("external_ids", {}).get("isrc")
    except Exception:
        return {}

    if not isrc:
        return {}

    # 2. Consultar MusicBrainz
    mb_url = f"https://musicbrainz.org/ws/2/recording"
    mb_params = {"query": f"isrc:{isrc}", "fmt": "json"}
    mb_resp = requests.get(mb_url, headers=HEADERS_MB, params=mb_params)
    if mb_resp.status_code != 200:
        return {}
    mb_data = mb_resp.json()
    recordings = mb_data.get("recordings", [])
    if not recordings:
        return {}
    mbid = recordings[0]["id"]

    # 3. Obtener high-level de AcousticBrainz
    ab_url = f"https://acousticbrainz.org/api/v1/{mbid}/high-level"
    ab_resp = requests.get(ab_url)
    if ab_resp.status_code != 200:
        return {}
    ab_data = ab_resp.json()

    high = ab_data.get("highlevel", {})
    rhythm = ab_data.get("rhythm", {})

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
    feat = get_acousticbrainz_features(t["track"]["id"])
    records.append({
        "track": t["track"]["name"],
        "artist": t["track"]["artists"][0]["name"],
        "played_at": t["played_at"],
        **feat
    })
df = pd.DataFrame(records)
df["played_at"] = pd.to_datetime(df["played_at"])
df["date"] = df["played_at"].dt.date
# Clasificación de estados emocionales
conds = [
    df.valence >= 0.7,
    (df.valence >= 0.4) & (df.valence < 0.7),
    df.valence < 0.4
]
df["state"] = np.select(conds, ["Feliz", "Neutral", "Triste"], default="Desconocido")

# ——— VISUALIZACIONES ———
st.subheader("🎶 Últimas 50 canciones con audio-features de AcousticBrainz")
st.dataframe(df)
st.subheader("📈 Evolución emocional diaria")
daily = df.groupby("date")[['valence','energy','danceability']].mean().reset_index()
st.plotly_chart(px.line(daily, 'date','valence', color=daily.valence > 0.5))

# ... (resto de visualizaciones similares al original)
