# Tu Huella Emocional Sonora - Proyecto Completo
# Requiere: spotipy, pandas, numpy, plotly, scikit-learn, streamlit, openai (opcional para reflexión GPT)

import pandas as pd
import numpy as np
import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
import plotly.express as px
import matplotlib.pyplot as plt
import streamlit as st
import datetime as dt
import openai

# Configurar API de OpenAI si se desea usar reflexiones GPT
# openai.api_key = 'TU_API_KEY_OPENAI'

# ---------- PARTE 1: Autenticación y Extracción de Datos ----------

st.title("🎧 Tu Huella Emocional Sonora")

with st.sidebar:
    st.header("🔐 Autenticación Spotify")
    client_id = st.text_input("Client ID", type="password")
    client_secret = st.text_input("Client Secret", type="password")
    redirect_uri = st.text_input("Redirect URI", value="http://localhost:8888/callback")
    fetch_data = st.button("Cargar historial musical")

if fetch_data and client_id and client_secret:
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope='user-read-recently-played'
    ))

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

    # Estado emocional simplificado
    conditions = [
        (songs['valence'] >= 0.7),
        (songs['valence'] >= 0.4) & (songs['valence'] < 0.7),
        (songs['valence'] < 0.4)
    ]
    choices = ['Feliz', 'Neutral', 'Triste']
    songs['estado_emocional'] = np.select(conditions, choices, default='Desconocido')

    # ---------- PARTE 2: Análisis y Visualización ----------

    st.subheader("📊 Visualizaciones Emocionales")

    daily_mood = songs.groupby('date')[['valence', 'energy', 'danceability']].mean().reset_index()

    # Clustering
    kmeans = KMeans(n_clusters=3, random_state=42)
    daily_mood['cluster'] = kmeans.fit_predict(daily_mood[['valence', 'energy']])

    # Timeline emocional
    fig1 = px.line(daily_mood, x='date', y='valence', color=daily_mood['cluster'].astype(str), title='Evolución emocional (valence)')
    st.plotly_chart(fig1)

    # Radar de emociones
    radar_df = songs.groupby('estado_emocional')[['valence', 'energy', 'danceability']].mean().reset_index()
    fig2 = px.line_polar(radar_df, r='valence', theta='estado_emocional', line_close=True, title='Radar de estados emocionales')
    st.plotly_chart(fig2)

    # PCA clustering
    pca = PCA(n_components=2)
    components = pca.fit_transform(daily_mood[['valence', 'energy']])
    daily_mood['pca1'] = components[:, 0]
    daily_mood['pca2'] = components[:, 1]
    fig3 = px.scatter(daily_mood, x='pca1', y='pca2', color=daily_mood['cluster'].astype(str), title='Tipos de días musicales (PCA)')
    st.plotly_chart(fig3)

    # ---------- PARTE 3: Recomendación y Reflexión ----------

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

    # Reflexión GPT opcional
    if st.checkbox("💬 Generar reflexión personalizada con GPT"):
        try:
            texto = f"Esta semana tu media de valencia fue {media_valence:.2f} y energía {daily_mood['energy'].mean():.2f}. Resume el estado emocional general en una frase corta."
            respuesta = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": texto}]
            )
            st.success("GPT dice: " + respuesta.choices[0].message['content'])
        except Exception as e:
            st.error("No se pudo generar la reflexión con GPT. Verifica tu API Key.")

    # ---------- PARTE 4: Playlist sugerida (básica) ----------

    st.subheader("🎼 Playlist sugerida para hoy")
    latest_cluster = daily_mood.iloc[-1]['cluster']
    mood_labels = {0: 'épico', 1: 'relajado', 2: 'emocional'}
    st.markdown(f"Hoy parece un día **{mood_labels.get(latest_cluster, 'interesante')}**. Aquí tienes una selección basada en tu mood reciente:")

    top_songs = songs[songs['date'] == songs['date'].max()].sort_values(by='valence', ascending=False).head(5)
    for _, row in top_songs.iterrows():
        st.write(f"🎵 {row['track_name']} - {row['artist']} (Valence: {row['valence']:.2f})")

else:
    st.warning("Introduce las credenciales de Spotify para comenzar.")