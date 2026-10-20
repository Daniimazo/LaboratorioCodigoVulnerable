# Gestión académica segura

Aplicación demostrativa construida con Flask y SQLite. Permite iniciar sesión según un rol, consultar perfiles académicos, buscar estudiantes, administrar calificaciones y cargar archivos. Las vistas se organizan por funcionalidades en `templates/features/` y comparten componentes mediante un layout común.

> Es un proyecto educativo. Las credenciales demo son públicas y solo sirven para desarrollo local. No despliegues estas cuentas ni la configuración local en producción.

## Inicio rápido

<<<<<<< HEAD
Requisitos: Python 3.10 o superior y Flask 3.x.
=======
## Roles y permisos

La autorizacion se verifica en el servidor. Ocultar un enlace en la interfaz ayuda a mantener una navegacion coherente, pero no sustituye el control de acceso de las rutas.

| Accion | `admin` | `docente` | `estudiante` |
| --- | --- | --- | --- |
| Abrir el inicio | Si | Si | Si |
| Buscar en el directorio | Si | Si | No (HTTP 403) |
| Consultar perfiles | Todos | Todos | Solo su propio perfil |
| Editar biografias | Cualquier perfil | No | Solo la propia |
| Editar calificaciones | Si | Si | No |
| Subir archivos | Si | Si | No |

Para identificar el perfil propio, el sistema compara el nombre de usuario de la sesion con el nombre completo del perfil, sin distinguir mayusculas/minusculas. Por ejemplo, la cuenta `Ana Torres` corresponde al perfil `Ana Torres`. Un estudiante que intenta abrir el perfil de otra persona recibe una respuesta 404; si intenta editar una biografia no autorizada recibe 403. El admin puede editar cualquier biografia. El rol docente puede consultar perfiles, editar calificaciones y subir archivos, pero no editar biografias.

El menu de un estudiante muestra un enlace directo a **Mi perfil**, no el directorio. Si su cuenta no coincide con ningun perfil, la pagina de inicio le indica que contacte al administrador; no se le asigna automaticamente otro perfil.

## Busqueda de estudiantes

La busqueda esta disponible para `admin` y `docente`; los estudiantes no pueden acceder ni directamente a `/buscar`. El campo HTML admite hasta 100 caracteres; el servidor recorta espacios al principio y al final. Las consultas SQL usan parametros, escapan `\`, `%` y `_` para tratarlos como texto literal y devuelven como maximo 100 coincidencias ordenadas por nombre. Los perfiles y resultados se siguen protegiendo con autenticacion y autorizacion por rol.

## Cuentas de ejemplo

En la base de datos de desarrollo se registraron cuentas con el nombre completo como usuario para que la verificacion de propiedad funcione. Los usuarios y roles de referencia son:

| Usuario / perfil | Rol | Contraseña |
| --- | --- | --- |
| `admin` | `admin` | `admin123` |
| `profesor` | `docente` | `clave456` |
| `estudiante` | `estudiante` | `1234` |
| `Ana Torres` | `estudiante` | `Roble!Limon_73Nube#Azul` |
| `Luis Gomez` | `estudiante` | `Rio#Cedro_58Menta!Sol` |
| `Maria Ruiz` | `estudiante` | `Cobre!Nube_92Pino#Luz` |

