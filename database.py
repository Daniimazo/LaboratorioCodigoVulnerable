"""SQLite access and non-destructive schema initialization."""

import os
import sqlite3
from contextlib import contextmanager

from werkzeug.security import generate_password_hash

from config import Config


def get_connection():
    conn = sqlite3.connect(Config.DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def connection():
    """Commit or roll back a transaction and always close the connection."""
    conn = get_connection()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    """Create missing tables and hash legacy plaintext passwords in place."""
    os.makedirs(os.path.dirname(Config.DATABASE) or ".", exist_ok=True)
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                rol TEXT NOT NULL CHECK (rol IN ('admin', 'docente', 'estudiante'))
            );
            CREATE TABLE IF NOT EXISTS estudiantes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                carrera TEXT NOT NULL,
                biografia TEXT
            );
            CREATE TABLE IF NOT EXISTS calificaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                estudiante_id INTEGER NOT NULL,
                materia TEXT NOT NULL,
                nota REAL NOT NULL CHECK (nota >= 0 AND nota <= 5),
                FOREIGN KEY (estudiante_id) REFERENCES estudiantes (id)
            );
            CREATE TABLE IF NOT EXISTS archivos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre_archivo TEXT NOT NULL,
                ruta TEXT NOT NULL,
                subido_por INTEGER,
                FOREIGN KEY (subido_por) REFERENCES usuarios (id)
            );
            """
        )

        # Upgrade the original lab schema without deleting user data.
        user_columns = {row[1] for row in conn.execute("PRAGMA table_info(usuarios)")}
        if "username" in user_columns:
            for row in conn.execute("SELECT id, password FROM usuarios").fetchall():
                stored = row["password"]
                if not stored.startswith(("scrypt:", "pbkdf2:")):
                    conn.execute(
                        "UPDATE usuarios SET password = ? WHERE id = ?",
                        (generate_password_hash(stored), row["id"]),
                    )

        # Seed public demonstration data only when those tables are empty.
        if conn.execute("SELECT COUNT(*) FROM estudiantes").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO estudiantes (nombre, carrera, biografia) VALUES (?, ?, ?)",
                [
                    ("Ana Torres", "Ingenieria de Sistemas", "Estudiante de septimo semestre."),
                    ("Luis Gomez", "Ciberseguridad", "Interesado en pentesting."),
                    ("Maria Ruiz", "Ciencia de Datos", "Le gusta el machine learning."),
                ],
            )
        if conn.execute("SELECT COUNT(*) FROM calificaciones").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO calificaciones (estudiante_id, materia, nota) VALUES (?, ?, ?)",
                [(1, "Redes", 4.2), (1, "Bases de Datos", 3.8), (2, "Criptografia", 4.7), (3, "Estadistica", 3.5)],
            )


def create_user(username, password, role="estudiante"):
    """Create a user with an application-generated password hash."""
    if role not in {"admin", "docente", "estudiante"}:
        raise ValueError("Rol no valido.")
    if len(password) < 12:
        raise ValueError("La contrasena debe tener al menos 12 caracteres.")
    if not username or len(username) > 80:
        raise ValueError("El usuario debe tener entre 1 y 80 caracteres.")
    with connection() as conn:
        conn.execute(
            "INSERT INTO usuarios (username, password, rol) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), role),
        )


def set_user_password(username, password):
    """Set a user's password without storing the plaintext password."""
    if len(password) < 12:
        raise ValueError("La contrasena debe tener al menos 12 caracteres.")
    with connection() as conn:
        result = conn.execute(
            "UPDATE usuarios SET password = ? WHERE username = ?",
            (generate_password_hash(password), username),
        )
        if result.rowcount == 0:
            raise ValueError("El usuario no existe.")
