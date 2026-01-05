import os
import random
import asyncio
import discord
import aiohttp
from discord.ext import commands
from yt_dlp import YoutubeDL
from dotenv import load_dotenv
import json
from discord.utils import get
import asyncio
from discord.ext import tasks
import sys         # <-- Añadido para el reinicio
import subprocess  # <-- Añadido para ejecutar pip

# Cargar variables de entorno
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Configuración inicial
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='-', intents=intents)

queues = {}         # Diccionario para almacenar las colas de reproducción por servidor
current_songs = {}  # Almacena la canción actual por servidor
voice_timeout = {}  # Diccionario para controlar timeouts por servidor

# Bibliotecas a monitorear para actualizaciones
LIBS_TO_UPDATE = ['yt-dlp', 'discord.py', 'PyNaCl']

# Diccionario para alias de comandos
command_aliases = {
    'play': ['p', 'reproducir'],
    'pause': ['pausa', 'stop'],
    'resume': ['continuar', 'reanudar', 'unpause'],
    'stopit': ['parar', 'terminar', 'stp'],
    'disconnect': ['desconectar', 'leave', 'salir', 'dc'],
    'nowplaying': ['np', 'current', 'actual'],
    'queue': ['lista', 'colas', 'q'],
    'shuffle': ['random', 'mezclar'],
    'remove': ['eliminar', 'delete', 'quitar'],
    'helpme': ['ayuda', 'comandos']
}

# Configuración de yt-dlp (Optimizada para playlists)
ydl_opts = {
    'format': 'bestaudio[ext=opus]/bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'noplaylist': False,
    'extract_flat': 'in_playlist',
    'source_address': '0.0.0.0'
}

# Opciones de FFmpeg (Sin cambios)
ffmpeg_options = {
    'options': '-vn -filter:a "volume=0.1" -b:a 128k -threads 4 -loglevel error',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 2 -analyzeduration 0 -probesize 32k -fflags +nobuffer+fastseek+discardcorrupt'
}

# Cargar o crear archivo de configuración
def load_config():
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        default_config = {
            'aliases': command_aliases,
            'join_sound': 'sounds/join.mp3',
            'leave_sound': 'sounds/leave.mp3'
        }
        save_config(default_config)
        return default_config

def save_config(config):
    with open('config.json', 'w') as f:
        json.dump(config, f, indent=4)

config = load_config()
command_aliases = config.get('aliases', command_aliases)

# Verificar y crear carpetas necesarias
if not os.path.exists('sounds'):
    os.makedirs('sounds')

# Función para buscar y descargar música (maneja playlists)
async def search_and_download(query):
    loop = bot.loop
    
    ydl_search_opts = ydl_opts.copy()
    ydl_search_opts['noplaylist'] = True
    ydl_url_opts = ydl_opts.copy()

    with YoutubeDL(ydl_url_opts) as ydl:
        try:
            info = await loop.run_in_executor(
                None, lambda: ydl.extract_info(query, download=False)
            )
        except Exception:
            try:
                with YoutubeDL(ydl_search_opts) as ydl_search:
                    info_search = await loop.run_in_executor(
                        None, lambda: ydl_search.extract_info(f"ytsearch:{query}", download=False)
                    )
                if 'entries' in info_search and info_search['entries']:
                    return [info_search['entries'][0]]
                else:
                    return None
            except Exception as e:
                print(f"Error en búsqueda: {e}")
                return None

    if 'entries' in info:
        return info['entries']
    else:
        return [info]

