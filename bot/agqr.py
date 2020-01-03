import asyncio
import re
import time
import urllib.parse
from asyncio import Task
from datetime import datetime
from subprocess import PIPE, Popen
from threading import Thread
from typing import Any, Dict, Optional

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
            await self.text_channel.purge(check=lambda x: x.author == App.client.user)
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

    async def get_on_air(self) -> Dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate",
                "Accept-Language": "ja",
                "Cache-Control": "max-age=0",
                "Referer": "http://www.uniqueradio.jp/agplayerf/player3.php",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.115 Safari/537.36"
            }

            async with session.get("http://www.uniqueradio.jp/aandg", headers=headers) as response:
                t = [
                    urllib.parse.unquote(re.sub("^.+?'(.*)';$", r"\1", line))
                    for line in (await response.text()).splitlines()
                ]

                return {
                    "name": t[0],
                    "banner_url": t[1] if t[1] else None,
                    "url": t[2] if t[2] else None,
                    "description": re.sub("<.+?>", "", t[3].replace("<br>", "\n")) if t[3] else None,
                    "cast": t[4] if t[4] else None,
                    "ad_img_url": t[5] if t[5] else None,
                    "ad_url": t[6] if t[6] else None,
                    "music_title": t[7] if t[7] else None,
                    "music_artist": t[8] if t[8] else None
                }

    async def update(self):
        last_program_name = None
        last_message = None

        while App.client.loop.is_running():
            program = await self.get_on_air()

            if program["name"] != last_program_name:
                if self.text_channel:
                    async with self.text_channel.typing():
                        embed = Embed(
                            title=program["name"],
                            description=program["description"],
                            url=program["url"] or "https://www.agqr.jp",
                            color=0xe30067,
                        )
                        embed.set_author(
                            name=program["cast"] if program["cast"] else program["name"],
                            url=program["url"] or "https://www.agqr.jp"
                        )

                        if last_message:
                            last_message = await last_message.edit(embed=embed)
                        else:
                            last_message = await self.text_channel.send(embed=embed)

                await App.client.change_presence(
                    activity=Streaming(
                        name=program["name"] + " (超A&G+)",
                        url="https://twitch.tv/slashnephy"
                    )
                )

                last_program_name = program["name"]

            await asyncio.sleep(30)
