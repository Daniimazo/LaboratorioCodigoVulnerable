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

## Despliegue con Docker y HTTPS

La configuración de despliegue usa esta arquitectura:

```text
Navegador --HTTPS--> Ngrok (certificado público) == túnel cifrado ==> Caddy (127.0.0.1:8080)
                                                                       `-- red privada --> Gunicorn/Flask (8000) -- /metrics --> Prometheus
                                                                            |-- volumen academia_data
                                                                            `-- volumen upload_data
```

Caddy funciona como proxy inverso local. En esta configuración, Ngrok termina HTTPS usando el certificado de su dominio y reenvía el tráfico por su túnel al puerto local 8080; Caddy lo pasa a Flask por la red privada. El contenedor `web` no publica el puerto 8000 en el host y Caddy solo está enlazado a `127.0.0.1`, no a todas las interfaces. La aplicación corre con Gunicorn, como usuario sin privilegios, con sistema de archivos de solo lectura excepto los volúmenes persistentes y `/tmp`.

### Preparar el dominio y los secretos

1. Copia la plantilla de variables y edítala. No subas `.env` al repositorio.

```powershell
Copy-Item .env.example .env
```

2. En `.env`, conserva el dominio Ngrok que proporcionaste o reemplázalo por el que te asignaron. Genera un secreto aleatorio:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Pega el resultado como valor de `SECRET_KEY`. No uses el valor de ejemplo en `.env.example` como secreto real. El token de Ngrok se configura en la herramienta Ngrok y no debe copiarse a este repositorio.

### Construir e iniciar

Desde la carpeta del proyecto, con Docker Desktop activo, inicia la aplicación y Caddy:

```powershell
docker compose up --build -d
docker compose logs -f caddy web
```

En una segunda terminal, configura el token de Ngrok una sola vez y abre el túnel hacia Caddy:

```powershell
ngrok config add-authtoken TU_TOKEN_DE_NGROK
ngrok http 8080 --url https://trench-operable-entire.ngrok-free.dev
```

El token se obtiene en el panel de Ngrok; no lo publiques ni lo pongas en archivos del proyecto. Cuando el túnel indique que está activo, abre <https://trench-operable-entire.ngrok-free.dev>. Ngrok proporciona HTTPS en el acceso público. La aplicación arranca en modo producción, por lo que `ProductionConfig` exige `SECRET_KEY` y activa `Secure` en la cookie de sesión.

La base de datos, los archivos cargados y las métricas históricas viven en volúmenes nombrados. Para detener los servicios sin borrar datos:

```powershell
docker compose down
```

No uses `docker compose down -v` salvo que quieras borrar deliberadamente esos datos. Para revisar registros utiliza `docker compose logs -f web caddy`.

### Crear la primera cuenta administrativa

El contenedor inicializa las tablas, pero no crea usuarios demo. No ejecutes `scripts/seed_demo_users.py` en producción: sus contraseñas son públicas y el script las restablece. Crea una cuenta administrativa introduciendo la contraseña de forma interactiva:

```powershell
docker compose exec web python -c "from app import app; from database import create_user; from getpass import getpass; ctx=app.app_context(); ctx.push(); create_user(input('Usuario administrador: '), getpass('Contraseña (mínimo 12 caracteres): '), 'admin')"
```

### Prometheus y métricas

`prometheus-flask-exporter` instrumenta las solicitudes Flask y publica métricas HTTP en `/metrics`. `monitoring/prometheus.yml` configura una consulta cada 15 segundos al destino `web:8000`, que Docker resuelve por nombre de servicio. Se agrupa por endpoint de Flask en vez de URL concreta para evitar crear una serie distinta por cada ID de perfil.

Prometheus guarda su historial en el volumen `prometheus_data`. Su interfaz queda enlazada a `127.0.0.1:9090`, por lo que se consulta desde esta máquina en <http://localhost:9090>; no se publica por Caddy ni por Ngrok. Caddy devuelve 404 para `/metrics` en la entrada pública, mientras que Prometheus accede directamente al servicio `web` dentro de la red Docker. En la página **Status → Targets**, el trabajo `gestion-academica` debe quedar `UP`. En **Graph**, se puede consultar `flask_http_request_total`.

Las métricas deben contener información agregada de operación, no nombres, biografías, contraseñas ni identificadores de estudiantes.

### Estrategia HTTPS y operación

- El navegador negocia TLS con Ngrok. El agente Ngrok mantiene el túnel cifrado hasta la máquina; en ella el tráfico se entrega a Caddy por `127.0.0.1:8080` y luego a Gunicorn por la red interna.
- El puerto de Flask no se publica y el puerto local de Caddy no escucha en la red externa, reduciendo el riesgo de saltarse el proxy.
- Se habilitan cookies `HttpOnly`, `SameSite=Lax` y `Secure`, además de cabeceras de protección en Caddy.
- Mantén `.env` y el token de Ngrok fuera de Git, restringe quién puede administrar Docker y respalda los volúmenes `academia_data`, `upload_data` y `prometheus_data`.
- Esta configuración conserva SQLite para una demostración de instancia única. Para varias réplicas o más concurrencia, cambia la base a PostgreSQL y usa migraciones versionadas.

El enlace Ngrok es adecuado para demostración y acceso temporal. La URL depende de que el agente Ngrok permanezca ejecutándose. Para un despliegue permanente, usa un dominio propio o contratado, DNS hacia el servidor y deja que Caddy gestione directamente certificados públicos en 80/443; esa arquitectura requiere cambiar el mapeo de puertos y el bloque del `Caddyfile`.

## 3. Gestión de riesgos

OWASP ZAP reportó tres alertas pasivas relacionadas con encabezados HTTP: ausencia de `X-Content-Type-Options` (riesgo bajo), ausencia de `Strict-Transport-Security` (riesgo bajo) y revisión de directivas `Cache-Control` (informativa). La aplicación establece `X-Content-Type-Options: nosniff` y una política de no almacenamiento en caché en las respuestas Flask. Caddy aplica esas directivas y HSTS en el acceso público HTTPS. Después de reconstruir el despliegue (`docker compose up --build -d`), repite el escaneo pasivo de ZAP y revisa las respuestas de `/`, `/robots.txt` y `/sitemap.xml`.

## Inicialización y cuentas propias

La inicialización ocurre al ejecutar `scripts/seed_demo_users.py` o al iniciar `app.py`. Para crear cuentas desde código, importa `create_user` y ejecútalo dentro del contexto de la aplicación; los estudiantes necesitan el ID de un perfil existente. Para obtener perfiles existentes:

```powershell
python -c "from app import app; from models import Student; app.app_context().push(); print([(s.id, s.nombre) for s in Student.query.order_by(Student.id).all()])"
```

Las funciones `create_user`, `set_user_password` y `link_student_account` en `database.py` también deben invocarse dentro de `app.app_context()`. El cambio de contraseña invalida las sesiones previas.

## Alcance de la demostración

La inspección de una firma inicial y la extensión no equivalen a analizar el documento completo. Un servicio real debería guardar cargas fuera de la raíz pública, aplicar análisis antimalware y políticas de retención, usar migraciones versionadas y contar con monitoreo y respaldos. Las cuentas demo se conocen públicamente y existen solo para desarrollo local.
