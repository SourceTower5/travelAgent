from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    database_path: str
    ollama_model: str


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        database_path=os.getenv("TRAVEL_AGENT_DB", "travel_agent.sqlite"),
        ollama_model=os.getenv("OLLAMA_MODEL", "ollama/qwen2.5:7b"),
    )
