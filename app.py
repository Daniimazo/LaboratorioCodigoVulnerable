"""Secure academic management demo application."""

import hashlib
import hmac
import math
import os
import secrets
import time
import uuid
from datetime import datetime
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from config import Config, ProductionConfig
from database import init_db
from extensions import db, login_manager
from models import Grade, LoginRateLimit, Student, UploadedFile, User


app = Flask(__name__)
app.config.from_object(Config)
if os.environ.get("APP_ENV", "development").lower() == "production":
    ProductionConfig.validate()
    app.config.from_object(ProductionConfig)
db.init_app(app)
login_manager.init_app(app)

ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
EDIT_ROLES = {"admin", "docente"}
DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_urlsafe(32))


@login_manager.user_loader
def load_user(user_id):
    """Load the account from the database and reject stale sessions."""
    try:
        user = db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None
    if user is None or session.get("session_version") != user.session_version:
        return None
    return user


@login_manager.unauthorized_handler
def unauthorized():
    return redirect(url_for("login", next=_request_target()))


def csrf_token():
    token = session.get("csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


app.jinja_env.globals["csrf_token"] = csrf_token


@app.context_processor
def inject_common_template_values():
    own_profile_id = (
        current_user.estudiante_id
        if current_user.is_authenticated and current_user.rol == "estudiante"
        else None
    )
    return {"now_year": datetime.now().year, "own_profile_id": own_profile_id}


@app.before_request
def protect_post_requests():
    if request.method == "POST":
        expected = session.get("csrf_token")
        submitted = request.form.get("csrf_token", "")
        if not expected or not secrets.compare_digest(expected, submitted):
            abort(400, description="Token CSRF ausente o inválido.")


def roles_required(*roles):
    """Require a logged-in account whose server-side role is allowed."""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.rol not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def can_edit_biography(student):
    if not current_user.is_authenticated:
        return False
    return current_user.rol == "admin" or (
        current_user.rol == "estudiante"
        and current_user.estudiante_id == student.id
    )


def _login_limit_keys(username):
    secret = app.secret_key.encode("utf-8")
    account_id = hmac.new(secret, username.casefold().encode("utf-8"), hashlib.sha256).hexdigest()
    address_id = hmac.new(
        secret, (request.remote_addr or "unknown").encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return (
        (f"account:{account_id}", app.config["LOGIN_ACCOUNT_FAILURES"]),
        (f"address:{address_id}", app.config["LOGIN_ADDRESS_FAILURES"]),
    )


def _login_is_limited(keys, now):
    cutoff = now - app.config["LOGIN_RATE_LIMIT_WINDOW_SECONDS"]
    LoginRateLimit.query.filter(
        LoginRateLimit.window_started < cutoff,
        LoginRateLimit.blocked_until < now,
    ).delete(synchronize_session=False)
    limited = any(
        (row := db.session.get(LoginRateLimit, key)) is not None
        and row.blocked_until > now
        for key, _limit in keys
    )
    db.session.commit()
    return limited


def _record_login_failure(keys, now):
    window = app.config["LOGIN_RATE_LIMIT_WINDOW_SECONDS"]
    # Serialize updates so concurrent failed logins cannot lose an increment.
    try:
        # End the read transaction opened by the account lookup before asking
        # SQLite for its write lock.
        db.session.rollback()
        db.session.execute(text("BEGIN IMMEDIATE"))
        for key, limit in keys:
            row = db.session.get(LoginRateLimit, key)
            if row is None or now - row.window_started >= window:
                if row is None:
                    row = LoginRateLimit(key=key, failures=1, window_started=now, blocked_until=0)
                    db.session.add(row)
                else:
                    row.failures, row.window_started, row.blocked_until = 1, now, 0
                continue
            row.failures += 1
            if row.failures >= limit:
                row.blocked_until = now + window
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("No se pudo actualizar el límite de intentos de inicio de sesión")
        raise


def _clear_account_login_failures(keys):
    row = db.session.get(LoginRateLimit, keys[0][0])
    if row is not None:
        db.session.delete(row)
        db.session.commit()


def _safe_next_path(destination):
    if not destination or "\\" in destination or any(ord(char) < 32 for char in destination):
        return None
    parsed = urlsplit(destination)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/") or parsed.path.startswith("//"):
        return None
    return destination


def _request_target():
    query = request.query_string.decode("latin-1")
    return f"{request.path}?{query}" if query else request.path


def _file_signature_matches(upload, extension):
    signatures = {
        "png": lambda data: data == b"\x89PNG\r\n\x1a\n",
        "jpg": lambda data: data.startswith(b"\xff\xd8\xff"),
        "jpeg": lambda data: data.startswith(b"\xff\xd8\xff"),
        "pdf": lambda data: data.startswith(b"%PDF-"),
    }
    try:
        position = upload.stream.tell()
        header = upload.stream.read(8)
        upload.stream.seek(position)
    except (AttributeError, OSError):
        return False
    return signatures[extension](header)


@app.route("/")
@login_required
def inicio():
    return render_template("features/home/index.html", usuario=current_user.username)


@app.route("/login", methods=["GET", "POST"])
def login():
    next_path = request.args.get("next", "")
    if request.method == "POST":
        next_path = request.form.get("next", "") or next_path
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        now = time.time()
        keys = _login_limit_keys(username[:256])
        limited = _login_is_limited(keys, now)
        user = None
        if not limited and len(username) <= 80 and len(password) <= 1024:
            user = User.query.filter(User.username.collate("NOCASE") == username).first()

        stored_hash = user.password if user else DUMMY_PASSWORD_HASH
        password_matches = (
            check_password_hash(stored_hash, password[:1024]) if not limited else False
        )
        if not limited and user and password_matches:
            session.clear()
            session.permanent = True
            session["session_version"] = user.session_version
            login_user(user, fresh=True)
            session["csrf_token"] = secrets.token_urlsafe(32)
            _clear_account_login_failures(keys)
            destination = _safe_next_path(next_path)
            return redirect(destination or url_for("inicio"))

        if not limited:
            _record_login_failure(keys, now)
        flash("Credenciales inválidas o demasiados intentos. Revisa los datos e intenta de nuevo.", "error")
    return render_template("features/auth/login.html", next_path=next_path)


@app.post("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("login"))


@app.route("/buscar")
@roles_required("admin", "docente")
def buscar():
    termino = request.args.get("q", "").strip()[:100]
    resultados = []
    if termino:
        patron = termino.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        resultados = Student.query.filter(
            Student.nombre.like(f"%{patron}%", escape="\\")
        ).order_by(Student.nombre).limit(100).all()
    return render_template("features/students/search.html", resultados=resultados, termino=termino)


@app.route("/perfil/<int:id>")
@login_required
def perfil(id):
    student = db.session.get(Student, id)
    if student is None:
        abort(404)
    if current_user.rol == "estudiante" and current_user.estudiante_id != student.id:
        abort(404)
    grades = Grade.query.filter_by(estudiante_id=id).order_by(Grade.id).all()
    return render_template(
        "features/students/profile.html",
        estudiante=student,
        notas=grades,
        puede_editar_biografia=can_edit_biography(student),
    )


@app.route("/perfil/<int:id>/editar", methods=["GET", "POST"])
@login_required
def editar_biografia(id):
    student = db.session.get(Student, id)
    if student is None:
        abort(404)
    if not can_edit_biography(student):
        abort(403)
    if request.method == "POST":
        bio = request.form.get("biografia", "")
        if len(bio) > 2000:
            flash("La biografía no puede superar 2000 caracteres.", "error")
            return render_template("features/students/edit_biography.html", estudiante=student), 400
        student.biografia = bio
        db.session.commit()
        flash("Biografía actualizada.", "success")
        return redirect(url_for("perfil", id=id))
    return render_template("features/students/edit_biography.html", estudiante=student)


@app.route("/nota/editar/<int:id>", methods=["GET", "POST"])
@roles_required(*EDIT_ROLES)
def editar_nota(id):
    grade = db.session.get(Grade, id)
    if grade is None:
        abort(404)
    if request.method == "POST":
        try:
            new_grade = float(request.form.get("nota", ""))
        except ValueError:
            new_grade = -1
        if not math.isfinite(new_grade) or not 0 <= new_grade <= 5:
            flash("La nota debe ser un número entre 0 y 5.", "error")
            return render_template("features/grades/edit.html", calificacion=grade), 400
        grade.nota = new_grade
        db.session.commit()
        flash("Nota actualizada.", "success")
        return redirect(url_for("perfil", id=grade.estudiante_id))
    return render_template("features/grades/edit.html", calificacion=grade)


@app.route("/subir", methods=["GET", "POST"])
@roles_required("admin", "docente")
def subir():
    if request.method == "POST":
        upload = request.files.get("archivo")
        if not upload or not upload.filename:
            flash("Selecciona un archivo.", "error")
            return redirect(url_for("subir"))
        safe_name = secure_filename(upload.filename)
        if not safe_name or "." not in safe_name:
            flash("Nombre de archivo no válido.", "error")
            return redirect(url_for("subir"))
        extension = safe_name.rsplit(".", 1)[1].lower()
        if extension not in ALLOWED_EXTENSIONS:
            flash("Tipo de archivo no permitido. Usa PDF, PNG o JPG.", "error")
            return redirect(url_for("subir"))
        if not _file_signature_matches(upload, extension):
            flash("El contenido no coincide con el formato indicado.", "error")
            return redirect(url_for("subir"))

        stored_name = f"{uuid.uuid4().hex}.{extension}"
        upload_dir = Path(app.config["UPLOAD_FOLDER"]).resolve()
        upload_dir.mkdir(parents=True, exist_ok=True)
        destination = upload_dir / stored_name
        upload.save(destination)
        try:
            db.session.add(UploadedFile(
                nombre_archivo=safe_name,
                ruta=str(destination),
                subido_por=current_user.id,
            ))
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            destination.unlink(missing_ok=True)
            app.logger.exception("No se pudo registrar el archivo cargado")
            abort(500)
        flash("Archivo cargado correctamente.", "success")
        return redirect(url_for("subir"))
    return render_template("features/uploads/upload.html")


@app.errorhandler(413)
def request_too_large(_error):
    limit_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    return f"El archivo supera el límite permitido ({limit_mb} MB).", 413


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="127.0.0.1", port=5000, debug=False)
