"""Environment-based configuration using standard PostgreSQL connection strings."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    log_level: str = "INFO"

    @classmethod
    def from_environment(cls) -> "Settings":
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        return cls(database_url=database_url, log_level=os.getenv("LOG_LEVEL", "INFO"))

