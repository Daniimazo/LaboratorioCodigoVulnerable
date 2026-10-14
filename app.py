"""
app.py  -  VERSION INTENCIONALMENTE VULNERABLE
==============================================
Sistema de Gestion Academica para el laboratorio de S-SDLC.

Este archivo contiene, A PROPOSITO, las 4 vulnerabilidades clasicas:
  1. Inyeccion SQL (SQLi)            -> /login y /buscar
  2. Cross-Site Scripting (XSS)      -> /perfil/<id>
  3. Control de acceso roto (IDOR)   -> /nota/editar/<id>
  4. Carga de archivos sin restriccion -> /subir

USAR SOLO EN UN ENTORNO LOCAL Y AISLADO CON FINES EDUCATIVOS.
"""

import os

from flask import (
    Flask,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from database import get_connection, init_db

app = Flask(__name__)
app.secret_key = "clave-insegura-de-laboratorio"  # MALA PRACTICA: clave debil y fija

UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


@app.route("/")
def inicio():
    """Pagina de inicio con el banner del laboratorio."""
    return render_template("index.html", usuario=session.get("username"))


# ======================================================================
# VULNERABILIDAD 1: INYECCION SQL (SQLi)
# ======================================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    """Inicio de sesion vulnerable a inyeccion SQL."""
    error = None
    if request.method == "POST":
        usuario = request.form.get("username", "")
        clave = request.form.get("password", "")

        conn = get_connection()
        cur = conn.cursor()

        # VULNERABLE: la consulta se construye concatenando la entrada del
        # usuario directamente. Un atacante puede escribir:  admin' --
        # o tambien:  ' OR '1'='1
        query = (
            "SELECT * FROM usuarios WHERE username = '"
            + usuario
            + "' AND password = '"
            + clave
            + "'"
        )
        print("SQL ejecutado:", query)  # para que el estudiante vea la inyeccion
        cur.execute(query)
        fila = cur.fetchone()
        conn.close()

        if fila:
            session["username"] = fila["username"]
            session["rol"] = fila["rol"]
            return redirect(url_for("inicio"))
        error = "Credenciales invalidas"

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("inicio"))


# ======================================================================
# VULNERABILIDAD 1 (variante): SQLi en el buscador de estudiantes
# ======================================================================
@app.route("/buscar")
def buscar():
    """Buscador de estudiantes vulnerable a inyeccion SQL."""
    termino = request.args.get("q", "")
    resultados = []
    query = ""
    if termino:
        conn = get_connection()
        cur = conn.cursor()
        # VULNERABLE: se concatena el termino de busqueda en la consulta.
        # Ejemplo de ataque con UNION para extraer usuarios y contrasenas:
        #   ' UNION SELECT id, username, password, rol FROM usuarios --
        query = (
            "SELECT id, nombre, carrera, biografia FROM estudiantes "
            "WHERE nombre LIKE '%" + termino + "%'"
        )
        print("SQL ejecutado:", query)
        cur.execute(query)
        resultados = cur.fetchall()
        conn.close()
    return render_template(
        "buscar.html", resultados=resultados, termino=termino, query=query
    )


# ======================================================================
# VULNERABILIDAD 2: CROSS-SITE SCRIPTING (XSS) ALMACENADO
# ======================================================================
@app.route("/perfil/<int:id>")
def perfil(id):
    """Muestra el perfil de un estudiante SIN escapar la biografia."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM estudiantes WHERE id = ?", (id,))
    estudiante = cur.fetchone()
    cur.execute("SELECT * FROM calificaciones WHERE estudiante_id = ?", (id,))
    notas = cur.fetchall()
    conn.close()
    if not estudiante:
        return "Estudiante no encontrado", 404
    # La plantilla perfil.html imprime la biografia con "| safe",
    # desactivando el autoescape de Jinja2 -> XSS almacenado.
    return render_template("perfil.html", estudiante=estudiante, notas=notas)


@app.route("/perfil/<int:id>/editar", methods=["GET", "POST"])
def editar_biografia(id):
    """Permite editar la biografia (fuente del XSS almacenado)."""
    conn = get_connection()
    cur = conn.cursor()
    if request.method == "POST":
        bio = request.form.get("biografia", "")
        # Se guarda la biografia tal cual, sin sanear el contenido.
        cur.execute(
            "UPDATE estudiantes SET biografia = ? WHERE id = ?", (bio, id)
        )
        conn.commit()
        conn.close()
        return redirect(url_for("perfil", id=id))
    cur.execute("SELECT * FROM estudiantes WHERE id = ?", (id,))
    estudiante = cur.fetchone()
    conn.close()
    return render_template("editar_biografia.html", estudiante=estudiante)


# ======================================================================
# VULNERABILIDAD 3: CONTROL DE ACCESO ROTO (IDOR)
# ======================================================================
@app.route("/nota/editar/<int:id>", methods=["GET", "POST"])
def editar_nota(id):
    """
    Edita una calificacion identificada por su ID en la URL.
    VULNERABLE: no verifica que el usuario haya iniciado sesion, ni su rol,
    ni si la calificacion le pertenece. Cualquiera puede cambiar
    /nota/editar/5 por /nota/editar/6 y modificar la nota de otro.
    """
    conn = get_connection()
    cur = conn.cursor()
    if request.method == "POST":
        nueva_nota = request.form.get("nota", "0")
        cur.execute(
            "UPDATE calificaciones SET nota = ? WHERE id = ?", (nueva_nota, id)
        )
        conn.commit()
        conn.close()
        return redirect(url_for("buscar"))
    cur.execute("SELECT * FROM calificaciones WHERE id = ?", (id,))
    calificacion = cur.fetchone()
    conn.close()
    if not calificacion:
        return "Calificacion no encontrada", 404
    return render_template("editar_nota.html", calificacion=calificacion)


# ======================================================================
# VULNERABILIDAD 4: CARGA DE ARCHIVOS SIN RESTRICCION
# ======================================================================
@app.route("/subir", methods=["GET", "POST"])
def subir():
    """Sube un archivo SIN validar extension ni tipo -> permite .py, .php, etc."""
    mensaje = None
    if request.method == "POST":
        archivo = request.files.get("archivo")
        if archivo and archivo.filename:
            # VULNERABLE: se acepta cualquier nombre/extension y se guarda
            # el archivo directamente. No hay lista blanca ni validacion.
            ruta = os.path.join(app.config["UPLOAD_FOLDER"], archivo.filename)
            archivo.save(ruta)

            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO archivos (nombre_archivo, ruta, subido_por) "
                "VALUES (?, ?, ?)",
                (archivo.filename, ruta, session.get("username")),
            )
            conn.commit()
            conn.close()
            mensaje = f"Archivo '{archivo.filename}' subido a {ruta}"
    return render_template("subir.html", mensaje=mensaje)


if __name__ == "__main__":
    if not os.path.exists("academia.db"):
        init_db()
    # debug=True tambien es una mala practica en produccion (expone la consola)
    app.run(host="127.0.0.1", port=5000, debug=True)
