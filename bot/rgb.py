import asyncio
import time
from datetime import datetime
from subprocess import PIPE, Popen
from threading import Thread
from typing import Optional

from discord import (Embed, PCMAudio, PCMVolumeTransformer, Streaming,
                     TextChannel, VoiceChannel, VoiceClient)
from discord.ext import commands
from discord.opus import Encoder

from bot.app import App


class RadioGardenPlayer(commands.Cog):
    voice: VoiceClient
    voice_channel: VoiceChannel
    text_channel: Optional[TextChannel]

    @commands.Cog.listener()
    async def on_ready(self):
        App.logger.debug("Rgb module loaded.")

        if App.config.text_channel_id:
            self.text_channel = App.client.get_channel(App.config.text_channel_id)
        self.voice_channel = App.client.get_channel(App.config.voice_channel_id)

        member = self.voice_channel.guild.get_member(App.client.user.id)
        if member.nick != "Radio Garden":
            await member.edit(nick="Radio Garden")
            with open("resources/rgb.png", "rb") as f:
                await App.client.user.edit(avatar=f.read())

        # バグ対応のため, 一度接続して切断する
        await (await self.voice_channel.connect()).disconnect()
        self.voice = await self.voice_channel.connect()

        Thread(target=self.player).start()
        App.client.loop.create_task(self.update())

    def player(self):
        while App.client.loop.is_running():
            with Popen(["ffmpeg", "-i", App.config.radio_garden_url, "-f", "s16le", "-ar", str(Encoder.SAMPLING_RATE), "-ac", str(Encoder.CHANNELS), "-loglevel", "warning", "pipe:1"], stdout=PIPE) as p:
                source = PCMVolumeTransformer(PCMAudio(p.stdout), volume=App.config.volume)
                self.voice.play(source, after=lambda _: p.kill())
                p.wait()

            time.sleep(5)

    async def update(self):
        last_url = None
        last_message = None

        async for message in self.text_channel.history(limit=10):
            if message.author == App.client.user:
                last_message = message
                break

        while App.client.loop.is_running():
            url = App.config.radio_garden_url

            if url != last_url:
                if self.text_channel:
                    async with self.text_channel.typing():
                        embed = Embed(
                            description=url,
                            color=0x42f58d,
                            timestamp=datetime.utcnow()
                        )
                        embed.set_author(
                            name="Radio Garden",
                            url="https://radio.garden"
                        )

                        if last_message:
                            await last_message.edit(embed=embed)
                        else:
                            last_message = await self.text_channel.send(embed=embed)

                await App.client.change_presence(
                    activity=Streaming(
                        name=url,
                        url="https://twitch.tv/slashnephy"
                    )
                )

                last_url = url

            await asyncio.sleep(30)
