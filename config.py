"""
Database configuration.

Settings are read from environment variables. For local development, put them
in a `.env` file next to this module (see `.env.example`); it is loaded
automatically and never overrides variables already set in the environment.
"""
import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent / ".env"


def _load_env_file(path=ENV_FILE):
    """Load KEY=VALUE pairs from a .env file into os.environ (no extra dependency)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "sparkifydb")
# Existing database used only to drop/create DB_NAME.
DB_ADMIN_DB = os.getenv("DB_ADMIN_DB", "postgres")


def dsn(dbname=DB_NAME):
    """Return a libpq connection string for the given database."""
    return (
        f"host={DB_HOST} port={DB_PORT} dbname={dbname} "
        f"user={DB_USER} password={DB_PASSWORD}"
    )
