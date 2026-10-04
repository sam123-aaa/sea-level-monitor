import os

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine


db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(connection, _record):
    """SQLite leaves foreign-key checks off unless each connection enables them."""
    if connection.__class__.__module__ == "sqlite3":
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def database_url():
    configured = os.getenv("DATABASE_URL")
    if configured:
        if not configured.startswith("sqlite:"):
            raise RuntimeError("This application currently supports SQLite only; set DATABASE_URL to a sqlite URL")
        return configured
    if os.getenv("AMVERA"):
        path = "/data/sea_level.db"
    else:
        path = os.getenv("SQLITE_PATH", "sea_level.db")
    return "sqlite:///" + os.path.abspath(path).replace("\\", "/")