# Función para reproducir la siguiente canción en la cola
# Función para reproducir la siguiente canción en la cola (Embed MEJORADO)
async def play_next(ctx):
    if ctx.guild.id in voice_timeout:
        del voice_timeout[ctx.guild.id]

    if not queues.get(ctx.guild.id) or len(queues[ctx.guild.id]) == 0:
        await ctx.send("ℹ️ No hay más canciones en la cola.")
        return

    voice_client = ctx.voice_client
    if not voice_client or not voice_client.is_connected():
        return

    try:
        if len(queues[ctx.guild.id]) > 1:
            next_song = queues[ctx.guild.id][1]
            asyncio.create_task(preload_song(next_song['url']))

        song = queues[ctx.guild.id].pop(0)
        current_songs[ctx.guild.id] = song
        
        with YoutubeDL(ydl_opts) as ydl:
            info = await bot.loop.run_in_executor(
                None, lambda: ydl.extract_info(song['url'], download=False)
            )
            stream_url = info['url'] 

            source = discord.FFmpegPCMAudio(
                stream_url,
                **ffmpeg_options
            )

            # --- INICIO DE LA SECCIÓN MODIFICADA ---
            embed = discord.Embed(
                title="🎵 Reproduciendo ahora",
                url=song['url'],
                description=f"**[{song['title']}]({song['url']})**",
                color=discord.Color.green()
            )
            
            # Añadir la miniatura (thumbnail) si existe
            if song.get('thumbnail'):
                embed.set_thumbnail(url=song['thumbnail'])
            
            # Añadir la duración
            duration_str = song.get('duration', 'Desconocida')
            embed.add_field(name="Duración", value=duration_str, inline=True)
            
            # Añadir quién la solicitó
            requester = song.get('requester', 'Desconocido')
            embed.add_field(name="Solicitado por", value=requester, inline=True)
            
            await ctx.send(embed=embed)
            # --- FIN DE LA SECCIÓN MODIFICADA ---

            def after_playing(error):
                if error:
                    print(f"Error en after_playing: {error}")
                asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)

            if voice_client.is_playing():
                voice_client.stop()

            voice_client.play(source, after=after_playing)

    except Exception as e:
        print(f"Error crítico en play_next: {e}")
        await ctx.send("⚠️ Error al reproducir la canción. Saltando...")
        await play_next(ctx)

async def preload_song(url):
    try:
        with YoutubeDL(ydl_opts) as ydl:
            await asyncio.to_thread(ydl.extract_info, url, download=False)
    except Exception as e:
        print(f"Error en precarga: {e}")

async def check_empty_voice(guild):
    try:
        voice_client = guild.voice_client
        
        if not voice_client or not voice_client.is_connected():
            voice_timeout.pop(guild.id, None)
            return

        human_members = [m for m in voice_client.channel.members if not m.bot]
        
        if not human_members:
            current_time = asyncio.get_event_loop().time()
            
            if guild.id not in voice_timeout:
                voice_timeout[guild.id] = current_time
                return
            
            if (current_time - voice_timeout[guild.id]) >= 3:
                try:
                    if voice_client.is_playing():
                        voice_client.stop()
                    
                    if os.path.exists(config['leave_sound']):
                        def after_playing(error):
                            coro = safe_disconnect(guild)
                            fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
                            try:
                                fut.result()
                            except:
                                pass
                        
                        sound = discord.FFmpegPCMAudio(config['leave_sound'])
                        voice_client.play(sound, after=after_playing)
                    else:
                        await safe_disconnect(guild)
                
                except Exception as e:
                    print(f"Error durante desconexión: {e}")
                    await safe_disconnect(guild)
        
        else:
            voice_timeout.pop(guild.id, None)
    
    except Exception as e:
        print(f"Error crítico en check_empty_voice: {e}")
        voice_timeout.pop(guild.id, None)

async def safe_disconnect(guild):
    try:
        voice_client = guild.voice_client
        if voice_client and voice_client.is_connected():
            await voice_client.disconnect()
    except:
        pass
    
    queues.pop(guild.id, None)
    current_songs.pop(guild.id, None)
    voice_timeout.pop(guild.id, None)

def format_time(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes}:{seconds:02d}"

def create_progress_bar(position, duration, length=15):
    if duration <= 0:
        return ""
    
    progress = min(position / duration, 1.0)
    filled = int(progress * length)
    bar = "▬" * filled + "🔘" + "▬" * (length - filled - 1)
    return f"`[{bar}]`"

