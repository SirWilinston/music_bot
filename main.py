import discord
from discord.ext import commands
from config import DISCORD_TOKEN

class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='-', intents=intents)

    async def setup_hook(self):
        # Carga el cog de música
        await self.load_extension('cogs.music')
        # Sincroniza los comandos de barra con Discord
        await self.tree.sync()
        print("Comandos Slash sincronizados correctamente.")

    async def on_ready(self):
        print(f'Bot conectado como {self.user.name}')
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="/play"))

if __name__ == "__main__":
    bot = MusicBot()
    bot.run(DISCORD_TOKEN)