# Tu Huella Emocional Sonora - App Final

import os, base64, requests
import pandas as pd, numpy as np
import plotly.express as px
import streamlit as st
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
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

# ——— DATA & ANÁLISIS ———
# Spotify permite max 50 en recently_played
items = sp.current_user_recently_played(limit=50)["items"]

print(f"Recuperando {len(items)} canciones...")

st.subheader("🎶 Últimas 50 canciones reproducidas")
for i, t in enumerate(items, 1):
    name   = t["track"]["name"]
    artist = t["track"]["artists"][0]["name"]
    st.write(f"{i:2d}. **{name}** — {artist}")

records = []
for t in items:
    f = sp.audio_features(t["track"]["id"])[0]
    records.append({
        "track": t["track"]["name"],
        "artist": t["track"]["artists"][0]["name"],
        "played_at": t["played_at"],
        **{k: f[k] for k in ["valence","energy","danceability","tempo"]}
    })

df = pd.DataFrame(records)
df["played_at"] = pd.to_datetime(df["played_at"])
df["date"] = df["played_at"].dt.date
conds = [df.valence>=0.7, (df.valence>=0.4)&(df.valence<0.7), df.valence<0.4]
df["state"] = np.select(conds, ["Feliz","Neutral","Triste"], default="Desconocido")

daily = df.groupby("date")[['valence','energy','danceability']].mean().reset_index()
daily['cluster'] = KMeans(3,random_state=42).fit_predict(daily[['valence','energy']])

# ——— VISUALS ———
st.subheader("📈 Evolución emocional diaria")
st.plotly_chart(px.line(daily,'date','valence',color=daily.cluster.astype(str)))

st.subheader("🕸️ Radar estados emocionales")
radar = df.groupby('state')[['valence','energy','danceability']].mean().reset_index()
st.plotly_chart(px.line_polar(radar,r='valence',theta='state',line_close=True))

st.subheader("📊 Clusters de días (PCA)")
pca = PCA(2).fit_transform(daily[['valence','energy']])
daily['pca1'],daily['pca2']=pca[:,0],pca[:,1]
st.plotly_chart(px.scatter(daily,'pca1','pca2',color=daily.cluster.astype(str)))

st.subheader("🧠 Reflexión rápida")
avg=daily.valence.mean()
msg="🎉 Semana alegre" if avg>0.6 else ("😌 Semana equilibrada" if avg>0.4 else "🌧️ Semana introspectiva")
st.info(msg)

# ——— PLAYLIST ———
st.subheader("🎼 Playlist sugerida")
today_cluster=daily.iloc[-1].cluster
labels={0:'épico',1:'relajado',2:'emocional'}
st.markdown(f"Hoy un día **{labels[today_cluster]}**, top tracks:")
for _,r in df[df.date==df.date.max()].nlargest(5,'valence').iterrows():
    st.write(f"🎵 {r.track} - {r.artist} (Valence: {r.valence:.2f})")