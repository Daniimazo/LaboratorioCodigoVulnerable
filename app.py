"""Secure academic management demo application."""

import os
import hashlib
import hmac
import secrets
import sqlite3
import time
import uuid
from datetime import datetime
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from config import Config, ProductionConfig
from database import connection, init_db


app = Flask(__name__)
app.config.from_object(Config)
if os.environ.get("APP_ENV", "development").lower() == "production":
    ProductionConfig.validate()
    app.config.from_object(ProductionConfig)

ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
EDIT_ROLES = {"admin", "docente"}
DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_urlsafe(32))


def csrf_token():
    token = session.get("csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


app.jinja_env.globals["csrf_token"] = csrf_token


@app.context_processor
def inject_common_template_values():
    own_profile_id = None
    user = getattr(g, "user", None)
    if user and user["rol"] == "estudiante":
        own_profile_id = user["estudiante_id"]
    return {"now_year": datetime.now().year, "own_profile_id": own_profile_id}


@app.before_request
def protect_post_requests():
    if request.endpoint is not None and request.endpoint not in {"login", "static"}:
        user_id = session.get("user_id")
        if user_id is None:
            return redirect(url_for("login", next=_request_target()))
        with connection() as conn:
            user = conn.execute(
                "SELECT id, username, rol, estudiante_id, session_version "
                "FROM usuarios WHERE id = ?",
                (user_id,),
            ).fetchone()
        if not user or user["session_version"] != session.get("session_version"):
            session.clear()
            return redirect(url_for("login", next=_request_target()))
        g.user = user
        # Keep presentation data in sync with current database permissions.
        session["username"] = user["username"]
        session["rol"] = user["rol"]
    if request.method == "POST":
        expected = session.get("csrf_token")
        submitted = request.form.get("csrf_token", "")
        if not expected or not secrets.compare_digest(expected, submitted):
            abort(400, description="Token CSRF ausente o invalido.")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if getattr(g, "user", None) is None:
            return redirect(url_for("login", next=_request_target()))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = getattr(g, "user", None)
            if user is None:
                return redirect(url_for("login", next=_request_target()))
            if user["rol"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def can_edit_biography(estudiante):
    user = getattr(g, "user", None)
    return bool(
        user
        and (
            user["rol"] == "admin"
            or (
                user["rol"] == "estudiante"
                and user["estudiante_id"] == estudiante["id"]
            )
        )
    )


def _login_limit_keys(username):
    secret = app.secret_key.encode("utf-8")
    account_id = hmac.new(secret, username.casefold().encode("utf-8"), hashlib.sha256).hexdigest()
    address_id = hmac.new(
        secret, (request.remote_addr or "unknown").encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return ((f"account:{account_id}", app.config["LOGIN_ACCOUNT_FAILURES"]),
            (f"address:{address_id}", app.config["LOGIN_ADDRESS_FAILURES"]))


def _login_is_limited(keys, now):
    with connection() as conn:
        conn.execute(
            "DELETE FROM login_rate_limits WHERE window_started < ? AND blocked_until < ?",
            (now - app.config["LOGIN_RATE_LIMIT_WINDOW_SECONDS"], now),
        )
        return any(
            (row := conn.execute(
                "SELECT blocked_until FROM login_rate_limits WHERE key = ?", (key,)
            ).fetchone()) is not None and row["blocked_until"] > now
            for key, _limit in keys
        )


def _record_login_failure(keys, now):
    window = app.config["LOGIN_RATE_LIMIT_WINDOW_SECONDS"]
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        for key, limit in keys:
            row = conn.execute(
                "SELECT failures, window_started, blocked_until "
                "FROM login_rate_limits WHERE key = ?",
                (key,),
            ).fetchone()
            if row is None or now - row["window_started"] >= window:
                conn.execute(
                    "INSERT OR REPLACE INTO login_rate_limits "
                    "(key, failures, window_started, blocked_until) VALUES (?, 1, ?, 0)",
                    (key, now),
                )
                continue
            failures = row["failures"] + 1
            blocked_until = now + window if failures >= limit else row["blocked_until"]
            conn.execute(
                "UPDATE login_rate_limits SET failures = ?, blocked_until = ? WHERE key = ?",
                (failures, blocked_until, key),
            )


def _clear_account_login_failures(keys):
    with connection() as conn:
        conn.execute("DELETE FROM login_rate_limits WHERE key = ?", (keys[0][0],))


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
    return render_template("features/home/index.html", usuario=session.get("username"))


@app.route("/login", methods=["GET", "POST"])
def login():
    next_path = request.args.get("next", "")
    if request.method == "POST":
        next_path = request.form.get("next", "") or next_path
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        now = time.time()
        keys = _login_limit_keys(username)
        limited = _login_is_limited(keys, now)
        user = None
        if not limited and len(username) <= 80 and len(password) <= 1024:
            with connection() as conn:
                user = conn.execute(
                    "SELECT id, username, password, rol, estudiante_id, session_version "
                    "FROM usuarios WHERE username = ? COLLATE NOCASE",
                    (username,),
                ).fetchone()
        password_matches = False
        if not limited and len(password) <= 1024:
            password_matches = check_password_hash(
                user["password"] if user else DUMMY_PASSWORD_HASH,
                password,
            )
        if not limited and user and password_matches:
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["rol"] = user["rol"]
            session["session_version"] = user["session_version"]
            session["csrf_token"] = secrets.token_urlsafe(32)
            _clear_account_login_failures(keys)
            destination = _safe_next_path(next_path)
            if destination:
                return redirect(destination)
            return redirect(url_for("inicio"))
        if not limited:
            _record_login_failure(keys, now)
        flash("Credenciales invalidas o demasiados intentos. Revisa los datos e intenta de nuevo.", "error")
    return render_template("features/auth/login.html", next_path=next_path)


@app.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("inicio"))


@app.route("/buscar")
@login_required
def buscar():
    if g.user["rol"] == "estudiante":
        abort(403)
    termino = request.args.get("q", "").strip()
    resultados = []
    if termino:
        # Escape LIKE metacharacters so input is treated as literal text.
        patron = termino.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with connection() as conn:
            resultados = conn.execute(
                "SELECT id, nombre, carrera, biografia FROM estudiantes "
                "WHERE nombre LIKE ? ESCAPE '\\' ORDER BY nombre LIMIT 100",
                (f"%{patron}%",),
            ).fetchall()
    return render_template("features/students/search.html", resultados=resultados, termino=termino)


@app.route("/perfil/<int:id>")
@login_required
def perfil(id):
    with connection() as conn:
        estudiante = conn.execute("SELECT * FROM estudiantes WHERE id = ?", (id,)).fetchone()
        notas = conn.execute(
            "SELECT * FROM calificaciones WHERE estudiante_id = ? ORDER BY id", (id,)
        ).fetchall()
    if not estudiante:
        abort(404)
    if g.user["rol"] == "estudiante" and not can_edit_biography(estudiante):
        abort(404)
    return render_template(
        "features/students/profile.html",
        estudiante=estudiante,
        notas=notas,
        puede_editar_biografia=can_edit_biography(estudiante),
    )


@app.route("/perfil/<int:id>/editar", methods=["GET", "POST"])
@login_required
def editar_biografia(id):
    with connection() as conn:
        estudiante = conn.execute("SELECT * FROM estudiantes WHERE id = ?", (id,)).fetchone()
        if not estudiante:
            abort(404)
        if not can_edit_biography(estudiante):
            abort(403)
        if request.method == "POST":
            bio = request.form.get("biografia", "")
            if len(bio) > 2000:
                flash("La biografia no puede superar 2000 caracteres.", "error")
                return render_template("features/students/edit_biography.html", estudiante=estudiante), 400
            conn.execute("UPDATE estudiantes SET biografia = ? WHERE id = ?", (bio, id))
            flash("Biografia actualizada.", "success")
            return redirect(url_for("perfil", id=id))
    return render_template("features/students/edit_biography.html", estudiante=estudiante)


@app.route("/nota/editar/<int:id>", methods=["GET", "POST"])
@roles_required(*EDIT_ROLES)
def editar_nota(id):
    with connection() as conn:
        calificacion = conn.execute("SELECT * FROM calificaciones WHERE id = ?", (id,)).fetchone()
        if not calificacion:
            abort(404)
        if request.method == "POST":
            try:
                nueva_nota = float(request.form.get("nota", ""))
            except ValueError:
                nueva_nota = -1
            if not 0 <= nueva_nota <= 5:
                flash("La nota debe ser un numero entre 0 y 5.", "error")
                return render_template("features/grades/edit.html", calificacion=calificacion), 400
            conn.execute("UPDATE calificaciones SET nota = ? WHERE id = ?", (nueva_nota, id))
            flash("Nota actualizada.", "success")
            return redirect(url_for("perfil", id=calificacion["estudiante_id"]))
    return render_template("features/grades/edit.html", calificacion=calificacion)


@app.route("/subir", methods=["GET", "POST"])
@roles_required("admin", "docente")
def subir():
    if request.method == "POST":
        archivo = request.files.get("archivo")
        if not archivo or not archivo.filename:
            flash("Selecciona un archivo.", "error")
            return redirect(url_for("subir"))
        safe_name = secure_filename(archivo.filename)
        if not safe_name or "." not in safe_name:
            flash("Nombre de archivo no valido.", "error")
            return redirect(url_for("subir"))
        extension = safe_name.rsplit(".", 1)[1].lower()
        if extension not in ALLOWED_EXTENSIONS:
            flash("Tipo de archivo no permitido. Usa PDF, PNG o JPG.", "error")
            return redirect(url_for("subir"))
        if not _file_signature_matches(archivo, extension):
            flash("El contenido no coincide con el formato indicado.", "error")
            return redirect(url_for("subir"))
        stored_name = f"{uuid.uuid4().hex}.{extension}"
        upload_dir = Path(app.config["UPLOAD_FOLDER"]).resolve()
        upload_dir.mkdir(parents=True, exist_ok=True)
        destination = upload_dir / stored_name
        archivo.save(destination)
        try:
            with connection() as conn:
                conn.execute(
                    "INSERT INTO archivos (nombre_archivo, ruta, subido_por) VALUES (?, ?, ?)",
                    (safe_name, str(destination), session["user_id"]),
                )
        except sqlite3.Error:
            destination.unlink(missing_ok=True)
            app.logger.exception("No se pudo registrar el archivo cargado")
            abort(500)
        flash("Archivo cargado correctamente.", "success")
        return redirect(url_for("subir"))
    return render_template("features/uploads/upload.html")


@app.errorhandler(413)
def request_too_large(_error):
    return "El archivo supera el limite permitido (5 MB).", 413


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=False)
