import os
import socket
import re
from dataclasses import dataclass, field
from threading import Thread

import discord
import mcstatus
import pystray
import yaml
from discord.ext import tasks
from mcipc.query import Client
from PIL import Image
from pystray import Menu, MenuItem
from yaml import Loader


class MineClient(discord.Client):
    def __init__(self, *, loop=None, **options):
        super().__init__(**options)
        self.old = []
        self.servers = []
        print("Initializing")

    async def on_ready(self):
        print(f"{self.user} has connected")
        try:
            with open("servers.yml", "r") as file:
                self.servers = yaml.load(file, Loader)
                print("Saved servers loaded:")
                for server in self.servers:
                    print(f"\t{server.name}")
        except FileNotFoundError:
            pass
        self.server_status.start()

    async def on_message(self, message: discord.Message):
        if message.author == self.user:
            return
        content = message.content.lower()
        channel = message.channel
        ip, port, etc = extract_ip(content)
        if content.startswith("!kill"):
            if message.author.id == 97117492178067456:
                await channel.send("kill")
                os._exit(1)
            else:
                await channel.send("You are not authorized to use this command")
        if content.startswith("!start"):
            if ip and port:
                await self.add_server(channel, ip, port, etc)
            else:
                await channel.send("Usage: !Start <ip_address>[:port] [Server Name]")
        if content.startswith("!stop"):
            if ip and port:
                await self.remove_server(channel, ip, port)
            else:
                await channel.send("Usage: !Stop <ip_address>[:port]")
        if content.startswith("!query"):
            if ip and port:
                await self.query(ip, port, channel)
            else:
                await channel.send("Usage: !Query <ip_address>[:port]")
        if content.startswith("!list"):
            await self.list_servers(channel)
        if content in ["!help", "!h"]:
            await message.channel.send(
                "!Start <ip_address>[:port] [Server Name] - Start monitoring <ip_address>, [Server Name] is optional\n"
                "!Query <ip_address>[:port] - List Current Players\n"
                "!Stop  <ip_address>[:port] - Stop monitoring <ip_address>\n"
                "!List - List all servers being monitored in this channel\n"
                "!Help - Print this Message"
            )

    async def query(self, ip, port, channel):
        try:
            with Client(ip, port, timeout=3) as client:
                pls = client.stats(full=True).players
                reply = (
                    f'Current Players Online: **{", ".join(pls) if pls else "None"}**'
                )
        except ConnectionRefusedError:
            try:
                status = mcstatus.JavaServer.lookup(f"{ip}:{port}").status()
                reply = (
                    f"Current Players Online: "
                    f'**{", ".join(status.players.names) if status.players.sample else "None"}**'
                )
            except ConnectionRefusedError:
                reply = "Connection Refused"
        except socket.timeout as timeout:
            reply = f"{timeout}\nMake sure query is enabled in server properties"
        except socket.error as e:
            reply = f"{e}"
        embed = discord.Embed(type="rich", description=reply)
        await channel.send(embed=embed)

    async def add_server(self, channel, server_ip, port, name):
        print(f"Adding {server_ip}:{port} {name}")
        try:
            server = MCServer(channel.id, server_ip, port)
            with Client(server_ip, port, timeout=3) as client:
                stats = client.stats(full=True)
                print(name)
                if name:
                    server.name = name
                elif stats.host_name != "A Minecraft Server":
                    server.name = stats.host_name
                else:
                    server.name = f"{server_ip}:{port}"
                reply = f"Now monitoring {server.name}"
            self.servers += [server]
            with open("servers.yml", "w") as file:
                yaml.dump(self.servers, file)
        except ConnectionRefusedError:
            try:
                server = MCServer(channel.id, server_ip, port)
                status = mcstatus.JavaServer.lookup(f"{server_ip}:{port}").status()
                server.type = "mcstatus"
                if name:
                    server.name = name
                elif status.description != "A Minecraft Server":
                    server.name = status.description
                else:
                    server.name = f"{server_ip}:{port}"
                reply = f"Now monitoring {server.name}"
                reply += "\nNote: Using mcstatus, player list may be inaccurate for large servers"
                reply += "\nTurn on query in server.properties for better results"
                self.servers += [server]
                with open("servers.yml", "w") as file:
                    yaml.dump(self.servers, file)
            except ConnectionRefusedError:
                reply = "Connection Refused"
        except socket.error as e:
            reply = f"{e}"
        embed = discord.Embed(type="rich", description=reply)
        await channel.send(embed=embed)

    async def remove_server(self, channel, server_ip, port):
        found = False
        for server in self.servers.copy():
            if (
                server.ip == server_ip
                and port == server.port
                and server.channel_id == channel.id
            ):
                found = True
                self.servers.remove(server)
                message = f"No longer monitoring {server.name}"
                embed = discord.Embed(type="rich", description=message)
                await channel.send(embed=embed)
        with open("servers.yml", "w") as file:
            yaml.dump(self.servers, file)
        if not found:
            await channel.send(
                f"Unable to find server with ip {server_ip}:{port}\n"
                f"Note: monitoring can only be stopped in the same channel it was started"
            )

    async def list_servers(self, channel):
        reply = "Currently Monitoring:\n"
        for server in self.servers:
            if server.channel_id == channel.id:
                if server.name == f"{server.ip}:{server.port}":
                    reply += f"\t{server.name}\n"
                else:
                    reply += f"\t{server.name} ({server.ip}:{server.port})\n"
        if reply == "Currently Monitoring:\n":
            reply = "Not currently monitoring any servers\n"
            reply += "Use !Start <ip_address>[:port] to start monitoring a server\n"
            reply += "Use !Help for more info"
        embed = discord.Embed(type="rich", description=reply)
        await channel.send(embed=embed)

    @tasks.loop(seconds=60)
    async def server_status(self):
        for server in self.servers:
            reply = ""
            try:
                if server.type == "query":
                    with Client(server.ip, server.port, timeout=3) as client:
                        server.timeout = 3600
                        pls = set(client.stats(full=True).players)
                        if pls != server.old:
                            message = ""
                            for player in pls ^ server.old:
                                message += (
                                    f"**{player}** has "
                                    f"{'Joined' if player in pls else 'Left'} "
                                    f"{server.name}\n"
                                )
                            message += f'Current Players Online: **{", ".join(pls) if pls else "None"}**'
                            embed = discord.Embed(type="rich", description=message)
                            channel = await self.fetch_channel(server.channel_id)
                            await channel.send(embed=embed)
                        server.old = set(pls)
                elif server.type == "mcstatus":
                    status = mcstatus.JavaServer.lookup(
                        f"{server.ip}:{server.port}"
                    ).status()
                    server.timeout = 3600
                    if status.players.sample:
                        pls = set(p.name for p in status.players.sample)
                    else:
                        pls = set()
                    if pls != server.old:
                        message = ""
                        for player in pls ^ server.old:
                            message += (
                                f"**{player}** has "
                                f"{'Joined' if player in pls else 'Left'} "
                                f"{server.name}\n"
                            )
                        message += f'Current Players Online: **{", ".join(pls) if pls else "None"}**'
                        embed = discord.Embed(type="rich", description=message)
                        channel = await self.fetch_channel(server.channel_id)
                        await channel.send(embed=embed)
                    server.old = set(pls)
            except ConnectionRefusedError:
                if server.timeout <= 0:
                    reply = (
                        "Unable to reach server for more than 1 hour"
                        f"\nmonitoring stopped for {server.name}"
                    )
                    self.servers.remove(server)
                    embed = discord.Embed(type="rich", description=reply)
                    channel = await self.fetch_channel(server.channel_id)
                    await channel.send(embed=embed)
                else:
                    server.timeout -= 60


def extract_ip(ip_string):
    # ip_string format: command ip_address[:port] [optional info]
    # returns ip_address, port, optional info
    match = re.match(r"(\S+)\s+([\w.]+)(?::(\S+))?(?:\s+(.*))?", ip_string)
    if match:
        ip = match.group(2)
        port = match.group(3) if match.group(3) else 25565
        info = match.group(4)
        return ip, int(port), info
    else:
        return None, None, None


@dataclass
class MCServer:
    channel_id: int
    ip: str
    port: int = 25565
    name: str = ""
    old: set[str] = field(repr=False, hash=False, default_factory=set)
    timeout: int = field(repr=False, hash=False, default=3600)
    type: str = "query"


def systray():
    image = Image.open("./icon.png")
    image = image.resize((64, 64))
    menu = Menu(MenuItem("Quit", lambda: os._exit(0)))
    icon = pystray.Icon("Discord Bot", image, "AAA", menu)
    icon.run()


if __name__ == "__main__":
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        print("TOKEN not set")
        exit()
    discordClient = MineClient(intents=discord.Intents.all())
    iconThread = Thread(target=systray)
    iconThread.start()
    discordClient.run(TOKEN)
