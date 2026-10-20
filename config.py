"""Application configuration loaded from environment variables."""

import os
import secrets
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    DATABASE = str(Path(os.environ.get("DATABASE_PATH", BASE_DIR / "academia.db")).resolve())
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{Path(DATABASE).as_posix()}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", str(BASE_DIR / "uploads"))
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 5 * 1024 * 1024))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    PERMANENT_SESSION_LIFETIME = 1800
    SESSION_REFRESH_EACH_REQUEST = False
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("LOGIN_RATE_LIMIT_WINDOW_SECONDS", 900))
    LOGIN_ACCOUNT_FAILURES = int(os.environ.get("LOGIN_ACCOUNT_FAILURES", 5))
    LOGIN_ADDRESS_FAILURES = int(os.environ.get("LOGIN_ADDRESS_FAILURES", 20))


class DevelopmentConfig(Config):
    DEBUG = False


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True

    @classmethod
    def validate(cls):
        if not os.environ.get("SECRET_KEY"):
            raise RuntimeError("SECRET_KEY debe configurarse en produccion.")
        if len(os.environ["SECRET_KEY"]) < 32:
            raise RuntimeError("SECRET_KEY debe tener al menos 32 caracteres en produccion.")