La base de datos local puede contener cuentas distintas o adicionales. Las contrasenas no se documentan ni se guardan en el repositorio. Para crear una cuenta, usa `create_user`; para asignar o restablecer una contrasena, ejecuta el siguiente comando por cuenta. Se solicita sin mostrarla y se guarda unicamente su hash:
>>>>>>> efb1a750dad7f608af556d2bb789208ece0c40bf

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install Flask
```

Prepara la base de datos y las cuentas locales de demostración:

```powershell
python scripts/seed_demo_users.py
```

El comando inicializa/migra `academia.db`, agrega los perfiles académicos de demostración que falten y crea o restablece las siguientes cuentas. Las contraseñas se guardan como hashes Werkzeug.

| Usuario | Contraseña | Rol |
| --- | --- | --- |
| `admin` | `AdminDemo-2026!` | Administrador |
| `profesor` | `DocenteDemo-2026!` | Docente |
| `demo_estudiante` | `EstudianteDemo-2026!` | Estudiante, vinculado al perfil de demostración |

Luego inicia el servidor:

```powershell
python app.py
```

Abre <http://127.0.0.1:5000>. La aplicación muestra el login primero; sin una sesión válida no permite consultar estudiantes ni usar los módulos. La inicialización puede migrar una base existente: haz una copia de seguridad de `academia.db` antes de ejecutarla en una base con datos importantes. Si encuentra nombres de usuario duplicados ignorando mayúsculas, falla de forma explícita para que puedan resolverse sin eliminar cuentas.

## Módulos y roles

Los permisos se validan en el servidor en cada solicitud. Ocultar enlaces en la interfaz solo mejora la navegación y no reemplaza los controles de las rutas.

| Módulo/acción | `admin` | `docente` | `estudiante` |
| --- | --- | --- | --- |
| Inicio | Sí | Sí | Sí |
| Buscar estudiantes | Sí | Sí | No |
| Consultar perfiles | Todos | Todos | Solo el propio |
| Editar biografías | Cualquiera | No | Solo la propia |
| Editar calificaciones | Sí | Sí | No |
| Cargar archivos | Sí | Sí | No |

La identidad del perfil del estudiante se determina mediante `estudiante_id`, no por coincidencia de nombres. Los estudiantes no pueden entrar al directorio de búsqueda ni consultar o modificar el perfil de otra persona. El menú se adapta al rol, pero las rutas también aplican las mismas restricciones.

## Controles de seguridad implementados

### Autenticación y sesiones

- Las rutas funcionales requieren una sesión iniciada; solo login y recursos estáticos son públicos.
- La contraseña se verifica con Werkzeug y nunca se guarda en texto plano. Las contraseñas nuevas requieren al menos 12 caracteres.
- Tras autenticar, se renueva el estado de sesión y el token CSRF. El rol y el perfil se consultan en la base en cada petición protegida.
- Las cookies usan `HttpOnly` y `SameSite=Lax`; en producción se activa `Secure`. La sesión expira tras 30 minutos y un cambio de contraseña invalida las sesiones anteriores.
- El login aplica límites de intentos por cuenta y dirección IP: 5 fallos por cuenta o 20 por IP dentro de una ventana de 15 minutos. Los identificadores de limitación se guardan como HMAC.

### Autorización y RBAC

- Cada ruta sensible exige el rol permitido en el servidor.
- El perfil de estudiante se vincula a una cuenta mediante `estudiante_id` único. No se usa el nombre de usuario como comprobación de identidad.
- La búsqueda está disponible para administración y docencia. Cada estudiante solo accede a su propio perfil y sus propias acciones permitidas.

### Protección SQLi y XSS

- Las consultas usan parámetros SQL; los valores de búsqueda se tratan como texto y los comodines se escapan.
- Jinja conserva el autoescape. Las biografías se presentan como texto, se limitan a 2000 caracteres y no se interpretan como HTML.
- Las notas se validan entre 0 y 5. Las claves foráneas SQLite están activadas en las conexiones.

### CSRF, cargas y configuración

- Los formularios POST, incluidos login y logout, validan token CSRF. Logout solo acepta POST.
- Las cargas aceptan PDF, PNG y JPG/JPEG, sanea el nombre, generan un UUID y comprueban una firma inicial del archivo. El límite de petición predeterminado es 5 MiB.
- La configuración central vive en `config.py`; las variables de entorno permiten cambiar secreto, base de datos, carpeta de cargas y límites.
- `init_db` crea lo que falta sin borrar los registros existentes, agrega restricciones/migraciones necesarias y convierte contraseñas heredadas en hashes.

## Organización del frontend

```text
templates/
  layouts/base.html              # layout, navegación y estructura común
  components/flash_messages.html # mensajes compartidos
  features/
    auth/login.html
    home/index.html
    students/search.html
    students/profile.html
    students/edit_biography.html
    grades/edit.html
    uploads/upload.html
static/style.css                 # estilos responsive
```

Cada carpeta de `features` reúne las páginas de un módulo. `layouts` y `components` contienen elementos reutilizados. La navegación refleja los roles y la hoja de estilos soporta escritorio y móvil sin depender de fuentes externas.

## Crear y administrar cuentas

Para crear usuarios fuera de la configuración demo, inicializa primero la base y utiliza `create_user`. Los estudiantes requieren el ID de un perfil existente:

```powershell
python -c "from database import init_db; init_db()"
python -c "import sqlite3; c=sqlite3.connect('academia.db'); print(c.execute('SELECT id, nombre FROM estudiantes').fetchall()); c.close()"
```

```powershell
python -c "from getpass import getpass; from database import create_user; create_user('docente2', getpass('Contraseña (mínimo 12 caracteres): '), 'docente')"
python -c "from getpass import getpass; from database import create_user; create_user('alumno2', getpass('Contraseña (mínimo 12 caracteres): '), 'estudiante', student_id=1)"
```

Para cambiar una contraseña, se solicita sin mostrarla y se guarda como hash:

```powershell
python -c "from getpass import getpass; from database import set_user_password; set_user_password(input('Usuario: '), getpass('Nueva contraseña (mínimo 12 caracteres): '))"
```

## Configuración de producción

No ejecutes `scripts/seed_demo_users.py` en producción. Define un secreto aleatorio y selecciona el entorno antes de iniciar la aplicación:

```powershell
$env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
$env:APP_ENV = "production"
python app.py
```

La aplicación exige `SECRET_KEY` y activa cookies `Secure` en producción. Usa HTTPS detrás de un servidor WSGI; no expongas el servidor integrado de Flask. Restringe permisos del archivo SQLite y del directorio de cargas.

| Variable | Uso | Valor predeterminado |
| --- | --- | --- |
| `SECRET_KEY` | Firma de sesiones; obligatoria en producción | Secreto temporal generado al arrancar en desarrollo |
| `APP_ENV` | Selecciona el entorno | `development` |
| `DATABASE_PATH` | Archivo SQLite | `academia.db` junto a `config.py` |
| `UPLOAD_FOLDER` | Directorio de cargas | `uploads` junto a `config.py` |
| `MAX_CONTENT_LENGTH` | Tamaño máximo de petición, en bytes | 5 MiB |
| `SESSION_COOKIE_SECURE` | Exige HTTPS para la cookie | Desactivado en desarrollo; activado en producción |
| `LOGIN_RATE_LIMIT_WINDOW_SECONDS` | Ventana de limitación del login, en segundos | 900 |
| `LOGIN_ACCOUNT_FAILURES` | Fallos permitidos por cuenta | 5 |
| `LOGIN_ADDRESS_FAILURES` | Fallos permitidos por IP | 20 |

## Límites conocidos

La firma inicial y la extensión no prueban que un archivo sea seguro ni analizan su contenido completo. Para un servicio expuesto, añade análisis antimalware, almacenamiento fuera del servidor web, monitoreo de eventos y una política de respaldo. Las contraseñas demo son deliberadamente conocidas; el script solo rechaza `APP_ENV=production`, así que también debes proteger el acceso al entorno local.
