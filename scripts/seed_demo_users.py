"""Create or reset local-only demonstration accounts.

Never use these public credentials in production.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import connection, create_user, init_db, set_user_password


DEMO_USERS = (
    ("admin", "AdminDemo-2026!", "admin"),
    ("profesor", "DocenteDemo-2026!", "docente"),
    ("demo_estudiante", "EstudianteDemo-2026!", "estudiante"),
)


def provision(username, password, role, student_id=None):
    with connection() as conn:
        user = conn.execute(
            "SELECT id, rol, estudiante_id FROM usuarios "
            "WHERE username = ? COLLATE NOCASE",
            (username,),
        ).fetchone()

    if user is None:
        create_user(username, password, role, student_id=student_id)
        return
    if user["rol"] != role:
        raise RuntimeError(
            f"La cuenta {username!r} ya existe con el rol {user['rol']!r}; "
            "no se modifico su rol."
        )
    if role == "estudiante" and user["estudiante_id"] != student_id:
        raise RuntimeError(
            f"La cuenta {username!r} ya esta asociada a otro perfil; "
            "no se modifico la asociacion."
        )
    set_user_password(username, password)


def main():
    if os.environ.get("APP_ENV", "development").lower() == "production":
        raise SystemExit("No se crean cuentas demo cuando APP_ENV=production.")

    init_db()
    with connection() as conn:
        profiles = conn.execute(
            "SELECT id FROM estudiantes WHERE nombre = ? COLLATE NOCASE",
            ("Perfil de demostracion",),
        ).fetchall()
        if len(profiles) > 1:
            raise RuntimeError("Hay varios perfiles de demostracion; resuelvelos manualmente.")
        if profiles:
            student_id = profiles[0]["id"]
        else:
            cursor = conn.execute(
                "INSERT INTO estudiantes (nombre, carrera, biografia) VALUES (?, ?, ?)",
                (
                    "Perfil de demostracion",
                    "Ingenieria de Sistemas",
                    "Perfil de prueba para validar permisos de estudiante.",
                ),
            )
            student_id = cursor.lastrowid

    for username, password, role in DEMO_USERS:
        provision(
            username,
            password,
            role,
            student_id=student_id if role == "estudiante" else None,
        )

    print("Cuentas demo locales listas. No las uses en produccion.")
    for username, password, _ in DEMO_USERS:
        print(f"  {username}: {password}")


if __name__ == "__main__":
    main()