# Comando para reproducir música
@bot.command(name='play', aliases=command_aliases.get('play', []))
async def play(ctx, *, query):
    if not ctx.author.voice:
        await ctx.send("❌ Debes estar en un canal de voz para usar este comando.")
        return
    
    voice_client = ctx.voice_client
    if not voice_client:
        voice_client = await ctx.author.voice.channel.connect()
        
        if os.path.exists(config['join_sound']):
            voice_client.play(discord.FFmpegPCMAudio(config['join_sound']))
            while voice_client.is_playing():
                await asyncio.sleep(1)
    
    try:
        await ctx.send(f"🔍 Buscando: `{query}`...")
        song_info_list = await search_and_download(query)
        
        if not song_info_list:
            await ctx.send("❌ No se pudo encontrar la canción o playlist.")
            return
            
        if ctx.guild.id not in queues:
            queues[ctx.guild.id] = []
            
        songs_added = 0
        for song_info in song_info_list:
            if not song_info:
                continue

            webpage_url = song_info.get('webpage_url', song_info.get('url'))
            duration_sec = song_info.get('duration', 0)
            
            song_data = {
                'title': song_info.get('title', 'Título desconocido'),
                'url': webpage_url,
                'duration': format_time(duration_sec) if duration_sec > 0 else 'Desconocida',
                'duration_seconds': duration_sec,
                'thumbnail': song_info.get('thumbnail', ''),
                'requester': ctx.author.display_name
            }
            queues[ctx.guild.id].append(song_data)
            songs_added += 1

        if songs_added == 0:
             await ctx.send("❌ No se pudieron añadir canciones de la playlist.")
             return

        if songs_added == 1:
            await ctx.send(f"✅ Añadido a la cola: **{song_info_list[0].get('title', 'Título desconocido')}**")
        else:
            await ctx.send(f"✅ Añadidas **{songs_added}** canciones a la cola.")
        
        if not ctx.voice_client.is_playing():
            await play_next(ctx)
    except Exception as e:
        print(f"Error en comando play: {e}")
        await ctx.send(f"❌ Error al buscar: {e}")

# Comando para pausar
@bot.command(name='pause', aliases=command_aliases.get('pause', []))
async def pause(ctx):
    voice_client = ctx.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await ctx.send("⏸️ Música pausada.")
    else:
        await ctx.send("ℹ️ No hay música reproduciéndose actualmente.")

# Comando para saltar (corregido)
@bot.command(name='skip', aliases=['s'])
async def skip(ctx):
    voice_client = ctx.voice_client
    
    if not voice_client or not voice_client.is_connected() or not voice_client.is_playing():
        await ctx.send("⚠️ No hay nada reproduciéndose.")
        return

    queue_is_empty = not (ctx.guild.id in queues and len(queues[ctx.guild.id]) > 0)

    voice_client.stop()
    
    if not queue_is_empty:
        await ctx.send("⏭️ Canción saltada.")

# Comando para reanudar
@bot.command(name='resume', aliases=command_aliases.get('resume', []))
async def resume(ctx):
    voice_client = ctx.voice_client
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await ctx.send("▶️ Música reanudada.")
    else:
        await ctx.send("ℹ️ La música no está pausada o no hay música en la cola.")

# Comando para detener y limpiar la cola
@bot.command(name='stopit', aliases=command_aliases.get('stopit', []))
async def stop(ctx):
    voice_client = ctx.voice_client
    if voice_client:
        if ctx.guild.id in queues:
            queues[ctx.guild.id].clear()
        if voice_client.is_playing():
            voice_client.stop()
        await ctx.send("⏹️ Música detenida y cola limpiada.")

