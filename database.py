"""SQLAlchemy database initialization and account-management helpers."""

from pathlib import Path

from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash

from extensions import db
from models import Grade, Student, User


def init_db():
    """Create missing tables and perform non-destructive legacy upgrades.

    Call inside an application context. Existing academic records are retained.
    """
    Path(db.engine.url.database).parent.mkdir(parents=True, exist_ok=True)
    db.create_all()

    # Keep installations made with earlier versions usable. SQLite cannot add
    # UNIQUE/FK constraints to an existing table without rebuilding it, so the
    # corresponding uniqueness guarantee is enforced with an index here.
    user_columns = {column["name"] for column in inspect(db.engine).get_columns("usuarios")}
    with db.engine.begin() as connection:
        if "estudiante_id" not in user_columns:
            connection.execute(text(
                "ALTER TABLE usuarios ADD COLUMN estudiante_id INTEGER REFERENCES estudiantes(id)"
            ))
        if "session_version" not in user_columns:
            connection.execute(text(
                "ALTER TABLE usuarios ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0"
            ))

        duplicates = connection.execute(text(
            "SELECT username, GROUP_CONCAT(id) AS ids FROM usuarios "
            "GROUP BY username COLLATE NOCASE HAVING COUNT(*) > 1"
        )).mappings().all()
        if duplicates:
            description = "; ".join(f"{row['username']!r} (IDs {row['ids']})" for row in duplicates)
            raise RuntimeError(
                "Hay nombres de usuario duplicados (sin distinguir mayúsculas) en "
                f"la base de datos: {description}. Resuélvelos antes de iniciar."
            )
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_username_nocase "
            "ON usuarios(username COLLATE NOCASE)"
        ))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_estudiante "
            "ON usuarios(estudiante_id) WHERE estudiante_id IS NOT NULL"
        ))

    # Convert legacy plaintext passwords, then seed only empty academic tables.
    for user in User.query.all():
        if not user.password.startswith(("scrypt:", "pbkdf2:")):
            user.password = generate_password_hash(user.password)

    if Student.query.count() == 0:
        db.session.add_all([
            Student(nombre="Ana Torres", carrera="Ingeniería de Sistemas", biografia="Estudiante de séptimo semestre."),
            Student(nombre="Luis Gomez", carrera="Ciberseguridad", biografia="Interesado en pentesting."),
            Student(nombre="Maria Ruiz", carrera="Ciencia de Datos", biografia="Le gusta el machine learning."),
        ])
        db.session.flush()

    if Grade.query.count() == 0:
        seed_grades = {
            "Ana Torres": [("Redes", 4.2), ("Bases de Datos", 3.8)],
            "Luis Gomez": [("Criptografía", 4.7)],
            "Maria Ruiz": [("Estadística", 3.5)],
        }
        for name, grades in seed_grades.items():
            matches = Student.query.filter(Student.nombre.collate("NOCASE") == name).all()
            if len(matches) == 1:
                db.session.add_all(
                    Grade(estudiante_id=matches[0].id, materia=subject, nota=grade)
                    for subject, grade in grades
                )

    linked = {user.estudiante_id for user in User.query.filter(User.estudiante_id.isnot(None)).all()}
    students_by_name = {}
    for student in Student.query.all():
        students_by_name.setdefault(student.nombre.strip().casefold(), []).append(student.id)
    for user in User.query.filter_by(rol="estudiante", estudiante_id=None).all():
        candidates = students_by_name.get(user.username.strip().casefold(), [])
        if len(candidates) == 1 and candidates[0] not in linked:
            user.estudiante_id = candidates[0]
            linked.add(candidates[0])

    db.session.commit()


def _find_user(username):
    return User.query.filter(User.username.collate("NOCASE") == username.strip()).all()


def create_user(username, password, role="estudiante", student_id=None):
    """Create an account and store only a Werkzeug password hash."""
    username = (username or "").strip()
    if role not in {"admin", "docente", "estudiante"}:
        raise ValueError("Rol no válido.")
    if len(password) < 12:
        raise ValueError("La contraseña debe tener al menos 12 caracteres.")
    if not username or len(username) > 80:
        raise ValueError("El usuario debe tener entre 1 y 80 caracteres.")
    if role == "estudiante" and student_id is None:
        raise ValueError("Asocia la cuenta estudiante con un student_id existente.")
    if role != "estudiante" and student_id is not None:
        raise ValueError("Solo las cuentas estudiante pueden asociarse a un perfil.")
    if _find_user(username):
        raise ValueError("Ya existe una cuenta con ese nombre de usuario.")
    if student_id is not None and db.session.get(Student, student_id) is None:
        raise ValueError("El perfil estudiante indicado no existe.")
    db.session.add(User(
        username=username,
        password=generate_password_hash(password),
        rol=role,
        estudiante_id=student_id,
    ))
    db.session.commit()


def set_user_password(username, password):
    """Set a password hash and invalidate sessions created with the old one."""
    if len(password) < 12:
        raise ValueError("La contraseña debe tener al menos 12 caracteres.")
    users = _find_user(username)
    if not users:
        raise ValueError("El usuario no existe.")
    if len(users) != 1:
        raise ValueError("Hay varias cuentas con ese nombre; resuelve los duplicados primero.")
    users[0].password = generate_password_hash(password)
    users[0].session_version += 1
    db.session.commit()


def link_student_account(username, student_id):
    """Associate a student login with exactly one existing academic profile."""
    users = [user for user in _find_user(username) if user.rol == "estudiante"]
    if not users:
        raise ValueError("No existe una cuenta estudiante con ese usuario.")
    if len(users) != 1:
        raise ValueError("Hay varias cuentas con ese nombre; resuelve los duplicados primero.")
    if db.session.get(Student, student_id) is None:
        raise ValueError("El perfil estudiante indicado no existe.")
    users[0].estudiante_id = student_id
    db.session.commit()
