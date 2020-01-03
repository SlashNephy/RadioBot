import logging

from discord import Status, Game
from discord.ext import commands

from .config import Config, Module

class App:
    config: Config
    logger: logging.Logger
    client: commands.Bot

    @classmethod
    def run(cls):
        cls.config = Config.load()

        cls.logger = logging.getLogger("RadioBot")
        cls.logger.setLevel(logging.INFO)

        handler = logging.StreamHandler()
        formatter = logging.Formatter(fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        handler.setFormatter(formatter)
        cls.logger.addHandler(handler)

        if cls.config.debug:
            cls.logger.setLevel(logging.DEBUG)

        cls.client = commands.Bot(cls.config.prefix)

        if cls.config.module == Module.Radiko:
            from .radiko import RadikoPlayer
            cls.client.add_cog(RadikoPlayer())
        elif cls.config.module == Module.Agqr:
            from .agqr import AgqrPlayer
            cls.client.add_cog(AgqrPlayer())
        elif cls.config.module == Module.RadioGarden:
            from .rgb import RadioGardenPlayer
            cls.client.add_cog(RadioGardenPlayer())

        cls.logger.info("Initialized.")

        cls.client.run(cls.config.token)
