"""Secure academic management demo application."""

import os
import secrets
import sqlite3
import uuid
from functools import wraps
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash
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


def csrf_token():
    token = session.get("csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def protect_post_requests():
    if request.method == "POST":
        expected = session.get("csrf_token")
        submitted = request.form.get("csrf_token", "")
        if not expected or not secrets.compare_digest(expected, submitted):
            abort(400, description="Token CSRF ausente o invalido.")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login", next=request.path))
            if session.get("rol") not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


@app.route("/")
def inicio():
    return render_template("index.html", usuario=session.get("username"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with connection() as conn:
            user = conn.execute(
                "SELECT id, username, password, rol FROM usuarios WHERE username = ?",
                (username,),
            ).fetchone()
        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["rol"] = user["rol"]
            session["csrf_token"] = secrets.token_urlsafe(32)
            destination = request.args.get("next", "")
            # Only allow local relative paths to prevent open redirects.
            if destination.startswith("/") and not destination.startswith("//"):
                return redirect(destination)
            return redirect(url_for("inicio"))
        flash("Credenciales invalidas.", "error")
    return render_template("login.html")


@app.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("inicio"))


@app.route("/buscar")
def buscar():
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
    return render_template("buscar.html", resultados=resultados, termino=termino)


@app.route("/perfil/<int:id>")
def perfil(id):
    with connection() as conn:
        estudiante = conn.execute("SELECT * FROM estudiantes WHERE id = ?", (id,)).fetchone()
        notas = conn.execute(
            "SELECT * FROM calificaciones WHERE estudiante_id = ? ORDER BY id", (id,)
        ).fetchall()
    if not estudiante:
        abort(404)
    return render_template("perfil.html", estudiante=estudiante, notas=notas)


@app.route("/perfil/<int:id>/editar", methods=["GET", "POST"])
@roles_required(*EDIT_ROLES)
def editar_biografia(id):
    with connection() as conn:
        estudiante = conn.execute("SELECT * FROM estudiantes WHERE id = ?", (id,)).fetchone()
        if not estudiante:
            abort(404)
        if request.method == "POST":
            bio = request.form.get("biografia", "")
            if len(bio) > 2000:
                flash("La biografia no puede superar 2000 caracteres.", "error")
                return render_template("editar_biografia.html", estudiante=estudiante), 400
            conn.execute("UPDATE estudiantes SET biografia = ? WHERE id = ?", (bio, id))
            flash("Biografia actualizada.", "success")
            return redirect(url_for("perfil", id=id))
    return render_template("editar_biografia.html", estudiante=estudiante)


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
                return render_template("editar_nota.html", calificacion=calificacion), 400
            conn.execute("UPDATE calificaciones SET nota = ? WHERE id = ?", (nueva_nota, id))
            flash("Nota actualizada.", "success")
            return redirect(url_for("perfil", id=calificacion["estudiante_id"]))
    return render_template("editar_nota.html", calificacion=calificacion)


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
    return render_template("subir.html")


@app.errorhandler(413)
def request_too_large(_error):
    return "El archivo supera el limite permitido (5 MB).", 413


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=False)
