import discord
from discord.ext import commands
from discord import app_commands

class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Sobrescribimos el manejador de errores global del árbol de comandos
        self.bot.tree.on_error = self.on_app_command_error

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        # Manejo de errores comunes en Slash Commands
        if isinstance(error, app_commands.CommandOnCooldown):
            msg = f"⏳ Comando en enfriamiento. Intenta de nuevo en {error.retry_after:.2f}s."
        elif isinstance(error, app_commands.MissingPermissions):
            msg = "❌ No tienes los permisos necesarios para usar este comando."
        else:
            msg = f"❌ Ocurrió un error inesperado al ejecutar el comando."
            print(f"[Error en Slash Command] {interaction.command.name if interaction.command else 'Desconocido'}: {error}")

        # Comprobar si ya habíamos respondido o deferido la interacción
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Events(bot))