import base64
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from io import BytesIO
from threading import Thread

import discord
import mcstatus
import yaml
from discord.ext import tasks
from PIL import Image
from pystray import Icon, Menu, MenuItem
from yaml import Loader


class MineClient(discord.Client):

    def __init__(self, *, loop=None, **options):
        super().__init__(**options)
        self.old = []
        self.servers = []
        log_file = "discord.log"
        if os.path.exists(log_file):
            os.remove(log_file)
        logging.basicConfig(
            level=logging.INFO,
            format="[%(asctime)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
        )
        logging.info("Initializing")

    async def on_ready(self):
        logging.info(f"{self.user} has connected")
        try:
            with open("servers.yml", "r") as file:
                self.servers = yaml.load(file, Loader)
                logging.info(f"Loaded {len(self.servers)} servers")
                for server in self.servers:
                    if server.last_checked < datetime.now() - timedelta(days=1):
                        server.old = set()
                        status = self.lookup(server.address)
                        if not isinstance(status, str):
                            server.name = self.get_server_name(status, server.address)
                            server.last_checked = datetime.now()
                logging.info(
                    "Servers loaded: " + ", ".join([s.name for s in self.servers])
                )
        except FileNotFoundError:
            pass
        self.server_status.start()

    async def on_message(self, message: discord.Message):
        if message.author == self.user:
            return
        content = message.content.lower()
        channel = message.channel
        if not content.startswith("!") or len(content.split()) < 2:
            return

        _, address, *etc = content.split()
        etc = " ".join(etc)

        if content.startswith("!start"):
            if address:
                await self.add_server(channel, address, etc)
            else:
                await channel.send("Usage: !Start <ip_address> [Server Name]")
        elif content.startswith("!stop"):
            if address:
                await self.remove_server(channel, address)
            else:
                await channel.send("Usage: !Stop <ip_address>")
        elif content.startswith("!query"):
            if address:
                await self.query(address, channel)
            else:
                await channel.send("Usage: !Query <ip_address>")
        elif content in ["!list", "!l"]:
            await self.list_servers(channel)
        elif content in ["!help", "!h"]:
            await channel.send(embed=self.help_embed())

    def help_embed(self):
        embed = discord.Embed(type="rich", title="Help")
        embed.add_field(
            name="Query",
            value="!Query <ip_address> - List Current Players",
            inline=False,
        )
        embed.add_field(
            name="Start",
            value="!Start <ip_address> [Server Name] - Start monitoring <ip_address>\nServer Name is optional",
            inline=False,
        )
        embed.add_field(
            name="Stop",
            value="!Stop  <ip_address> - Stop monitoring <ip_address>",
            inline=False,
        )
        embed.add_field(
            name="List",
            value="!List - List all servers being monitored in this channel",
            inline=False,
        )
        embed.add_field(name="Help", value="!Help - Print this Message")
        return embed

    def lookup(self, address) -> mcstatus.status_response.JavaServerStatus:
        try:
            return mcstatus.JavaServer.lookup(address).status()
        except (ConnectionRefusedError, TimeoutError, IOError) as e:
            logging.warning(f"Error getting status for {address}: {e}")
            return f"Unable to reach server at {address}: {e}"
        except Exception as e:
            logging.error(f"Error looking up {address}: {e}", exc_info=True)
            return f"Error looking up {address}: {e}"

    def get_server_name(self, status, address):
        if status.motd.to_plain() != "A Minecraft Server":
            return status.motd.to_plain()
        else:
            return address

    def get_players(self, status):
        if status.players.sample:
            return set(p.name for p in status.players.sample)
        else:
            return set()

    def get_server_icon(self, status):
        if status.icon:
            icon = BytesIO(base64.b64decode(status.icon.split(",")[-1]))
            return discord.File(icon, filename="icon.png")
        else:
            icon = Image.open("icon.png")
            buffer = BytesIO()
            icon.save(buffer, format="PNG")
            buffer.seek(0)
            return discord.File(buffer, filename="icon.png")

    def current_players(self, players):
        return (
            f"Current Players Online: **{', '.join(players) if players else 'None'}**"
        )

    def check_players(self, players, old, name):
        message = ""
        for player in players ^ old:
            message += (
                f"**{player}** has "
                f"{'joined' if player in players else 'left'} {name}\n"
            )
        return message

    def players_message(self, players, old, name):
        if old is None:
            return self.current_players(players)
        else:
            return self.check_players(players, old, name) + self.current_players(
                players
            )

    def make_embed(self, name, message, icon=None):
        embed = discord.Embed(type="rich", title=name, description=message)
        if icon:
            embed.set_thumbnail(url="attachment://icon.png")
        return embed

    async def send_players_embed(self, status, channel, address, old=None):
        players = self.get_players(status)
        name = self.get_server_name(status, address)
        message = self.players_message(players, old, name)
        icon = self.get_server_icon(status)
        embed = self.make_embed(name, message, icon)
        await channel.send(embed=embed, file=icon)

    async def query(self, ip, channel):
        status = self.lookup(ip)
        if isinstance(status, str):
            embed = discord.Embed(type="rich", title="Error", description=status)
            await channel.send(embed=embed)
            return
        await self.send_players_embed(status, channel, ip)

    async def add_server(self, channel, server_ip, name):
        server = MCServer(channel.id, server_ip)
        status = self.lookup(server_ip)
        if isinstance(status, str):
            embed = self.make_embed("Error", status)
            await channel.send(embed=embed)
            return
        server.name = name if name else self.et_server_name(status, server_ip)

        self.servers += [server]
        with open("servers.yml", "w") as file:
            yaml.dump(self.servers, file)

        message = f"Now monitoring {server.name}"
        icon = self.get_server_icon(status)
        embed = self.make_embed(server.name, message, icon)
        await channel.send(embed=embed, file=icon)

    async def remove_server(self, channel, address):
        found = False
        for server in self.servers.copy():
            if server.address == address and server.channel_id == channel.id:
                found = True
                self.servers.remove(server)
                message = f"No longer monitoring {server.name}"
                embed = discord.Embed(
                    type="rich", title=server.name, description=message
                )
                await channel.send(embed=embed)
        with open("servers.yml", "w") as file:
            yaml.dump(self.servers, file)
        if not found:
            await channel.send(
                f"Unable to find server at {address}\n"
                "Try using !List to see all servers being monitored in this channel\n"
            )

    async def list_servers(self, channel):
        reply = "Currently Monitoring:\n"
        for server in self.servers:
            if server.channel_id == channel.id:
                if server.name == f"{server.address}":
                    reply += f"\t{server.name}\n"
                else:
                    reply += f"\t{server.name} ({server.address})\n"
        if reply == "Currently Monitoring:\n":
            reply = "Not currently monitoring any servers\n"
            reply += "Use !Start <ip_address> to start monitoring a server\n"
            reply += "Use !Help for more info"
        embed = discord.Embed(type="rich", description=reply)
        await channel.send(embed=embed)

    @tasks.loop(seconds=60)
    async def server_status(self):
        to_remove = []
        for server in self.servers:
            channel = await self.fetch_channel(server.channel_id)
            status = self.lookup(server.address)
            if isinstance(status, str):
                if server.last_checked < datetime.now() - timedelta(hours=1):
                    reply = (
                        f"Unable to reach server for more than 1 hour\n"
                        f"monitoring stopped for {server.name}"
                    )
                    to_remove += [server]
                    embed = self.make_embed("Connection Refused", reply)
                    await channel.send(embed=embed)
                continue
            players = self.get_players(status)
            if players == server.old:
                continue
            await self.send_players_embed(status, channel, server.address, server.old)
            server.old = set(players)
            server.last_checked = datetime.now()
        for server in to_remove:
            self.servers.remove(server)
        with open("servers.yml", "w") as file:
            yaml.dump(self.servers, file)


@dataclass
class MCServer:
    channel_id: int
    address: str
    name: str = ""
    old: set[str] = field(repr=False, hash=False, default_factory=set)
    last_checked: datetime = field(repr=False, hash=False, default_factory=datetime.now)


def systray():
    image = Image.open("./icon.png")
    image = image.resize((64, 64))
    menu = Menu(MenuItem("Quit", lambda: os._exit(0)))
    icon = Icon(name="Discord Bot", icon=image, menu=menu)
    icon.run()


if __name__ == "__main__":
    TOKEN = os.getenv("TOKEN")
    if not TOKEN:
        logging.error("No token found")
        exit()
    discordClient = MineClient(intents=discord.Intents.all())
    iconThread = Thread(target=systray)
    iconThread.start()
    discordClient.run(TOKEN)
