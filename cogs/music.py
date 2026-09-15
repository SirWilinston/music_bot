import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from utils.fetcher import MusicFetcher
from utils.player import GuildPlayer

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}

    def get_player(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if guild_id not in self.players:
            self.players[guild_id] = GuildPlayer(self.bot, guild_id)
        player = self.players[guild_id]
        player.voice_client = interaction.guild.voice_client
        player.text_channel = interaction.channel
        return player

    async def check_voice(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.voice:
            await interaction.response.send_message("❌ Debes estar en un canal de voz.", ephemeral=True)
            return False
            
        if not interaction.guild.voice_client:
            voice_client = await interaction.user.voice.channel.connect()
            
            # --- LÓGICA DE SONIDO DE ENTRADA ---
            join_sound = 'sounds/join.mp3'
            if os.path.exists(join_sound):
                voice_client.play(discord.FFmpegPCMAudio(join_sound))
                # Esperamos a que el sonido termine antes de permitir que la música arranque
                while voice_client.is_playing():
                    await asyncio.sleep(0.5)
                    
        return True

    # --- COMANDOS DE REPRODUCCIÓN ---

    @app_commands.command(name="play", description="Añade una canción o playlist al final de la cola.")
    async def play(self, interaction: discord.Interaction, query: str):
        if not await self.check_voice(interaction): return
        await interaction.response.defer()
        
        player = self.get_player(interaction)
        songs = await MusicFetcher.fetch(query, interaction.user.display_name, self.bot.loop)

        if songs == "RESTRICTED":
            return await interaction.followup.send("❌ No puedo leer esta playlist de Spotify. Es privada, colaborativa o generada automáticamente.")
        
        if not songs:
            return await interaction.followup.send("❌ No pude encontrar resultados para eso.")
            
        player.queue.extend(songs)
        
        if len(songs) == 1:
            await interaction.followup.send(f"✅ Añadido a la cola: **{songs[0]['title']}**")
        else:
            await interaction.followup.send(f"✅ Añadidas **{len(songs)}** canciones de la playlist a la cola.")

        if not player.voice_client.is_playing() and not player.current_song:
            await player.play_next()

    @app_commands.command(name="playnext", description="Añade una sola canción al inicio de la cola para ser la siguiente.")
    async def playnext(self, interaction: discord.Interaction, query: str):
        if not await self.check_voice(interaction): return
        await interaction.response.defer()
        
        player = self.get_player(interaction)
        songs = await MusicFetcher.fetch(query, interaction.user.display_name, self.bot.loop)
        
        if not songs:
            return await interaction.followup.send("❌ No pude encontrar resultados para eso.")
        
        if len(songs) > 1:
            return await interaction.followup.send("❌ El comando `/playnext` no permite playlists. Usa `/play`.")
            
        player.queue.insert(0, songs[0])
        await interaction.followup.send(f"⏭️ Siguiente en la cola: **{songs[0]['title']}**")

        if not player.voice_client.is_playing() and not player.current_song:
            await player.play_next()

    @app_commands.command(name="playnow", description="Reproduce una canción inmediatamente, saltando la actual.")
    async def playnow(self, interaction: discord.Interaction, query: str):
        if not await self.check_voice(interaction): return
        await interaction.response.defer()
        
        player = self.get_player(interaction)
        songs = await MusicFetcher.fetch(query, interaction.user.display_name, self.bot.loop)
        
        if not songs:
            return await interaction.followup.send("❌ No pude encontrar resultados para eso.")
        
        if len(songs) > 1:
            return await interaction.followup.send("❌ El comando `/playnow` no permite playlists.")
            
        song = songs[0]
        player.queue.insert(0, song)
        
        await interaction.followup.send(f"⚡ Reproduciendo de inmediato: **{song['title']}**")
        
        if player.voice_client and player.voice_client.is_playing():
            player.voice_client.stop() 
        elif not player.current_song:
            await player.play_next()

    # --- COMANDOS DE CONTROL DE COLA ---

    @app_commands.command(name="queue", description="Muestra las próximas 10 canciones en la cola.")
    async def queue(self, interaction: discord.Interaction):
        player = self.get_player(interaction)
        if not player.queue:
            return await interaction.response.send_message("ℹ️ La cola está vacía.")
            
        queue_slice = player.queue[:10]
        desc = ""
        for i, song in enumerate(queue_slice):
            desc += f"**{i+1}.** {song['title']} `[{song['duration_str']}]`\n"
            
        embed = discord.Embed(title=f"🎶 Cola actual ({len(player.queue)} canciones)", description=desc, color=discord.Color.blue())
        if len(player.queue) > 10:
            embed.set_footer(text=f"... y {len(player.queue) - 10} canciones más.")
            
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="skipto", description="Salta la cola directamente hasta el ID seleccionado.")
    async def skipto(self, interaction: discord.Interaction, id: int):
        player = self.get_player(interaction)
        if not player.queue:
            return await interaction.response.send_message("ℹ️ La cola está vacía.")
            
        index = id - 1
        if index < 0 or index >= len(player.queue):
            return await interaction.response.send_message("❌ ID inválido. Revisa la lista con `/queue`.")
            
        song_to_play = player.queue[index]
        player.queue = player.queue[index:]
        
        await interaction.response.send_message(f"⏭️ Saltando directamente a: **{song_to_play['title']}**")
        
        if player.voice_client and player.voice_client.is_playing():
            player.voice_client.stop()
        elif not player.current_song:
            await player.play_next()

    @app_commands.command(name="playnextqueue", description="Mueve una canción de la cola al primer lugar.")
    async def playnextqueue(self, interaction: discord.Interaction, id: int):
        player = self.get_player(interaction)
        if not player.queue:
            return await interaction.response.send_message("ℹ️ La cola está vacía.")
            
        index = id - 1
        if index < 0 or index >= len(player.queue):
            return await interaction.response.send_message("❌ ID inválido. Revisa la lista con `/queue`.")
            
        song = player.queue.pop(index)
        player.queue.insert(0, song)
        await interaction.response.send_message(f"⬆️ Movida al primer lugar: **{song['title']}**")

    @app_commands.command(name="remove", description="Elimina una canción específica de la cola mediante su ID.")
    async def remove(self, interaction: discord.Interaction, id: int):
        player = self.get_player(interaction)
        index = id - 1
        if index < 0 or index >= len(player.queue):
            return await interaction.response.send_message("❌ ID inválido. Revisa la lista con `/queue`.")
            
        song = player.queue.pop(index)
        await interaction.response.send_message(f"❌ Eliminada de la cola: **{song['title']}**")

    @app_commands.command(name="clear", description="Limpia todas las canciones de la cola de reproducción.")
    async def clear(self, interaction: discord.Interaction):
        player = self.get_player(interaction)
        player.queue.clear()
        await interaction.response.send_message("🧹 La cola ha sido limpiada.")

    # --- COMANDOS DE REPRODUCTOR ---

    @app_commands.command(name="pause", description="Pausa la canción actual.")
    async def pause(self, interaction: discord.Interaction):
        player = self.get_player(interaction)
        if player.voice_client and player.voice_client.is_paused():
            return await interaction.response.send_message("ℹ️ La música ya estaba pausada. Usa `/resume` para reanudar.")
            
        if player.voice_client and player.voice_client.is_playing():
            player.voice_client.pause()
            await interaction.response.send_message("⏸️ Música pausada. Usa `/resume` para reanudar.")
        else:
            await interaction.response.send_message("ℹ️ No hay nada reproduciéndose.", ephemeral=True)

    @app_commands.command(name="resume", description="Reanuda la canción actual.")
    async def resume(self, interaction: discord.Interaction):
        player = self.get_player(interaction)
        if player.voice_client and player.voice_client.is_playing():
            return await interaction.response.send_message("ℹ️ La música ya está sonando. Usa `/pause` para pausar.")
            
        if player.voice_client and player.voice_client.is_paused():
            player.voice_client.resume()
            await interaction.response.send_message("▶️ Música reanudada. Usa `/pause` para pausar.")
        else:
            await interaction.response.send_message("ℹ️ No hay música pausada.", ephemeral=True)

    @app_commands.command(name="stop", description="Detiene la música y limpia la cola completa.")
    async def stop(self, interaction: discord.Interaction):
        player = self.get_player(interaction)
        player.queue.clear()
        
        if player.voice_client and player.voice_client.is_connected():
            player.voice_client.stop()
            
        await interaction.response.send_message("⏹️ Música detenida y cola limpiada.")

    # --- COMANDO DESCONECTAR (SONIDO SALIDA) ---
    @app_commands.command(name="disconnect", description="Desconecta al bot del canal de voz.")
    async def disconnect(self, interaction: discord.Interaction):
        player = self.get_player(interaction)
        player.queue.clear()
        
        if player.voice_client and player.voice_client.is_connected():
            if player.voice_client.is_playing():
                player.voice_client.stop()
                
            await interaction.response.send_message("👋 Desconectando...")
            
            # --- LÓGICA DE SONIDO DE SALIDA ---
            leave_sound = 'sounds/leave.mp3'
            if os.path.exists(leave_sound):
                def after_playing(error):
                    # Desconectar una vez termine el sonido
                    fut = asyncio.run_coroutine_threadsafe(player.voice_client.disconnect(), self.bot.loop)
                    try: fut.result()
                    except: pass
                
                try:
                    player.voice_client.play(discord.FFmpegPCMAudio(leave_sound), after=after_playing)
                except:
                    await player.voice_client.disconnect()
            else:
                await player.voice_client.disconnect()
        else:
            await interaction.response.send_message("ℹ️ No estoy conectado a ningún canal de voz.", ephemeral=True)

    @app_commands.command(name="playnowqueue", description="Reproduce inmediatamente una canción de la cola por su ID.")
    async def playnowqueue(self, interaction: discord.Interaction, id: int):
        player = self.get_player(interaction)
        
        if not player.queue:
            return await interaction.response.send_message("ℹ️ La cola está vacía.", ephemeral=True)
            
        index = id - 1
        if index < 0 or index >= len(player.queue):
            return await interaction.response.send_message("❌ ID inválido. Revisa la lista con `/queue`.", ephemeral=True)
            
        # Extraemos la canción de su posición actual
        song = player.queue.pop(index)
        # La insertamos como la inminente (posición 0)
        player.queue.insert(0, song)
        
        await interaction.response.send_message(f"⚡ Reproduciendo de inmediato: **{song['title']}**")
        
        # Detenemos la actual para forzar el salto a la nueva canción
        if player.voice_client and player.voice_client.is_playing():
            player.voice_client.stop()
        elif not player.current_song:
            await player.play_next()

    @app_commands.command(name="nowplaying", description="Muestra la información de la canción que está sonando actualmente.")
    async def nowplaying(self, interaction: discord.Interaction):
        player = self.get_player(interaction)
        
        if not player.current_song:
            return await interaction.response.send_message("ℹ️ No hay nada reproduciéndose en este momento.", ephemeral=True)
            
        embed = discord.Embed(
            title="🎵 Reproduciendo ahora",
            description=f"**[{player.current_song['title']}]({player.current_song['url']})**",
            color=discord.Color.green()
        )
        if player.current_song['thumbnail']:
            # También puedes usar set_image() en lugar de set_thumbnail() si prefieres que la foto salga más grande
            embed.set_thumbnail(url=player.current_song['thumbnail'])
            
        embed.add_field(name="Duración", value=player.current_song['duration_str'], inline=True)
        embed.add_field(name="Pedido por", value=player.current_song['requester'], inline=True)
        
        songs_left = len(player.queue)
        footer_text = f"Siguientes en cola: {songs_left}" if songs_left > 0 else "Esta es la última canción de la cola."
        embed.set_footer(text=footer_text)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="shuffle", description="Aleatoriza las canciones actuales en la cola de reproducción.")
    async def shuffle(self, interaction: discord.Interaction):
        player = self.get_player(interaction)
        
        if not player.queue or len(player.queue) < 2:
            return await interaction.response.send_message("ℹ️ No hay suficientes canciones en la cola para mezclar.", ephemeral=True)
            
        # Mezclamos la lista in-place
        import random
        random.shuffle(player.queue)
        
        await interaction.response.send_message("🔀 La cola de reproducción ha sido mezclada aleatoriamente.")

    # --- COMANDO AYUDA ---
    @app_commands.command(name="help", description="Muestra la lista de todos los comandos disponibles.")
    async def help_cmd(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎵 Panel de Ayuda - Bot de Música",
            description="Aquí tienes la lista de comandos disponibles y su función:",
            color=discord.Color.blurple()
        )
        
        commands_info = {
            "/play [query]": "Añade una canción o playlist al final de la cola.",
            "/playnext [query]": "Añade una canción como la siguiente en sonar.",
            "/playnow [query]": "Reproduce una canción inmediatamente, saltando la actual.",
            "/queue": "Muestra las próximas 10 canciones en la cola.",
            "/shuffle": "Mezcla de forma aleatoria todas las canciones pendientes en la cola.",
            "/nowplaying": "Muestra la canción que está sonando en este momento.",
            "/skipto [id]": "Salta la cola directamente hasta el número indicado.",
            "/playnextqueue [id]": "Mueve una canción que ya está en la cola al primer lugar.",
            "/playnowqueue [id]": "Reproduce inmediatamente esa canción de la cola, omitiendo la actual.",
            "/remove [id]": "Elimina una canción específica de la cola.",
            "/pause": "Pausa la reproducción actual.",
            "/resume": "Reanuda la canción pausada.",
            "/stop": "Detiene la música y limpia por completo la cola.",
            "/clear": "Elimina todas las canciones de la cola (sin detener la actual).",
            "/disconnect": "Desconecta al bot del canal de voz.",
            "/help": "Muestra este panel de ayuda."
        }
        
        for cmd, desc in commands_info.items():
            embed.add_field(name=f"`{cmd}`", value=desc, inline=False)
            
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Music(bot))