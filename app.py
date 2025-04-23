import os
import base64
import requests

import pandas as pd
import numpy as np
import plotly.express as px
import streamlit as st

from sklearn.cluster import KMeans
from sklearn.decomposition import PCA

import spotipy
from spotipy.exceptions import SpotifyException

# ——— CONFIG ———
CLIENT_ID     = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI  = "https://tu-musiquilla.streamlit.app/callback"
SCOPE         = "user-read-recently-played"

AUTH_URL = (
    f"https://accounts.spotify.com/authorize"
    f"?client_id={CLIENT_ID}"
    f"&response_type=code"
    f"&redirect_uri={REDIRECT_URI}"
    f"&scope={SCOPE}"
)
TOKEN_URL = "https://accounts.spotify.com/api/token"

# ——— UI ———
st.title("🎧 Tu Huella Emocional Sonora")

# Antes: st.experimental_get_query_params()
code = st.query_params.get("code", [None])[0]

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
    data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI
    }
)
if resp.status_code != 200:
    st.error("❌ Error al obtener token:")
    st.json(resp.json())
    st.stop()

token = resp.json()["access_token"]
sp = spotipy.Spotify(auth=token)
st.success("✅ Autenticado. Cargando historial…")

# ——— DATA & ANÁLISIS ———
try:
    items = sp.current_user_recently_played(limit=50)["items"]
except SpotifyException as e:
    st.error(f"❌ No se pudo cargar historial: {e}")
    st.stop()

# Filtrar solo pistas con ID válido (evita 403 en episodios, etc.)
tracks = [t for t in items if t.get("track") and t["track"].get("id")]
ids = [t["track"]["id"] for t in tracks]

# Obtener audio features en lote
features = sp.audio_features(ids)

records = []
for t, f in zip(tracks, features):
    if not f:
        continue
    records.append({
        "track": t["track"]["name"],
        "artist": t["track"]["artists"][0]["name"],
        "played_at": t["played_at"],
        **{k: f[k] for k in ["valence", "energy", "danceability", "tempo"]}
    })

df = pd.DataFrame(records)
df["played_at"] = pd.to_datetime(df["played_at"])
df["date"] = df["played_at"].dt.date

conds = [
    df.valence >= 0.7,
    (df.valence >= 0.4) & (df.valence < 0.7),
    df.valence < 0.4
]
df["state"] = np.select(conds, ["Feliz", "Neutral", "Triste"], default="Desconocido")

daily = df.groupby("date")[["valence", "energy", "danceability"]].mean().reset_index()
daily["cluster"] = KMeans(3, random_state=42).fit_predict(daily[["valence", "energy"]])

# ——— VISUALS ———
st.subheader("📈 Evolución emocional diaria")
st.plotly_chart(px.line(daily, x="date", y="valence",
                       color=daily.cluster.astype(str)))

st.subheader("🕸️ Radar estados emocionales")
radar = df.groupby("state")[["valence", "energy", "danceability"]].mean().reset_index()
st.plotly_chart(px.line_polar(radar, r="valence", theta="state", line_close=True))

st.subheader("📊 Clusters de días (PCA)")
pca_coords = PCA(2).fit_transform(daily[["valence", "energy"]])
daily["pca1"], daily["pca2"] = pca_coords[:, 0], pca_coords[:, 1]
st.plotly_chart(px.scatter(daily, x="pca1", y="pca2",
                          color=daily.cluster.astype(str)))

st.subheader("🧠 Reflexión rápida")
avg_val = daily.valence.mean()
msg = ("🎉 Semana alegre" if avg_val > 0.6
       else "😌 Semana equilibrada" if avg_val > 0.4
       else "🌧️ Semana introspectiva")
st.info(msg)

# ——— PLAYLIST ———
st.subheader("🎼 Playlist sugerida")
today_cluster = daily.iloc[-1].cluster
labels = {0: "épico", 1: "relajado", 2: "emocional"}
st.markdown(f"Hoy un día **{labels[today_cluster]}**, top tracks:")
for _, r in (
    df[df.date == df.date.max()]
    .nlargest(5, "valence")
    .iterrows()
):
    st.write(f"🎵 {r.track} - {r.artist} (Valence: {r.valence:.2f})")
