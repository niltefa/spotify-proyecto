# Tu Huella Emocional Sonora - Versión OAuth adaptada a Streamlit Cloud (sin input manual)

import pandas as pd
import numpy as np
import spotipy
import requests
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
import plotly.express as px
import streamlit as st
import datetime as dt
import openai
import os
import base64

# ---------- STREAMLIT UI ----------
st.title("🎧 Tu Huella Emocional Sonora")

# Obtener CLIENT_ID y SECRET desde input si no están como variables de entorno
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

if CLIENT_ID is None or CLIENT_SECRET is None:
    st.warning("🔐 Por favor, introduce tus credenciales de Spotify")
    CLIENT_ID = st.text_input("Client ID")
    CLIENT_SECRET = st.text_input("Client Secret", type="password")

REDIRECT_URI = "https://tu-musiquilla.streamlit.app/"
SCOPE = "user-read-recently-played"
TOKEN_URL = "https://accounts.spotify.com/api/token"

# Generar AUTH_URL solo si ya se tiene client_id
AUTH_URL = f"https://accounts.spotify.com/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={REDIRECT_URI}&scope={SCOPE}" if CLIENT_ID else ""

query_params = st.query_params
code = query_params.get("code", [None])[0]

if code is None:
    if CLIENT_ID and CLIENT_SECRET:
        st.markdown("### 🔐 Para comenzar, inicia sesión en Spotify")
        st.markdown(f"[👉 Iniciar sesión con Spotify]({AUTH_URL})")
    else:
        st.info("Introduce tus credenciales para generar el enlace de autenticación.")
else:
    # ---------- INTERCAMBIAR CÓDIGO POR TOKEN ----------
    st.write("🔁 Intercambiando código por token...")
    auth_str = f"{CLIENT_ID}:{CLIENT_SECRET}"
    b64_auth_str = base64.b64encode(auth_str.encode()).decode()

    headers = {
        "Authorization": f"Basic {b64_auth_str}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI
    }

    response = requests.post(TOKEN_URL, headers=headers, data=data)
    if response.status_code != 200:
        st.error("❌ Error al obtener el token de acceso.")
        st.json(response.json())
    else:
        access_token = response.json()["access_token"]
        sp = spotipy.Spotify(auth=access_token)

        st.success("✅ Autenticación completada. Cargando historial musical...")
        results = sp.current_user_recently_played(limit=100)
        data = []

        for item in results['items']:
            track = item['track']
            features = sp.audio_features(track['id'])[0]
            data.append({
                'track_name': track['name'],
                'artist': track['artists'][0]['name'],
                'played_at': item['played_at'],
                'valence': features['valence'],
                'energy': features['energy'],
                'danceability': features['danceability'],
                'tempo': features['tempo'],
                'id': track['id']
            })

        songs = pd.DataFrame(data)
        songs['played_at'] = pd.to_datetime(songs['played_at'])
        songs['date'] = songs['played_at'].dt.date

        # Clasificación emocional
        conditions = [
            (songs['valence'] >= 0.7),
            (songs['valence'] >= 0.4) & (songs['valence'] < 0.7),
            (songs['valence'] < 0.4)
        ]
        choices = ['Feliz', 'Neutral', 'Triste']
        songs['estado_emocional'] = np.select(conditions, choices, default='Desconocido')

        st.subheader("📊 Visualizaciones Emocionales")
        daily_mood = songs.groupby('date')[['valence', 'energy', 'danceability']].mean().reset_index()
        kmeans = KMeans(n_clusters=3, random_state=42)
        daily_mood['cluster'] = kmeans.fit_predict(daily_mood[['valence', 'energy']])

        fig1 = px.line(daily_mood, x='date', y='valence', color=daily_mood['cluster'].astype(str), title='Evolución emocional (valence)')
        st.plotly_chart(fig1)

        radar_df = songs.groupby('estado_emocional')[['valence', 'energy', 'danceability']].mean().reset_index()
        fig2 = px.line_polar(radar_df, r='valence', theta='estado_emocional', line_close=True, title='Radar de estados emocionales')
        st.plotly_chart(fig2)

        pca = PCA(n_components=2)
        components = pca.fit_transform(daily_mood[['valence', 'energy']])
        daily_mood['pca1'] = components[:, 0]
        daily_mood['pca2'] = components[:, 1]
        fig3 = px.scatter(daily_mood, x='pca1', y='pca2', color=daily_mood['cluster'].astype(str), title='Tipos de días musicales (PCA)')
        st.plotly_chart(fig3)

        st.subheader("🧠 Reflexión semanal")
        media_valence = daily_mood['valence'].mean()

        def reflexion_simple(media_val):
            if media_val > 0.6:
                return "🎉 Esta semana ha sido alegre y enérgica. ¡Buen ánimo musical!"
            elif media_val > 0.4:
                return "😌 Semana equilibrada emocionalmente. Algo de calma, algo de energía."
            else:
                return "🌧️ Ha sido una semana introspectiva. Tal vez música más tranquila o triste."

        st.info(reflexion_simple(media_valence))

        st.subheader("🎼 Playlist sugerida para hoy")
        latest_cluster = daily_mood.iloc[-1]['cluster']
        mood_labels = {0: 'épico', 1: 'relajado', 2: 'emocional'}
        st.markdown(f"Hoy parece un día **{mood_labels.get(latest_cluster, 'interesante')}**. Aquí tienes una selección basada en tu mood reciente:")

        top_songs = songs[songs['date'] == songs['date'].max()].sort_values(by='valence', ascending=False).head(5)
        for _, row in top_songs.iterrows():
            st.write(f"🎵 {row['track_name']} - {row['artist']} (Valence: {row['valence']:.2f})")