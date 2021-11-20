import asyncio
import os
import discord
from discord import Color
from discord.ext import tasks

from mcipc.query import Client
from mcipc.rcon.je import Client as rClient


class MineClient(discord.Client):
    def __init__(self, *, loop=None, **options):
        super().__init__()
        self.old = []
        self.guild_servers = {}

    async def on_ready(self):
        print(f'{self.user} has connected')
        self.server_status.start()

    async def on_message(self, message: discord.Message):
        if message.author == self.user:
            return
        if message.content.startswith('!Start'):
            channel = message.channel
            guild_id = message.guild.id
            if len(message.content.split("!Start ")) > 1:
                await message.channel.send('Starting')
                _, ip = message.content.split("!Start ")
                port = 25565
                if ":" in ip:
                    ip, port = ip.split(":")
                await self.add_server(guild_id, channel, ip, port)
            else:
                await channel.send("Usage: !Start <ip_address>[:port]")
        if message.content.startswith('!Stop'):
            del self.guild_servers[message.guild.id]
        if message.content == '!Query':
            curr_channel = message.channel
            channel, ip, port = self.guild_servers[message.guild.id]
            with Client(ip, port) as client:
                pls = client.stats(full=True).players
                message = f'Current Players Online: **{", ".join(pls) if pls else "None"}**'
                embed = discord.Embed(type='rich', description=message)
                await curr_channel.send(embed=embed)

    async def add_server(self, guild_id, channel, server_ip, port):
        if guild_id not in self.guild_servers:
            self.guild_servers[guild_id] = (channel, server_ip, port)
            message = f"Now listening to {server_ip}:{port}"
        else:
            message = f"Currently only one MC server per Discord server is allowed\n" \
                      f"Current server: {self.guild_servers[guild_id][1]}\n" \
                      f"Send \"!Stop\" to switch servers"
        await channel.send(message)

    @tasks.loop(seconds=5.0)
    async def server_status(self):
        for g_id, (channel, ip, port) in self.guild_servers.items():
            with Client(ip, port) as client:
                pls = client.stats(full=True).players
                if pls != self.old:
                    message = ""
                    for player in (set(pls) ^ set(self.old)):
                        message += f"**{player}** has " \
                                   f"{'Joined' if player in pls else 'Left'} " \
                                   f"the server\n"
                    message += f'Current Players Online: **{", ".join(pls) if pls else "None"}**'
                    embed = discord.Embed(type='rich', description=message)
                    await channel.send(embed=embed)
                self.old = pls


TOKEN = os.getenv('BOT_TOKEN')
discordClient = MineClient()
discordClient.run(TOKEN)