# Comando para desconectar
# Comando para desconectar (CORREGIDO)
@bot.command(name='disconnect', aliases=command_aliases.get('disconnect', []))
async def disconnect(ctx):
    voice_client = ctx.voice_client
    
    if voice_client and voice_client.is_connected():
        # Limpiar estado primero
        if ctx.guild.id in queues:
            queues[ctx.guild.id].clear()
        if voice_client.is_playing():
            voice_client.stop()
            
        # Enviar el mensaje de despedida ANTES de la lógica de desconexión
        await ctx.send("👋 Desconectando del canal de voz...")

        if os.path.exists(config['leave_sound']):
            # Función callback que se ejecuta DESPUÉS de que el sonido termine
            def after_playing(error):
                if error:
                    print(f"Error en el sonido de salida: {error}")
                
                # Usar run_coroutine_threadsafe para llamar a la corutina 'safe_disconnect'
                # ya que 'after' se ejecuta en un hilo diferente.
                coro = safe_disconnect(ctx.guild)
                fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
                try:
                    fut.result() # Esperar a que la desconexión termine
                except Exception as e:
                    print(f"Error al ejecutar safe_disconnect desde after_playing: {e}")

            try:
                # Intentar reproducir el sonido y pasarle la función 'after'
                source = discord.FFmpegPCMAudio(config['leave_sound'])
                voice_client.play(source, after=after_playing)
            except Exception as e:
                print(f"Error al reproducir sonido de salida, desconectando igualmente: {e}")
                # Si falla la reproducción del sonido, desconectar de todas formas
                await safe_disconnect(ctx.guild)
        
        else:
            # Si no hay sonido de salida, desconectar directamente
            await safe_disconnect(ctx.guild) 
    
    else:
        await ctx.send("ℹ️ El bot no está conectado a un canal de voz.")

# Comando para mostrar la canción actual
@bot.command(name='nowplaying', aliases=command_aliases.get('nowplaying', []))
async def nowplaying(ctx):
    voice_client = ctx.voice_client
    
    if not voice_client or not voice_client.is_playing():
        await ctx.send("ℹ️ No hay música reproduciéndose actualmente.")
        return
    
    song = current_songs.get(ctx.guild.id)
    if not song:
        await ctx.send("ℹ️ No se pudo obtener información de la canción actual.")
        return
    
    try:
        duration = song.get('duration_seconds', 0)
        
        embed = discord.Embed(
            title="🎵 Reproduciendo ahora",
            url=song['url'],
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=song.get('thumbnail', ''))
        embed.add_field(name="Canción", value=f"[{song['title']}]({song['url']})", inline=False)
        
        if duration > 0:
            embed.add_field(
                name="Duración",
                value=f"{format_time(duration)}",
                inline=False
            )
        
        embed.set_footer(text=f"Solicitado por: {song.get('requester', 'Desconocido')}")
        await ctx.send(embed=embed)
        
    except Exception as e:
        print(f"Error en nowplaying: {e}")
        await ctx.send("ℹ️ Reproduciendo: **" + song['title'] + "**")

# Comando para mostrar la cola
@bot.command(name='queue', aliases=['q'])
async def queue(ctx):
    if ctx.guild.id in queues and len(queues[ctx.guild.id]) > 0:
        page_size = 15
        queue_list = "\n".join(
            [f"{i+1}. {song['title']}" for i, song in enumerate(queues[ctx.guild.id][:page_size])]
        )
        
        embed = discord.Embed(
            title=f"🎶 Cola de reproducción ({len(queues[ctx.guild.id])} canciones)",
            description=queue_list,
            color=discord.Color.blue()
        )
        if len(queues[ctx.guild.id]) > page_size:
             embed.set_footer(text=f"... y {len(queues[ctx.guild.id]) - page_size} más.")
        await ctx.send(embed=embed)
    else:
        await ctx.send("ℹ️ La cola está vacía.")

# Comando para mezclar la cola
@bot.command(name='shuffle', aliases=command_aliases.get('shuffle', []))
async def shuffle(ctx):
    if ctx.guild.id in queues and len(queues[ctx.guild.id]) > 0:
        random.shuffle(queues[ctx.guild.id])
        await ctx.send("🔀 Cola mezclada aleatoriamente.")
    else:
        await ctx.send("ℹ️ No hay suficientes canciones en la cola para mezclar.")

