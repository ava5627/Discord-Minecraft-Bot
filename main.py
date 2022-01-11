import asyncio
import os
import socket
from dataclasses import dataclass, field

import discord
import yaml
from yaml import Loader
from discord.ext import tasks
from mcipc.query import Client


class MineClient(discord.Client):
    def __init__(self, *, loop=None, **options):
        super().__init__()
        self.old = []
        self.servers = []

    async def on_ready(self):
        print(f'{self.user} has connected')
        try:
            with open("servers.yml", 'r') as file:
                self.servers = yaml.load(file, Loader)
        except FileNotFoundError:
            pass
        print('here')
        self.server_status.start()

    async def on_message(self, message: discord.Message):
        if message.author == self.user:
            return
        content = message.content.lower()
        channel = message.channel
        ip, port = extract_ip(content)
        if content.startswith('!kill'):
            exit(1)
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
            server = MCServer(channel.id, server_ip, port)
            with Client(server_ip, port, timeout=3) as client:
                stats = client.stats(full=True)
                if stats.host_name != "A Minecraft Server":
                    server.name = stats.host_name
                else:
                    server.name = f'{server_ip}:{port}'
                reply = f"Now monitoring {server.name}"
            self.servers += [server]
            with open("servers.yml", 'w') as file:
                yaml.dump(self.servers, file)
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
            if server.ip == server_ip and port == server.port and server.channel_id == channel.id:
                found = True
                self.servers.remove(server)
                message = f"No longer monitoring {server.name}"
                embed = discord.Embed(type='rich', description=message)
                await channel.send(embed=embed)
        with open("servers.yml", 'w') as file:
            yaml.dump(self.servers, file)
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
                    pls = set(client.stats(full=True).players)
                    if pls != server.old:
                        message = ""
                        for player in (pls ^ server.old):
                            message += f"**{player}** has " \
                                       f"{'Joined' if player in pls else 'Left'} " \
                                       f"{server.name}\n"
                        message += f'Current Players Online: **{", ".join(pls) if pls else "None"}**'
                        embed = discord.Embed(type='rich', description=message)
                        channel = await self.fetch_channel(server.channel_id)
                        await channel.send(embed=embed)
                    server.old = set(pls)
            except ConnectionRefusedError:
                if server.timeout <= 0:
                    reply = "Unable to reach server for more than 1 hour" \
                            f"\nmonitoring stopped for {server.name}"
                    self.servers.remove(server)
                    embed = discord.Embed(type='rich', description=reply)
                    channel = await self.fetch_channel(server.channel_id)
                    await channel.send(embed=embed)
                else:
                    server.timeout -= 5


def extract_ip(ip_string):
    if len(ip_string.split()) > 1:
        _, ip = ip_string.split()
        port = 25565
        if ":" in ip:
            ip, port = ip.split(":")
        return ip, int(port)
    return None, None


@dataclass
class MCServer:
    channel_id: int
    ip: str
    port: int = 25565
    name: str = ""
    old: set[str] = field(repr=False, hash=False, default_factory=set)
    timeout: int = field(repr=False, hash=False, default=3600)


if __name__ == '__main__':
    TOKEN = os.getenv('BOT_TOKEN')
    discordClient = MineClient()
    discordClient.run(TOKEN)
