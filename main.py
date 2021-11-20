import asyncio
import os
import discord
from discord import Color
from discord.ext import tasks

from mcipc.query import Client
from mcipc.rcon.je import Client as rClient

TOKEN = os.getenv('BOT_TOKEN')
SERVER_IP = os.getenv('SERVER_IP')
if TOKEN is None or SERVER_IP is None:
    print("ARG", TOKEN, SERVER_IP)
    exit(0)


class MineClient(discord.Client):
    def __init__(self, *, loop=None, **options):
        super().__init__()
        self.main_ch = None
        self.old = []

    async def on_ready(self):
        print(f'{self.user} has connected')

    async def on_message(self, message: discord.Message):
        if message.author == self.user:
            return
        if message.content == '!Start':
            await message.channel.send('Starting')
            self.main_ch = message.channel
            self.server_status.start()
        if message.content == '!Query':
            self.main_ch = message.channel
            with Client(SERVER_IP, 25565) as client:
                pls = client.stats(full=True).players
                message = f'Current Players Online: **{", ".join(pls) if pls else "None"}**'
                embed = discord.Embed(type='rich', description=message)
                await self.main_ch.send(embed=embed)

    @tasks.loop(seconds=5.0)
    async def server_status(self):
        with Client(SERVER_IP, 25565) as client:
            pls = client.stats(full=True).players
            if pls != self.old:
                message = f'**{", ".join(set(pls) ^ (set(self.old)))}** ' \
                      f'Has {"Joined" if pls else "Left"} The Server\n' \
                      f'Current Players Online: **{", ".join(pls) if pls else "None"}**'
                embed = discord.Embed(type='rich', description=message)
                await self.main_ch.send(embed=embed)
            self.old = pls


discordClient = MineClient()
discordClient.run(TOKEN)
