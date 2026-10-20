# Gestión académica segura

Aplicación demostrativa construida con Flask, Flask-Login, Flask-SQLAlchemy y SQLite. Incluye autenticación, autorización por roles, perfiles académicos, calificaciones y carga controlada de archivos. La interfaz se organiza por funcionalidades en `templates/features/`.

> Proyecto educativo para ejecución local. Las credenciales de demostración son públicas: no las uses en producción.

## Requisitos e instalación

Se requiere Python 3.10 o superior.

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Inicializa o actualiza la base de datos, y crea/restablece las cuentas locales de demostración:

```powershell
python scripts/seed_demo_users.py
```

| Usuario | Contraseña | Rol |
| --- | --- | --- |
| `admin` | `AdminDemo-2026!` | Administrador |
| `profesor` | `DocenteDemo-2026!` | Docente |
| `demo_estudiante` | `EstudianteDemo-2026!` | Estudiante asociado al perfil demo |

Inicia el servidor:

```powershell
python app.py
```

Abre <http://127.0.0.1:5000>. Las páginas funcionales exigen autenticación y, si no hay una sesión válida, Flask-Login envía al formulario de acceso. Antes de ejecutar la inicialización sobre una base con datos importantes, guarda una copia de `academia.db`.

## Arquitectura y estructura

```text
app.py                         # rutas, validación y reglas de acceso
config.py                      # configuración por entorno y variables
extensions.py                  # instancias compartidas de SQLAlchemy y LoginManager
models.py                      # modelos ORM: User, Student, Grade y otros
database.py                    # inicialización, migración compatible y cuentas
scripts/seed_demo_users.py     # aprovisionamiento de cuentas locales
templates/
  layouts/base.html            # layout y navegación por rol
  components/                  # componentes compartidos
  features/                    # páginas agrupadas por módulo
static/style.css               # presentación responsive
academia.db                    # base SQLite local
uploads/                       # almacenamiento local de archivos
```

El navegador envía las solicitudes a las rutas Flask. Las rutas requieren sesión mediante `@login_required` o `@roles_required`; el usuario autenticado se obtiene con Flask-Login. Las consultas y modificaciones pasan por los modelos de `models.py` y la sesión de Flask-SQLAlchemy. La base SQLite conserva estudiantes, notas, cuentas, cargas y límites de intentos. Las plantillas usan `current_user` para adaptar la navegación; la autorización real se vuelve a comprobar en el servidor.

## Roles y permisos

| Acción | `admin` | `docente` | `estudiante` |
| --- | --- | --- | --- |
| Abrir inicio y consultar perfiles | Sí | Sí | Solo su propio perfil |
| Buscar estudiantes | Sí | Sí | No |
| Editar biografías | Cualquier perfil | No | Solo la propia |
| Modificar calificaciones | Sí | Sí | No |
| Cargar materiales | Sí | Sí | No |

El perfil del estudiante se identifica por `usuarios.estudiante_id`, no por coincidencia de nombres. Las cuentas de estudiante deben asociarse a un perfil y la relación es única. Un estudiante que intenta consultar otro perfil recibe una respuesta 404; las acciones no autorizadas por rol reciben 403.

## Cómo se implementaron los controles

### Flask-Login y autenticación

- Las rutas privadas usan `@login_required`; `@roles_required` combina la autenticación con la comprobación del rol permitido.
- Flask-Login administra la identidad autenticada en la sesión y `load_user` vuelve a cargar la cuenta desde la base en cada solicitud. El rol y la relación con el perfil provienen de la base, no de datos de rol enviados por el navegador.
- Si una sesión tiene una versión distinta a `usuarios.session_version`, el cargador de usuario no la acepta. El restablecimiento de contraseña incrementa esa versión e invalida sesiones antiguas.
- La redirección posterior al login solo acepta rutas locales seguras. Si se intentara entregar una URL externa como `next`, se redirige al inicio.
- Hay límites de intentos por identificador de cuenta y dirección IP: 5 fallos por cuenta o 20 por dirección dentro de 15 minutos. Los identificadores se almacenan como HMAC, no como usuario o IP en claro.

### SQLAlchemy ORM y consultas