# Comando para eliminar una canción de la cola
@bot.command(name='remove', aliases=command_aliases.get('remove', []))
async def remove(ctx, index: int):
    if ctx.guild.id in queues and 0 < index <= len(queues[ctx.guild.id]):
        removed_song = queues[ctx.guild.id].pop(index - 1)
        await ctx.send(f"❌ Eliminada de la cola: **{removed_song['title']}**")
    else:
        await ctx.send("ℹ️ Índice inválido o cola vacía.")

# Comando para ayuda
@bot.command(name='helpme', aliases=command_aliases.get('helpme', []))
async def help_command(ctx):
    embed1 = discord.Embed(
        title="🎵 Ayuda del Bot de Música",
        description="Lista de comandos disponibles (también puedes usar los alias):",
        color=discord.Color.red()
    )
    
    commands_info = {
        '**play [query/url/playlist_url]**': "Reproduce una canción, playlist o añádela a la cola",
        '**pause**': "Pausa la música actual",
        '**resume**': "Reanuda la música pausada",
        '**stopit**': "Detiene la música y limpia la cola",
        '**disconnect**': "Desconecta el bot del canal de voz",
        '**nowplaying**': "Muestra la canción que se está reproduciendo",
        '**queue**': "Muestra la cola de reproducción actual",
        '**shuffle**': "Mezcla aleatoriamente la cola de reproducción",
        '**remove [número]**': "Elimina una canción de la cola por su número",
        '**helpme**': "Muestra este mensaje de ayuda"
    }
    
    for cmd, desc in commands_info.items():
        embed1.add_field(name=f"-{cmd}", value=desc, inline=True)
    
    embed1.set_footer(text="También puedes usar alias para estos comandos.")
    await ctx.send(embed=embed1)

    embed2 = discord.Embed(
        title="🎵 Ayuda del Bot de Música",
        description="Lista de comandos disponibles (también puedes usar los alias):",
        color=discord.Color.red()
    )
    
    alias_info = {
        '**PLAY**': 'p - reproducir',
        '**PAUSE**': 'ps - pausa',
        '**RESUME**': 'r - continuar - reanudar - unpause',
        '**STOPIT**': 'stp - parar - terminar - stop',
        '**DISCONNECT**': 'dc - desconectar - leave - salir',
        '**NOWPLAYING**': 'np - current - actual',
        '**QUEUE**': 'q - lista - cola',
        '**SHUFFLE**': 'rnd - random - mezclar',
        '**REMOVE**': 'rm - eliminar - delete - quitar',
        '**HELPME**': 'hm - ayuda - comandos'
    }
    
    for cmd, alias in alias_info.items():
        embed2.add_field(
            name=cmd,
            value=alias,
            inline=True
        )
    
    embed2.set_footer(text="También puedes usar alias para estos comandos.")
    await ctx.send(embed2)

# Comando para añadir alias
@bot.command(name='addalias')
@commands.has_permissions(administrator=True)
async def add_alias(ctx, command: str, alias: str):
    if command.lower() in command_aliases:
        if alias.lower() not in command_aliases[command.lower()]:
            command_aliases[command.lower()].append(alias.lower())
            config['aliases'] = command_aliases
            save_config(config)
            await ctx.send(f"✅ Alias '{alias}' añadido para el comando '{command}'.")
        else:
            await ctx.send("ℹ️ Este alias ya existe para este comando.")
    else:
        await ctx.send("❌ Comando no válido.")

# Tarea para revisar si el canal de voz está vacío
@tasks.loop(seconds=5)
async def voice_check_task():
    for guild in bot.guilds:
        try:
            await check_empty_voice(guild)
        except Exception as e:
            print(f"Error en voice_check_task para {guild.name}: {e}")
            voice_timeout.pop(guild.id, None)

