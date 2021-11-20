import asyncio
import os
import discord

from dataclasses import dataclass, field

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
            if message.guild.id in self.guild_servers:
                server = self.guild_servers[message.guild.id]
                with Client(server.ip, server.port) as client:
                    pls = client.stats(full=True).players
                    reply = f'Current Players Online: **{", ".join(pls) if pls else "None"}**'
                    embed = discord.Embed(type='rich', description=reply)
                    await curr_channel.send(embed=embed)
            else:
                await curr_channel.send(
                    "Not listening to any servers\n"
                    "Use: !Start <ip_address>[:port]"
                )
        if message.content == '!Help':
            await message.channel.send(
                "!Start <ip_address>[:port] - Start listening to <ip_address>\n"
                "!Query - List Current Players, requires Start first\n"
                "!Stop - Stop listening\n"
                "!Help - Print this Message"
            )

    async def add_server(self, guild_id, channel, server_ip, port):
        if guild_id not in self.guild_servers:
            self.guild_servers[guild_id] = MCServer(channel, server_ip, port)
            message = f"Now listening to {server_ip}:{port}"
        else:
            message = f"Currently only one MC server per Discord server implemented\n" \
                      f"Current server: {self.guild_servers[guild_id].ip}\n" \
                      f"Send \"!Stop\" to stop listening to this server"
        embed = discord.Embed(type='rich', description=message)
        await channel.send(embed=embed)

    @tasks.loop(seconds=5.0)
    async def server_status(self):
        for g_id, server in self.guild_servers.items():
            with Client(server.ip, server.port) as client:
                pls = client.stats(full=True).players
                if pls != server.old:
                    message = ""
                    for player in (set(pls) ^ set(server.old)):
                        message += f"**{player}** has " \
                                   f"{'Joined' if player in pls else 'Left'} " \
                                   f"the server\n"
                    message += f'Current Players Online: **{", ".join(pls) if pls else "None"}**'
                    embed = discord.Embed(type='rich', description=message)
                    await server.channel.send(embed=embed)
                server.old = pls


@dataclass
class MCServer:
    channel: discord.TextChannel
    ip: str
    port: int = 25565
    old: list[str] = field(default_factory=list)


TOKEN = os.getenv('BOT_TOKEN')
discordClient = MineClient()
discordClient.run(TOKEN)
