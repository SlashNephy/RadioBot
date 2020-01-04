from __future__ import annotations

import asyncio
import re
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from subprocess import PIPE, Popen
from threading import Thread
from typing import Optional

import aiohttp
from discord import (Embed, FFmpegPCMAudio, PCMVolumeTransformer, Streaming,
                     TextChannel, VoiceChannel, VoiceClient)
from discord.ext import commands

from bot.app import App


class AgqrPlayer(commands.Cog):
    voice: VoiceClient
    voice_channel: VoiceChannel
    text_channel: Optional[TextChannel]

    @commands.Cog.listener()
    async def on_ready(self):
        App.logger.debug("Agqr module loaded.")

        if App.config.text_channel_id:
            self.text_channel = App.client.get_channel(App.config.text_channel_id)
        self.voice_channel = App.client.get_channel(App.config.voice_channel_id)

        member = self.voice_channel.guild.get_member(App.client.user.id)
        if member.nick != "超A&G+":
            await member.edit(nick="超A&G+")
            with open("resources/agqr.png", "rb") as f:
                await App.client.user.edit(avatar=f.read())

        # バグ対応のため, 一度接続して切断する
        await (await self.voice_channel.connect()).disconnect()
        self.voice = await self.voice_channel.connect()

        Thread(target=self.player).start()
        App.client.loop.create_task(self.update())

    def player(self):
        url = "rtmp://fms-base2.mitene.ad.jp/agqr/aandg333"

        while App.client.loop.is_running():
            with Popen(["rtmpdump", "--live", "-r", url], stdout=PIPE) as p:
                source = PCMVolumeTransformer(FFmpegPCMAudio(p.stdout, pipe=True), volume=App.config.volume)
                self.voice.play(source, after=lambda _: p.kill())
                p.wait()

            time.sleep(5)

    async def update(self):
        last_program_name = None
        last_message = None

        async for message in self.text_channel.history(limit=10):
            if message.author == App.client.user:
                last_message = message
                break

        while App.client.loop.is_running():
            program = await AgqrProgram.get_on_air()

            if program.name != last_program_name:
                if self.text_channel:
                    async with self.text_channel.typing():
                        embed = Embed(
                            title=program.name,
                            description=program.description,
                            url=program.link_url or "https://www.agqr.jp",
                            color=0xe30067,
                            timestamp=datetime.utcnow()
                        )
                        embed.set_author(
                            name=program.personality if program.personality else "文化放送",
                            url=program.link_url or "https://www.agqr.jp"
                        )

                        if last_message:
                            await last_message.edit(embed=embed)
                        else:
                            last_message = await self.text_channel.send(embed=embed)

                await App.client.change_presence(
                    activity=Streaming(
                        name=program.name,
                        url="https://twitch.tv/slashnephy"
                    )
                )

                last_program_name = program.name

            await asyncio.sleep(30)

@dataclass
class AgqrProgram:
    name: str
    img_url: Optional[str]
    link_url: Optional[str]
    description: Optional[str]
    personality: Optional[str]
    ad_img_url: Optional[str]
    ad_link_url: Optional[str]
    music_title: Optional[str]
    music_artist: Optional[str]

    @classmethod
    async def get_on_air(cls) -> AgqrProgram:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate",
                "Accept-Language": "ja",
                "Cache-Control": "max-age=0",
                "Referer": "http://www.uniqueradio.jp/agplayerf/player3.php",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.115 Safari/537.36"
            }

            async with session.get("https://www.uniqueradio.jp/aandg", headers=headers) as response:
                text = await response.text()
                t = [
                    urllib.parse.unquote(re.sub("^.+?'(.*)';$", r"\1", line))
                    for line in text.splitlines()
                ]

                return AgqrProgram(
                    name=t[0],
                    img_url=t[1] if t[1] else None,
                    link_url=t[2] if t[2] else None,
                    description=re.sub("<.+?>", "", t[3].replace("<br>", "\n")) if t[3] else None,
                    personality=t[4] if t[4] else None,
                    ad_img_url=t[5] if t[5] else None,
                    ad_link_url=t[6] if t[6] else None,
                    music_title=t[7] if t[7] else None,
                    music_artist=t[8] if t[8] else None
                )
