from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional

CONFIG_PATH: str = "config.json"


class Module(Enum):
    Radiko = 0
    Agqr = 1
    RadioGarden = 2

@dataclass
class Config:
    debug: bool
    token: str
    volume: float
    prefix: str

    voice_channel_id: str
    text_channel_id: Optional[str]

    module: Module
    radiko_area: Optional[str]
    radiko_station: Optional[str]
    radio_garden_url: Optional[str]

    @staticmethod
    def load() -> Config:
        with open(CONFIG_PATH, "r") as f:
            d = json.load(f)

        return Config(
            debug=d.get("debug", False),
            token=d["token"],
            volume=d.get("volume") or 1.0,
            prefix=d.get("prefix") or "r!",
            voice_channel_id=d["voice_channel_id"],
            text_channel_id=d.get("text_channel_id"),
            module=Module(d.get("module") or 1),
            radiko_area=d.get("radiko_area"),
            radiko_station=d.get("radiko_station"),
            radio_garden_url=d.get("radio_garden_url")
        )