# --- INICIO DE NUEVA FUNCIONALIDAD: Auto-Update Task ---
@tasks.loop(hours=1)
async def update_check_task():
    print("[Auto-Update] Ejecutando revisión de actualizaciones...")

    # 1. Comprobar si el bot está activo en algún canal de voz
    is_active = False
    for guild in bot.guilds:
        if guild.voice_client and guild.voice_client.is_connected():
            is_active = True
            break
    
    if is_active:
        print("[Auto-Update] El bot está activo en un canal de voz. Omitiendo revisión.")
        return

    # 2. Si está inactivo, buscar actualizaciones (en un hilo)
    print("[Auto-Update] El bot está inactivo. Buscando actualizaciones de paquetes...")
    try:
        # sys.executable es la ruta al python.exe actual
        cmd = [sys.executable, '-m', 'pip', 'list', '--outdated']
        
        # Usamos asyncio.to_thread para ejecutar el comando síncrono
        process = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, check=True)
        output = process.stdout
        
        needs_update = False
        for lib in LIBS_TO_UPDATE:
            if lib in output:
                print(f"[Auto-Update] Actualización encontrada para: {lib}")
                needs_update = True
                break

        if not needs_update:
            print("[Auto-Update] Todas las bibliotecas están al día.")
            return

        # 3. Instalar actualizaciones (en un hilo)
        print("[Auto-Update] Instalando actualizaciones...")
        install_cmd = [sys.executable, '-m', 'pip', 'install', '--upgrade'] + LIBS_TO_UPDATE
        
        await asyncio.to_thread(subprocess.run, install_cmd, capture_output=True, text=True, check=True)
        
        print("[Auto-Update] Actualizaciones instaladas. Reiniciando el bot...")

        # 4. Reiniciar el bot
        await bot.close()  # Cerrar la conexión de Discord limpiamente
        bot.run(TOKEN)
        

    except subprocess.CalledProcessError as e:
        print(f"[Auto-Update] Error: Fallo al revisar/instalar actualizaciones. Error: {e.stderr}")
    except Exception as e:
        print(f"[Auto-Update] Error: Ocurrió un error inesperado: {e}")

@update_check_task.before_loop
async def before_update_check():
    await bot.wait_until_ready() # Esperar a que el bot esté listo
# --- FIN DE NUEVA FUNCIONALIDAD ---

# --- CONFIGURACIÓN DE MONITOR DE ESTADO (UPTIME KUMA) ---
UPTIME_KUMA_URL = "http://192.168.1.89:3001/api/push/vKnIkrymMwYfY8W1Gkl5ZoveUKyVFaVW?status=up&msg=OK&ping="  # Ejemplo: https://kuma.midominio.com/api/push/xxxxx...

@tasks.loop(seconds=20)
async def uptime_heartbeat():
    """Envía una señal a Uptime Kuma cada 60 segundos para indicar que el bot está vivo."""
    if not UPTIME_KUMA_URL or "PEGA_AQUI" in UPTIME_KUMA_URL:
        print("[Monitor] URL de Uptime Kuma no configurada.")
        return

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(UPTIME_KUMA_URL) as response:
                if response.status == 200:
                    # Si quieres menos spam en la consola, comenta la siguiente línea
                    # print(f"[Monitor] Latido enviado correctamente (Status: {response.status})")
                    pass
                else:
                    print(f"[Monitor] Error al enviar latido: Status {response.status}")
    except Exception as e:
        print(f"[Monitor] Fallo de conexión con Uptime Kuma: {e}")

@uptime_heartbeat.before_loop
async def before_heartbeat():
    await bot.wait_until_ready()
# --------------------------------------------------------

# Evento cuando el bot está listo
@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user.name}')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="-helpme"))
    voice_check_task.start()
    update_check_task.start() # <-- Iniciar la nueva tarea
    uptime_heartbeat.start()

# Manejo de errores
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Comando no encontrado. Usa `-helpme` para ver la lista de comandos.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Faltan argumentos. Usa `-helpme {ctx.command.name}` para más información.")
    else:
        await ctx.send(f"❌ Ocurrió un error: {str(error)}")
        print(f"Error en comando {ctx.command}: {error}")

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    
    guild = member.guild
    
    if guild.voice_client:
        await check_empty_voice(guild)

# Iniciar el bot
if __name__ == "__main__":
    bot.run(TOKEN)