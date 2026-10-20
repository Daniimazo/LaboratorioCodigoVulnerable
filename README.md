# Gestion academica segura

Aplicacion educativa en Flask y SQLite que muestra controles de seguridad para una gestion academica basica. La version anterior del laboratorio contenia SQL injection, XSS almacenado, acceso directo inseguro a notas y carga de archivos sin restricciones. Esta version aplica controles para reducir esos riesgos.

## Controles definidos

1. **Autenticacion:** el login consulta el usuario mediante parametros SQL y verifica la contrasena con Werkzeug. La sesion se limpia antes de crear una sesion autenticada nueva y expira tras 30 minutos.
2. **RBAC (control de acceso por roles):** solo `admin` y `docente` pueden editar biografias, cambiar notas o subir archivos. Las comprobaciones se hacen en el servidor con decoradores; ocultar enlaces en la plantilla solo mejora la interfaz y no sustituye la autorizacion.
3. **Hashing de contrasenas:** las nuevas cuentas se crean con `create_user`, que usa `generate_password_hash`. Al iniciar, `init_db` convierte contrasenas antiguas en texto plano a hashes Werkzeug sin borrar la base de datos.
4. **Proteccion contra SQL injection:** todas las consultas que incluyen entrada usan placeholders y parametros. El buscador escapa `%` y `_` para que se interpreten como texto y limita los resultados.
5. **Proteccion contra XSS:** Jinja2 mantiene el autoescape; se retiro el filtro `safe`. Las biografias se muestran como texto y tienen limite de longitud.

## Controles complementarios

- Token CSRF en todos los formularios POST, incluido el cierre de sesion.
- Cookies de sesion `HttpOnly` y `SameSite=Lax`; `Secure` en modo produccion.
- Carga restringida a PDF, PNG y JPG, nombre saneado, nombre de almacenamiento aleatorio, limite de 5 MB y autorizacion de rol.
- Notas validadas entre 0 y 5, claves foraneas habilitadas y conexiones SQLite gestionadas con contextos.
- `config.py` concentra rutas, secreto, limite de carga y opciones de cookies. En produccion se exige `SECRET_KEY`.
- La base de datos se inicializa de forma no destructiva. Ya no se elimina `academia.db` al preparar el esquema.

## Requisitos

- Python 3.10 o superior.
- Flask 3.x y Werkzeug (Werkzeug se instala como dependencia de Flask).

Instala Flask en el entorno virtual del proyecto:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install Flask
```

## Preparacion y ejecucion local

1. Inicializa el esquema y los datos academicos de ejemplo. Este paso no elimina tablas ni registros existentes:

   ```powershell
   python -c "from database import init_db; init_db()"
   ```

2. Crea el primer usuario administrador. Cambia la contrasena por una propia; el valor se guarda como hash:

   ```powershell
   python -c "from getpass import getpass; from database import create_user; create_user('admin', getpass('Contrasena (minimo 12 caracteres): '), 'admin')"
   ```

   Las contrasenas nuevas deben tener al menos 12 caracteres. Tambien puedes crear roles `docente` o `estudiante` cambiando el tercer argumento. Si ya existe el usuario, SQLite rechazara el nombre duplicado.

3. Inicia el servidor local:

   ```powershell
   python app.py
   ```

4. Abre <http://127.0.0.1:5000>. El modo debug esta desactivado.

La base de datos predeterminada es `academia.db` en la carpeta del proyecto. Se puede cambiar con `DATABASE_PATH`. Los archivos cargados se guardan en `uploads` o en la ruta indicada por `UPLOAD_FOLDER`.

## Configuracion para produccion

Configura un secreto impredecible y activa el modo de produccion antes de iniciar la aplicacion:

```powershell
$env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
$env:APP_ENV = "production"
python app.py
```

En produccion `SESSION_COOKIE_SECURE` se activa y Flask exige `SECRET_KEY`. Sirve la aplicacion detras de un servidor WSGI y HTTPS; no uses el servidor integrado de Flask como servidor publico. Guarda el secreto fuera del repositorio y limita los permisos del directorio de base de datos y cargas.

Variables admitidas:

| Variable | Uso | Valor predeterminado |
| --- | --- | --- |
| `SECRET_KEY` | Firma de sesiones; obligatoria en produccion | Secreto temporal generado al arrancar |
| `DATABASE_PATH` | Archivo SQLite | `academia.db` junto a `config.py` |
| `UPLOAD_FOLDER` | Directorio de cargas | `uploads` junto a `config.py` |
| `MAX_CONTENT_LENGTH` | Maximo de peticion, en bytes | 5 MiB |
| `SESSION_COOKIE_SECURE` | Exigir HTTPS para cookies | Desactivado en desarrollo |

## Como se aplicaron los cambios

- Se parametrizaron las consultas de login y busqueda, eliminando la construccion SQL con texto del usuario.
- Se verifican credenciales con hashes y se agregaron decoradores de autenticacion y roles en los endpoints de escritura.
- Se agrego un token CSRF a cada formulario que cambia estado y el logout paso a POST.
- Se retiro `|safe`, se limitaron los campos de texto y se conserva el escape automatico de Jinja.
- Se valida la extension de cargas, se normaliza el nombre original y se guarda el archivo con un UUID para evitar traversal y sobrescritura por nombre.
- Se centralizo la configuracion, se desactivo debug y se cambio la inicializacion para preservar los datos existentes y migrar contrasenas en texto plano.

## Limites conocidos

La lista de extensiones valida el nombre, no inspecciona el contenido real del archivo. Para una aplicacion expuesta se recomienda analizar los archivos con una herramienta antimalware, almacenar cargas fuera del servidor web, registrar eventos de seguridad y usar HTTPS. La conversion de hashes se hace al iniciar la aplicacion; realiza una copia de seguridad antes de desplegar esta version sobre una base de datos importante.
