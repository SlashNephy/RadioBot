from __future__ import annotations

import asyncio
import base64
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from subprocess import PIPE, Popen
from threading import Thread
from typing import Dict, Optional

import aiohttp
import requests
import xmltodict
from discord import (Embed, FFmpegPCMAudio, PCMVolumeTransformer, Streaming,
                     TextChannel, VoiceChannel, VoiceClient)
from discord.ext import commands

from bot.app import App


class RadikoPlayer(commands.Cog):
    voice: VoiceClient
    voice_channel: VoiceChannel
    text_channel: Optional[TextChannel]

    api: RadikoApiClient

    @commands.Cog.listener()
    async def on_ready(self):
        App.logger.debug("Radiko module loaded.")

        if App.config.text_channel_id:
            self.text_channel = App.client.get_channel(App.config.text_channel_id)
        self.voice_channel = App.client.get_channel(App.config.voice_channel_id)

        try:
            member = self.voice_channel.guild.get_member(App.client.user.id)
            if member.nick != "Radiko":
                await member.edit(nick="Radiko")
                with open("resources/radiko.png", "rb") as f:
                    await App.client.user.edit(avatar=f.read())
        except Exception as e:
            logging.exception("Failed to change nickname or avatar.", exc_info=e)

        # バグ対応のため, 一度接続して切断する
        await (await self.voice_channel.connect()).disconnect()
        self.voice = await self.voice_channel.connect()

        self.api = RadikoApiClient()
        await self.api.login()

        Thread(target=self.player).start()
        App.client.loop.create_task(self.update())

    def player(self):
        while App.client.loop.is_running():
            with Popen(["rtmpdump", "--live", "--rtmp", self.api.rtmp_url, "--swfVfy", "http://radiko.jp/apps/js/flash/myplayer-release.swf", "--pageUrl", "http://radiko.jp", "-C", "S:", "-C", "S:", "-C", "S:", "-C", f"S:{self.api.rtmp_token}"], stdout=PIPE) as p:
                source = PCMVolumeTransformer(FFmpegPCMAudio(p.stdout, pipe=True), volume=App.config.volume)
                self.voice.play(source, after=lambda _: p.kill())
                p.wait()

            time.sleep(5)

    async def update(self):
        last_program_title = None
        last_message = None
        last_login = datetime.now()

        async for message in self.text_channel.history(limit=10):
            if message.author == App.client.user:
                last_message = message
                break

        while App.client.loop.is_running():
            program = await self.api.get_on_air()

            if program.title != last_program_title:
                if self.text_channel:
                    async with self.text_channel.typing():
                        embed = Embed(
                            title=program.title,
                            description=f"{program.description or ''}\n{program.info}"[:500] + "...",
                            url=program.url,
                            color=0x00a7e9,
                            timestamp=datetime.utcnow()
                        )
                        embed.set_image(
                            url=program.banner_url
                        )
                        embed.set_author(
                            name=f"{program.cast} ({program.station_name})" if program.cast else program.station_name,
                            url=f"http://radiko.jp/#!/live/{program.station_id}"
                        )
                        embed.set_footer(
                            text=f"{program.start} - {program.end} ({program.sec // 60} 分間)",
                        )

                        if last_message:
                            await last_message.edit(embed=embed)
                        else:
                            last_message = await self.text_channel.send(embed=embed)

                await App.client.change_presence(
                    activity=Streaming(
                        name=f"{program.title} ({program.start} - {program.end})",
                        url="https://twitch.tv/slashnephy"
                    )
                )

                if datetime.now() - last_login > timedelta(hours=3):
                    await self.api.login()
                    last_login = datetime.now()

                last_program_title = program.title

            await asyncio.sleep(30)

class RadikoApiClient:
    headers: Dict[str, Optional[str]] = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "ja",
        "Origin": "http://radiko.jp",
        "pragma": "no-cache",
        "Referer": "http://radiko.jp/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.115 Safari/537.36",
        "X-Radiko-App": "pc_ts",
        "X-Radiko-App-Version": "4.0.0",
        "X-Radiko-Device": "pc",
        "X-Radiko-User": "test-stream",
        "X-Requested-With": "ShockwaveFlash/26.0.0.137"
    }

    @property
    def area_id(self) -> str:
        return App.config.radiko_area or "JP13"

    @property
    def station_id(self) -> str:
        return App.config.radiko_station or "QRR"

    @property
    def rtmp_url(self) -> str:
        return xmltodict.parse(requests.get(f"https://radiko.jp/v2/station/stream_multi/{self.station_id}.xml", headers={
            "Accept": "application/xml, text/xml, */*; q=0.01",
            "Referer": "http://radiko.jp/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.115 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest"
        }).text)["url"]["item"][0]["#text"]

    @property
    def rtmp_token(self) -> Optional[str]:
        return self.headers.get("X-Radiko-AuthToken")

    @property
    def is_authenticated(self) -> bool:
        return self.rtmp_token != None

    async def login(self):
        if "X-Radiko-AuthToken" in self.headers:
            del self.headers["X-Radiko-AuthToken"]

        async with aiohttp.ClientSession() as session:
            async with session.post("https://radiko.jp/v2/api/auth1_fms", data="\r\n", headers=self.headers) as response:
                self.headers["X-Radiko-AuthToken"] = response.headers["X-RADIKO-AUTHTOKEN"]

            tmp_headers = self.headers.copy()
            with open("resources/authkey.jpg", "rb") as f:
                f.seek(int(response.headers["X-Radiko-KeyOffset"]))
                tmp_headers["X-Radiko-PartialKey"] = base64.b64encode(f.read(int(response.headers["X-Radiko-KeyLength"]))).decode()

            async with session.post("https://radiko.jp/v2/api/auth2_fms", data="\r\n", headers=tmp_headers) as response:
                App.logger.info(f"Logged in Radiko with area {(await response.text()).strip()}")

    @staticmethod
    async def extract_authkey_jpg(self):
        filename: str = "player.swf"
        with open(filename, "wb") as f:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://radiko.jp/apps/js/flash/myplayer-release.swf") as response:
                    f.write(await response.read())

        with Popen(["swfextract", "-b", "12", "-o", "authkey.jpg", filename]) as p:
            p.wait()

    async def get_on_air(self) -> Optional[Dict]:
        if not self.is_authenticated:
            return None

        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://radiko.jp/v3/program/now/{self.area_id}.xml", headers=self.headers) as response:
                text = await response.text()

                for station in xmltodict.parse(text)["radiko"]["stations"]["station"]:
                    if station["@id"] == self.station_id:
                        program = station["progs"]["prog"][0]

                        return RadikoProgram(
                            station_id=station["@id"],
                            station_name=station["name"],
                            start=f"{program['@ftl'][0:-2]}:{program['@ftl'][-2:]}",
                            end=f"{program['@tol'][0:-2]}:{program['@tol'][-2:]}",
                            id=program["@id"],
                            sec=int(program["@dur"]),
                            title=program["title"],
                            url=program["url"],
                            description=program["desc"],
                            info=re.sub("<.+?>", "", program["info"].replace("<br />", "\n")).strip() if program["info"] else None,
                            cast=program["pfm"],
                            banner_url=program["img"]
                        )

@dataclass
class RadikoProgram:
    station_id: str
    station_name: str
    start: str
    end: str
    id: str
    sec: int
    title: str
    url: str
    description: Optional[str]
    info: Optional[str]
    cast: Optional[str]
    banner_url: str
