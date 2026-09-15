import os
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# --- VARIABLES DE ENTORNO ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
SPOTIPY_CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
SPOTIPY_CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')

# --- CONFIGURACIONES DE TAREAS ---
UPTIME_KUMA_URL = os.getenv("UPTIME_KUMA", "")
LIBS_TO_UPDATE = ['yt-dlp', 'discord.py', 'PyNaCl', 'spotipy']

# --- CONFIGURACIONES ESTÁTICAS ---
ydl_opts = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'extract_flat': 'in_playlist',
    'source_address': '0.0.0.0'
}

# Opciones de FFmpeg
ffmpeg_options = {
    'options': '-vn -filter:a "volume=0.15" -b:a 128k -threads 4 -loglevel error',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 2 -analyzeduration 0 -probesize 32k -fflags +nobuffer+fastseek+discardcorrupt'
}

# --- FUNCIONES UTILITARIAS GLOBALES ---
def format_time(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes}:{seconds:02d}"