- Las tablas académicas y de acceso se representan con clases ORM en `models.py`. El código de las rutas no concatena entradas en SQL ni usa consultas SQLite manuales.
- La búsqueda usa el ORM, limita la longitud de la entrada y el número de resultados, y escapa los comodines de `LIKE` para que se interpreten literalmente.
- `database.py` usa `db.create_all()` para crear tablas que falten y una migración compatible para columnas/índices de la versión previa. No borra las filas existentes; detecta nombres duplicados antes de crear el índice que exige unicidad sin distinguir mayúsculas.
- Contraseñas heredadas en texto plano se convierten a hashes durante la inicialización. Las nuevas contraseñas se guardan con `generate_password_hash` y se validan con `check_password_hash`.

### CSRF, XSS y carga de archivos

- Cada solicitud POST comprueba un token CSRF asociado a la sesión; el login también queda protegido. Cerrar sesión solo admite POST.
- Jinja mantiene el autoescape por defecto. Biografías y resultados se muestran como texto, nunca se marcan como HTML seguro.
- Las cargas se limitan a PDF, PNG y JPEG, se sanea el nombre visible, se verifica una firma inicial y el fichero se almacena con un UUID en lugar del nombre proporcionado. El máximo de solicitud predeterminado es 5 MiB. El directorio `uploads` no debe exponerse como contenido ejecutable.

### Cookies y secretos

- Las cookies de sesión llevan `HttpOnly` y `SameSite=Lax`; en producción, `Secure` obliga a usar HTTPS.
- La sesión es permanente por 30 minutos y no se renueva con cada solicitud.
- En desarrollo se genera una clave secreta temporal al iniciar. En producción se exige `SECRET_KEY` con al menos 32 caracteres. Para varios procesos, debe fijarse el mismo secreto por variable de entorno.

## `config.py` y variables de entorno

`Config` agrupa los valores comunes y deriva la URL SQLAlchemy del archivo indicado por `DATABASE_PATH`. `DevelopmentConfig` mantiene desactivado el modo debug. `ProductionConfig` exige un secreto configurado y activa la cookie segura. La aplicación selecciona producción cuando `APP_ENV=production`.

| Variable | Propósito | Valor predeterminado |
| --- | --- | --- |
| `APP_ENV` | Entorno (`development` o `production`) | `development` |
| `SECRET_KEY` | Firma de sesión y HMAC del límite de login | Secreto temporal local |
| `DATABASE_PATH` | Ruta al archivo SQLite | `academia.db` junto a la aplicación |
| `UPLOAD_FOLDER` | Directorio de cargas | `uploads/` junto a la aplicación |
| `MAX_CONTENT_LENGTH` | Límite de petición en bytes | 5 MiB |
| `SESSION_COOKIE_SECURE` | Marca cookies como solo HTTPS | Activado automáticamente en producción |
| `LOGIN_RATE_LIMIT_WINDOW_SECONDS` | Ventana de intentos fallidos | 900 segundos |
| `LOGIN_ACCOUNT_FAILURES` | Fallos antes de bloquear cuenta | 5 |
| `LOGIN_ADDRESS_FAILURES` | Fallos antes de bloquear dirección | 20 |

Ejemplo de configuración para PowerShell en despliegue con HTTPS:

```powershell
$env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
$env:APP_ENV = "production"
python app.py
```

En producción usa un servidor WSGI detrás de HTTPS, mantiene el secreto estable entre procesos, restringe el acceso a SQLite y a `uploads/`, y no ejecutes el script de cuentas demo.

## Inicialización y cuentas propias

La inicialización ocurre al ejecutar `scripts/seed_demo_users.py` o al iniciar `app.py`. Para crear cuentas desde código, importa `create_user` y ejecútalo dentro del contexto de la aplicación; los estudiantes necesitan el ID de un perfil existente. Para obtener perfiles existentes:

```powershell
python -c "from app import app; from models import Student; app.app_context().push(); print([(s.id, s.nombre) for s in Student.query.order_by(Student.id).all()])"
```

Las funciones `create_user`, `set_user_password` y `link_student_account` en `database.py` también deben invocarse dentro de `app.app_context()`. El cambio de contraseña invalida las sesiones previas.

## Alcance de la demostración

La inspección de una firma inicial y la extensión no equivalen a analizar el documento completo. Un servicio real debería guardar cargas fuera de la raíz pública, aplicar análisis antimalware y políticas de retención, usar migraciones versionadas y contar con monitoreo y respaldos. Las cuentas demo se conocen públicamente y existen solo para desarrollo local.
