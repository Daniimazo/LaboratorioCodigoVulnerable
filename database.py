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
                rol TEXT NOT NULL CHECK (rol IN ('admin', 'docente', 'estudiante')),
                estudiante_id INTEGER UNIQUE REFERENCES estudiantes (id),
                session_version INTEGER NOT NULL DEFAULT 0
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
            CREATE TABLE IF NOT EXISTS login_rate_limits (
                key TEXT PRIMARY KEY,
                failures INTEGER NOT NULL,
                window_started REAL NOT NULL,
                blocked_until REAL NOT NULL DEFAULT 0
            );
            """
        )

        # Upgrade the original lab schema without deleting user data.
        user_columns = {row[1] for row in conn.execute("PRAGMA table_info(usuarios)")}
        if "estudiante_id" not in user_columns:
            conn.execute(
                "ALTER TABLE usuarios ADD COLUMN estudiante_id INTEGER REFERENCES estudiantes (id)"
            )
        if "session_version" not in user_columns:
            conn.execute(
                "ALTER TABLE usuarios ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0"
            )

        duplicate_usernames = conn.execute(
            "SELECT username, GROUP_CONCAT(id) AS ids FROM usuarios "
            "GROUP BY username COLLATE NOCASE HAVING COUNT(*) > 1"
        ).fetchall()
        if duplicate_usernames:
            duplicates = "; ".join(
                f"{row['username']!r} (IDs {row['ids']})" for row in duplicate_usernames
            )
            raise RuntimeError(
                "Hay nombres de usuario duplicados (sin distinguir mayusculas) en "
                f"la base de datos: {duplicates}. Resuelvelos antes de iniciar."
            )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_username_nocase "
            "ON usuarios(username COLLATE NOCASE)"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_estudiante "
            "ON usuarios(estudiante_id) WHERE estudiante_id IS NOT NULL"
        )

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
            seed_grades = {
                "Ana Torres": [("Redes", 4.2), ("Bases de Datos", 3.8)],
                "Luis Gomez": [("Criptografia", 4.7)],
                "Maria Ruiz": [("Estadistica", 3.5)],
            }
            for name, grades in seed_grades.items():
                matches = conn.execute(
                    "SELECT id FROM estudiantes WHERE nombre = ? COLLATE NOCASE", (name,)
                ).fetchall()
                if len(matches) == 1:
                    conn.executemany(
                        "INSERT INTO calificaciones (estudiante_id, materia, nota) "
                        "VALUES (?, ?, ?)",
                        [(matches[0]["id"], subject, grade) for subject, grade in grades],
                    )

        # Safely link legacy student accounts only when the name maps to one profile.
        used_student_ids = {
            row[0]
            for row in conn.execute(
                "SELECT estudiante_id FROM usuarios WHERE estudiante_id IS NOT NULL"
            )
        }
        students = conn.execute("SELECT id, nombre FROM estudiantes").fetchall()
        for user in conn.execute(
            "SELECT id, username FROM usuarios "
            "WHERE rol = 'estudiante' AND estudiante_id IS NULL"
        ).fetchall():
            matches = [
                student["id"]
                for student in students
                if student["nombre"].strip().casefold() == user["username"].strip().casefold()
            ]
            if len(matches) == 1 and matches[0] not in used_student_ids:
                conn.execute(
                    "UPDATE usuarios SET estudiante_id = ? WHERE id = ?",
                    (matches[0], user["id"]),
                )
                used_student_ids.add(matches[0])


def create_user(username, password, role="estudiante", student_id=None):
    """Create a user with an application-generated password hash."""
    if role not in {"admin", "docente", "estudiante"}:
        raise ValueError("Rol no valido.")
    if len(password) < 12:
        raise ValueError("La contrasena debe tener al menos 12 caracteres.")
    if not username or len(username) > 80:
        raise ValueError("El usuario debe tener entre 1 y 80 caracteres.")
    username = username.strip()
    if not username:
        raise ValueError("El usuario no puede estar vacio.")
    if role == "estudiante" and student_id is None:
        raise ValueError("Asocia la cuenta estudiante con un student_id existente.")
    if role != "estudiante" and student_id is not None:
        raise ValueError("Solo las cuentas estudiante pueden asociarse a un perfil.")
    with connection() as conn:
        existing = conn.execute(
            "SELECT id FROM usuarios WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone()
        if existing:
            raise ValueError("Ya existe una cuenta con ese nombre de usuario.")
        if student_id is not None and not conn.execute(
            "SELECT 1 FROM estudiantes WHERE id = ?", (student_id,)
        ).fetchone():
            raise ValueError("El perfil estudiante indicado no existe.")
        conn.execute(
            "INSERT INTO usuarios (username, password, rol, estudiante_id) "
            "VALUES (?, ?, ?, ?)",
            (username, generate_password_hash(password), role, student_id),
        )


def set_user_password(username, password):
    """Set a user's password without storing the plaintext password."""
    if len(password) < 12:
        raise ValueError("La contrasena debe tener al menos 12 caracteres.")
    with connection() as conn:
        users = conn.execute(
            "SELECT id FROM usuarios WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchall()
        if not users:
            raise ValueError("El usuario no existe.")
        if len(users) != 1:
            raise ValueError("Hay varias cuentas con ese nombre; resuelve los duplicados primero.")
        conn.execute(
            "UPDATE usuarios SET password = ?, session_version = session_version + 1 "
            "WHERE id = ?",
            (generate_password_hash(password), users[0]["id"]),
        )


def link_student_account(username, student_id):
    """Associate an existing student login with one exact student profile."""
    with connection() as conn:
        users = conn.execute(
            "SELECT id FROM usuarios WHERE username = ? COLLATE NOCASE "
            "AND rol = 'estudiante'",
            (username,),
        ).fetchall()
        if not users:
            raise ValueError("No existe una cuenta estudiante con ese usuario.")
        if len(users) != 1:
            raise ValueError("Hay varias cuentas con ese nombre; resuelve los duplicados primero.")
        if not conn.execute("SELECT 1 FROM estudiantes WHERE id = ?", (student_id,)).fetchone():
            raise ValueError("El perfil estudiante indicado no existe.")
        conn.execute(
            "UPDATE usuarios SET estudiante_id = ? WHERE id = ?",
            (student_id, users[0]["id"]),
        )
