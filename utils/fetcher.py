from yt_dlp import YoutubeDL
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from config import SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, ydl_opts, format_time

spotify = None
if SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET:
    auth_manager = SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET)
    spotify = spotipy.Spotify(auth_manager=auth_manager)

class MusicFetcher:
    """Clase encargada de interpretar queries (YouTube, Spotify, Texto) y devolver canciones."""
    
    @staticmethod
    async def fetch(query, requester_name, loop):
        songs = []
        
        # 1. Manejo de URLs de Spotify
        if "spotify.com" in query and spotify:
            try:
                if "track" in query:
                    track = await loop.run_in_executor(None, spotify.track, query)
                    search_query = f"{track['name']} {track['artists'][0]['name']}"
                    yt_result = await MusicFetcher._search_youtube(search_query, loop)
                    if yt_result: songs.append(MusicFetcher._format_song(yt_result, requester_name))
                
                elif "playlist" in query:
                    playlist = await loop.run_in_executor(None, spotify.playlist_tracks, query)
                    for item in playlist['items']:
                        track = item.get('track')
                        if not track: continue
                        search_query = f"{track['name']} {track['artists'][0]['name']}"
                        yt_result = await MusicFetcher._search_youtube(search_query, loop)
                        if yt_result: songs.append(MusicFetcher._format_song(yt_result, requester_name))
                return songs
                
            except spotipy.exceptions.SpotifyException as e:
                if e.http_status == 401:
                    return "RESTRICTED"
                print(f"Error de Spotify: {e}")
                return []
            except Exception as e:
                print(f"Error general procesando Spotify: {e}")
                return []

        # 2. Manejo de Texto y URLs de YouTube
        ydl = YoutubeDL(ydl_opts)
        try:
            if not query.startswith("http"):
                query = f"ytsearch:{query}"
                
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(query, download=False))
            
            if 'entries' in info:
                for entry in info['entries']:
                    if entry:
                        songs.append(MusicFetcher._format_song(entry, requester_name))
                if query.startswith("ytsearch:"):
                    return [songs[0]] if songs else []
            else:
                songs.append(MusicFetcher._format_song(info, requester_name))
                
            return songs
        except Exception as e:
            print(f"Error procesando YouTube/Texto: {e}")
            return []

    @staticmethod
    async def _search_youtube(query, loop):
        ydl_search = ydl_opts.copy()
        ydl_search['noplaylist'] = True
        ydl = YoutubeDL(ydl_search)
        try:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(f"ytsearch1:{query}", download=False))
            if 'entries' in info and info['entries']:
                return info['entries'][0]
        except Exception:
            pass
        return None

    @staticmethod
    def _format_song(info, requester):
        duration = info.get('duration')
        try: duration_sec = int(duration) if duration else 0
        except: duration_sec = 0

        thumbnail_url = ''
        if info.get('thumbnails'):
            thumbnail_url = info['thumbnails'][-1].get('url', '')
        
        if not thumbnail_url:
            thumbnail_url = info.get('thumbnail', '')

        return {
            'title': info.get('title', 'Desconocido'),
            'url': info.get('webpage_url', info.get('url')),
            'duration_str': format_time(duration_sec) if duration_sec > 0 else 'Stream',
            'duration_sec': duration_sec,
            'thumbnail': thumbnail_url,
            'requester': requester
        }