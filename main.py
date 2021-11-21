import asyncio
import os
import socket

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
        self.servers = []

    async def on_ready(self):
        print(f'{self.user} has connected')
        self.server_status.start()

    async def on_message(self, message: discord.Message):
        if message.author == self.user:
            return
        content = message.content.lower()
        channel = message.channel
        ip, port = extract_ip(content)
        if content.startswith('!start'):
            if ip and port:
                await self.add_server(channel, ip, port)
            else:
                await channel.send("Usage: !Start <ip_address>[:port]")
        if content.startswith('!stop'):
            if ip and port:
                await self.remove_server(channel, ip, port)
            else:
                await channel.send("Usage: !Start <ip_address>[:port]")
        if content.startswith('!query'):
            if ip and port:
                sent = False
                print(ip, port)
                try:
                    with Client(ip, port, timeout=3) as client:
                        pls = client.stats(full=True).players
                        reply = f'Current Players Online: **{", ".join(pls) if pls else "None"}**'
                except ConnectionRefusedError:
                    reply = "Connection Refused"
                except socket.timeout as timeout:
                    reply = f"{timeout}\nMake sure query is enabled in server properties"
                except socket.error as e:
                    reply = f"{e}"
                embed = discord.Embed(type='rich', description=reply)
                await channel.send(embed=embed)
            else:
                await channel.send("Usage: !Query <ip_address>[:port]")

        if content in ['!help', '!h']:
            await message.channel.send(
                "!Start <ip_address>[:port] - Start monitoring <ip_address>\n"
                "!Query <ip_address>[:port] - List Current Players\n"
                "!Stop  <ip_address>[:port] - Stop monitoring <ip_address>\n"
                "!Help - Print this Message"
            )

    async def add_server(self, channel, server_ip, port):
        try:
            with Client(server_ip, port, timeout=3) as client:
                reply = f"Now monitoring {server_ip}:{port}"
            self.servers += [MCServer(channel, server_ip, port)]
        except ConnectionRefusedError:
            reply = "Connection Refused"
        except socket.timeout as timeout:
            reply = f"{timeout}\nMake sure query is enabled in server properties"
        except socket.error as e:
            reply = f"{e}"
        embed = discord.Embed(type='rich', description=reply)
        await channel.send(embed=embed)

    async def remove_server(self, channel, server_ip, port):
        found = False
        for server in self.servers.copy():
            if server.ip == server_ip and port == server.port and server.channel.id == channel.id:
                found = True
                self.servers.remove(server)
                message = f"No longer monitoring {server_ip}:{port}"
                embed = discord.Embed(type='rich', description=message)
                await channel.send(embed=embed)
        if not found:
            await channel.send(
                f"Unable to find server with ip {server_ip}:{port}\n"
                f"Note: monitoring can only be stopped in the same channel it was started"
            )

    @tasks.loop(seconds=5.0)
    async def server_status(self):
        for server in self.servers:
            reply = ""
            try:
                with Client(server.ip, server.port, timeout=3) as client:
                    server.timeout = 3600
                    pls = client.stats(full=True).players
                    if pls != server.old:
                        message = ""
                        for player in (set(pls) ^ set(server.old)):
                            message += f"**{player}** has " \
                                       f"{'Joined' if player in pls else 'Left'} " \
                                       f"{server.ip}\n"
                        message += f'Current Players Online: **{", ".join(pls) if pls else "None"}**'
                        embed = discord.Embed(type='rich', description=message)
                        await server.channel.send(embed=embed)
                    server.old = pls
            except ConnectionRefusedError:
                if server.timeout <= 0:
                    reply = "Unable to reach server for more than 1 hour" \
                            f"\nmonitoring stopped for {server.ip}:{server.port}"
                    self.servers.remove(server)
                    embed = discord.Embed(type='rich', description=reply)
                    await server.channel.send(embed=embed)
                else:
                    server.timeout -= 5


def extract_ip(ip_string):
    if len(ip_string.split()) > 1:
        _, ip = ip_string.split()
        port = 25565
        if ":" in ip:
            ip, port = ip.split(":")
        return ip, port
    return None, None


@dataclass
class MCServer:
    channel: discord.TextChannel
    ip: str
    port: int = 25565
    old: list[str] = field(default_factory=list)
    timeout: int = 3600


TOKEN = os.getenv('BOT_TOKEN')
discordClient = MineClient()
discordClient.run(TOKEN)
