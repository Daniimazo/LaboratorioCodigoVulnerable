"""ORM models for academic records and authentication."""

from flask_login import UserMixin
from sqlalchemy import CheckConstraint

from extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True)
    password = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), nullable=False)
    estudiante_id = db.Column(db.Integer, db.ForeignKey("estudiantes.id"), unique=True)
    session_version = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (CheckConstraint("rol IN ('admin', 'docente', 'estudiante')", name="ck_usuarios_rol"),)


class Student(db.Model):
    __tablename__ = "estudiantes"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(160), nullable=False)
    carrera = db.Column(db.String(160), nullable=False)
    biografia = db.Column(db.Text)


class Grade(db.Model):
    __tablename__ = "calificaciones"

    id = db.Column(db.Integer, primary_key=True)
    estudiante_id = db.Column(db.Integer, db.ForeignKey("estudiantes.id"), nullable=False)
    materia = db.Column(db.String(160), nullable=False)
    nota = db.Column(db.Float, nullable=False)

    __table_args__ = (CheckConstraint("nota >= 0 AND nota <= 5", name="ck_calificaciones_nota"),)


class UploadedFile(db.Model):
    __tablename__ = "archivos"

    id = db.Column(db.Integer, primary_key=True)
    nombre_archivo = db.Column(db.String(255), nullable=False)
    ruta = db.Column(db.String(1024), nullable=False)
    subido_por = db.Column(db.Integer, db.ForeignKey("usuarios.id"))


class LoginRateLimit(db.Model):
    __tablename__ = "login_rate_limits"

    key = db.Column(db.String(128), primary_key=True)
    failures = db.Column(db.Integer, nullable=False)
    window_started = db.Column(db.Float, nullable=False)
    blocked_until = db.Column(db.Float, nullable=False, default=0)
