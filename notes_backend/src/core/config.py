"""
Application configuration for notes_backend.

This module centralizes environment-based configuration and provides a typed
configuration object for the rest of the codebase.
"""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class AppConfig:
    """Typed configuration used throughout the backend."""
    sqlite_db_path: str
    cors_allow_origins: list[str]


# PUBLIC_INTERFACE
def get_config() -> AppConfig:
    """
    Build and return the application configuration.

    Contract:
      - Inputs: environment variables
          - SQLITE_DB (optional): path to sqlite database file.
          - CORS_ALLOW_ORIGINS (optional): comma-separated origins, or "*" (default).
      - Output: AppConfig
      - Errors: none (falls back to safe defaults)
      - Side effects: none
    """
    sqlite_db_path = os.environ.get("SQLITE_DB") or "myapp.db"
    cors_origins_raw = (os.environ.get("CORS_ALLOW_ORIGINS") or "*").strip()

    if cors_origins_raw == "*":
        cors_allow_origins = ["*"]
    else:
        cors_allow_origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()]

    return AppConfig(sqlite_db_path=sqlite_db_path, cors_allow_origins=cors_allow_origins)
