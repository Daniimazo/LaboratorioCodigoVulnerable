"""Application configuration loaded from environment variables."""

import os
import secrets
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    DATABASE = os.environ.get("DATABASE_PATH", str(BASE_DIR / "academia.db"))
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", str(BASE_DIR / "uploads"))
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 5 * 1024 * 1024))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    PERMANENT_SESSION_LIFETIME = 1800


class DevelopmentConfig(Config):
    DEBUG = False


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True

    @classmethod
    def validate(cls):
        if not os.environ.get("SECRET_KEY"):
            raise RuntimeError("SECRET_KEY debe configurarse en produccion.")
