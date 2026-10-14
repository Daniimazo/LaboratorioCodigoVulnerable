"""
database.py
-----------
Crea la base de datos SQLite del laboratorio y carga datos de ejemplo.

ADVERTENCIA: Este archivo forma parte de un ENTORNO INTENCIONALMENTE
VULNERABLE con fines EDUCATIVOS. No usar en produccion.
"""

import os
import sqlite3

DB_NAME = "academia.db"


def get_connection():
    """Devuelve una conexion a la base de datos SQLite."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Crea las tablas y carga los datos de ejemplo desde cero."""
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)

    conn = get_connection()
    cur = conn.cursor()

    # ------------------------------------------------------------------
    # Tabla de usuarios (login del sistema)
    # ------------------------------------------------------------------
    cur.execute(
        """
        CREATE TABLE usuarios (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            password TEXT NOT NULL,   -- MALA PRACTICA: contrasena en texto plano
            rol      TEXT NOT NULL    -- admin | docente | estudiante
        )
        """
    )

    # ------------------------------------------------------------------
    # Tabla de estudiantes
    # ------------------------------------------------------------------
    cur.execute(
        """
        CREATE TABLE estudiantes (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre    TEXT NOT NULL,
            carrera   TEXT NOT NULL,
            biografia TEXT             -- campo libre: sera el punto de XSS almacenado
        )
        """
    )

    # ------------------------------------------------------------------
    # Tabla de calificaciones
    # ------------------------------------------------------------------
    cur.execute(
        """
        CREATE TABLE calificaciones (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            estudiante_id INTEGER NOT NULL,
            materia       TEXT NOT NULL,
            nota          REAL NOT NULL,
            FOREIGN KEY (estudiante_id) REFERENCES estudiantes (id)
        )
        """
    )

    # ------------------------------------------------------------------
    # Tabla de archivos subidos
    # ------------------------------------------------------------------
    cur.execute(
        """
        CREATE TABLE archivos (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_archivo TEXT NOT NULL,
            ruta          TEXT NOT NULL,
            subido_por    INTEGER
        )
        """
    )

    # ------------------------------------------------------------------
    # Datos de ejemplo: 3 usuarios con contrasenas en TEXTO PLANO
    # (mala practica deliberada para demostrar en clase)
    # ------------------------------------------------------------------
    usuarios = [
        ("admin", "admin123", "admin"),        # profesor administrador
        ("profesor", "clave456", "docente"),   # profesor estandar
        ("estudiante", "1234", "estudiante"),  # estudiante
    ]
    cur.executemany(
        "INSERT INTO usuarios (username, password, rol) VALUES (?, ?, ?)",
        usuarios,
    )

    # Datos de ejemplo: estudiantes
    estudiantes = [
        ("Ana Torres", "Ingenieria de Sistemas", "Estudiante de septimo semestre."),
        ("Luis Gomez", "Ciberseguridad", "Interesado en pentesting."),
        ("Maria Ruiz", "Ciencia de Datos", "Le gusta el machine learning."),
    ]
    cur.executemany(
        "INSERT INTO estudiantes (nombre, carrera, biografia) VALUES (?, ?, ?)",
        estudiantes,
    )

    # Datos de ejemplo: calificaciones
    calificaciones = [
        (1, "Redes", 4.2),
        (1, "Bases de Datos", 3.8),
        (2, "Criptografia", 4.7),
        (3, "Estadistica", 3.5),
    ]
    cur.executemany(
        "INSERT INTO calificaciones (estudiante_id, materia, nota) VALUES (?, ?, ?)",
        calificaciones,
    )

    conn.commit()
    conn.close()
    print(f"Base de datos '{DB_NAME}' creada con datos de ejemplo.")


if __name__ == "__main__":
    init_db()
