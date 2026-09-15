import discord
from yt_dlp import YoutubeDL
from config import ydl_opts, ffmpeg_options

class GuildPlayer:
    """Administra el estado de reproducción de un servidor específico."""
    def __init__(self, bot, guild_id):
        self.bot = bot
        self.guild_id = guild_id
        self.queue = []
        self.current_song = None
        self.voice_client = None
        self.text_channel = None

    async def play_next(self):
        if not self.queue:
            self.current_song = None
            if self.text_channel:
                await self.text_channel.send("🏁 La cola de reproducción ha terminado.")
            return

        self.current_song = self.queue.pop(0)
        
        try:
            ydl_stream_opts = ydl_opts.copy()
            ydl_stream_opts['format'] = 'bestaudio/best'
            ydl_stream_opts['extract_flat'] = False
            
            with YoutubeDL(ydl_stream_opts) as ydl:
                info = await self.bot.loop.run_in_executor(None, lambda: ydl.extract_info(self.current_song['url'], download=False))
                stream_url = info['url']

            source = discord.FFmpegPCMAudio(stream_url, **ffmpeg_options)

            embed = discord.Embed(
                title="🎵 Reproduciendo ahora",
                description=f"**[{self.current_song['title']}]({self.current_song['url']})**",
                color=discord.Color.green()
            )
            if self.current_song['thumbnail']:
                embed.set_thumbnail(url=self.current_song['thumbnail'])
            embed.add_field(name="Duración", value=self.current_song['duration_str'], inline=True)
            embed.add_field(name="Pedido por", value=self.current_song['requester'], inline=True)
            
            if self.text_channel:
                await self.text_channel.send(embed=embed)

            def after_playing(error):
                if error: print(f"Error en reproducción: {error}")
                self.bot.loop.call_soon_threadsafe(lambda: self.bot.loop.create_task(self.play_next()))

            if self.voice_client.is_playing():
                self.voice_client.stop()

            self.voice_client.play(source, after=after_playing)

        except Exception as e:
            print(f"Error en motor de reproducción: {e}")
            if self.text_channel:
                await self.text_channel.send(f"⚠️ Error al reproducir **{self.current_song['title']}**. Saltando...")
            await self.play_next()