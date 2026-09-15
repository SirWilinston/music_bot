import os
import sys
import subprocess
import asyncio
import aiohttp
from discord.ext import commands, tasks
from config import LIBS_TO_UPDATE, UPTIME_KUMA_URL

class Tasks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_check_task.start()
        self.uptime_heartbeat.start()

    def cog_unload(self):
        self.update_check_task.cancel()
        self.uptime_heartbeat.cancel()

    @tasks.loop(hours=1)
    async def update_check_task(self):
        print("[Auto-Update] Ejecutando revisión de actualizaciones...")
        
        # Comprobar si el bot está activo en algún canal de voz
        is_active = any(guild.voice_client and guild.voice_client.is_connected() for guild in self.bot.guilds)
        
        if is_active:
            print("[Auto-Update] El bot está activo reproduciendo música. Omitiendo revisión para no interrumpir.")
            return

        print("[Auto-Update] El bot está inactivo. Buscando actualizaciones de paquetes...")
        try:
            # sys.executable es la ruta al python actual (incluyendo el venv si está activado)
            cmd = [sys.executable, '-m', 'pip', 'list', '--outdated']
            process = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, check=True)
            
            needs_update = any(lib in process.stdout for lib in LIBS_TO_UPDATE)

            if not needs_update:
                print("[Auto-Update] Todas las bibliotecas monitoreadas están al día.")
                return

            print("[Auto-Update] Instalando actualizaciones...")
            install_cmd = [sys.executable, '-m', 'pip', 'install', '--upgrade'] + LIBS_TO_UPDATE
            await asyncio.to_thread(subprocess.run, install_cmd, capture_output=True, text=True, check=True)
            
            print("[Auto-Update] Actualizaciones instaladas. Reiniciando el bot...")
            await self.bot.close()
            os._exit(0)
            
        except subprocess.CalledProcessError as e:
            print(f"[Auto-Update] Fallo al revisar/instalar actualizaciones. Error: {e.stderr}")
        except Exception as e:
            print(f"[Auto-Update] Ocurrió un error inesperado: {e}")

    @update_check_task.before_loop
    async def before_update_check(self):
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=20)
    async def uptime_heartbeat(self):
        if not UPTIME_KUMA_URL:
            return
            
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(UPTIME_KUMA_URL) as response:
                    if response.status == 200:
                        pass # Ping exitoso silencioso
        except Exception as e:
            print(f"[Monitor] Fallo al avisar a Uptime Kuma: {e}")

    @uptime_heartbeat.before_loop
    async def before_heartbeat(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Tasks(bot))