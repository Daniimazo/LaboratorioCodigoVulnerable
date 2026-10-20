"""Shared Flask extensions, initialized by the application factory module."""

import sqlite3

from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine


db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "Inicia sesión para acceder a este módulo."
login_manager.login_message_category = "error"


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(connection, _record):
    """SQLite leaves FK enforcement off unless enabled per connection."""
    if isinstance(connection, sqlite3.Connection):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
