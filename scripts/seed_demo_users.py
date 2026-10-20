"""Create or reset local-only demonstration accounts using the ORM."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app
from database import create_user, init_db, set_user_password
from extensions import db
from models import Student, User


DEMO_USERS = (
    ("admin", "AdminDemo-2026!", "admin"),
    ("profesor", "DocenteDemo-2026!", "docente"),
    ("demo_estudiante", "EstudianteDemo-2026!", "estudiante"),
)


def provision(username, password, role, student_id=None):
    user = User.query.filter(User.username.collate("NOCASE") == username).first()
    if user is None:
        create_user(username, password, role, student_id=student_id)
        return
    if user.rol != role:
        raise RuntimeError(
            f"La cuenta {username!r} ya existe con el rol {user.rol!r}; no se modificó su rol."
        )
    if role == "estudiante" and user.estudiante_id != student_id:
        raise RuntimeError(
            f"La cuenta {username!r} ya está asociada a otro perfil; no se modificó la asociación."
        )
    set_user_password(username, password)


def main():
    if os.environ.get("APP_ENV", "development").lower() == "production":
        raise SystemExit("No se crean cuentas demo cuando APP_ENV=production.")

    with app.app_context():
        init_db()
        profiles = Student.query.filter(
            Student.nombre.collate("NOCASE") == "Perfil de demostracion"
        ).all()
        if len(profiles) > 1:
            raise RuntimeError("Hay varios perfiles de demostración; resuélvelos manualmente.")
        if profiles:
            student_id = profiles[0].id
        else:
            profile = Student(
                nombre="Perfil de demostracion",
                carrera="Ingeniería de Sistemas",
                biografia="Perfil de prueba para validar permisos de estudiante.",
            )
            db.session.add(profile)
            db.session.commit()
            student_id = profile.id

        for username, password, role in DEMO_USERS:
            provision(
                username,
                password,
                role,
                student_id=student_id if role == "estudiante" else None,
            )

    print("Cuentas demo locales listas. No las uses en producción.")
    for username, password, _role in DEMO_USERS:
        print(f"  {username}: {password}")


if __name__ == "__main__":
    main()
