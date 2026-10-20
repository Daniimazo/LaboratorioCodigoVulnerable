# Gestion academica segura

Aplicacion educativa en Flask y SQLite que muestra controles de seguridad para una gestion academica basica. La version anterior del laboratorio contenia SQL injection, XSS almacenado, acceso directo inseguro a notas y carga de archivos sin restricciones. Esta version aplica controles para reducir esos riesgos.

## Seguridad, autenticacion y sesiones

- La aplicacion exige una sesion autenticada para acceder a sus rutas funcionales. Si no hay sesion, redirige al login y conserva la ruta local solicitada para volver a ella después de autenticarte. El login y los recursos estaticos son publicos.
- El login busca el usuario con una consulta parametrizada y verifica la contrasena con Werkzeug. Al autenticar, limpia la sesion anterior, guarda el identificador, el nombre y el rol, y genera un token CSRF nuevo.
- Las contrasenas se guardan como hashes Werkzeug, nunca como texto recuperable. `create_user` exige un minimo de 12 caracteres; `set_user_password` permite cambiarlas sin imprimirlas. `init_db` convierte contrasenas heredadas en texto plano a hashes al inicializar la base de datos.
- Los formularios POST, incluido login y logout, requieren token CSRF validado con comparacion constante. El cierre de sesion solo acepta POST.
- Las cookies de sesion son `HttpOnly` y `SameSite=Lax`; en produccion tambien requieren HTTPS (`Secure`). La sesion expira tras 30 minutos.
- Las plantillas Jinja conservan el autoescape; las biografias se muestran como texto y se limitan a 2000 caracteres.
- Las actualizaciones de calificaciones validan el rango de 0 a 5. SQLite activa claves foraneas y las conexiones usan transacciones con commit/rollback.
- La inicializacion crea las tablas y datos de ejemplo que falten sin borrar los registros existentes.

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

```powershell
python -c "from getpass import getpass; from database import set_user_password; set_user_password(input('Usuario: '), getpass('Nueva contrasena (minimo 12 caracteres): '))"
```

No reutilices contrasenas de ejemplo en produccion. Configura contrasenas unicas y compartelas con cada titular mediante un canal privado.

## Proteccion de archivos subidos

Solo `admin` y `docente` pueden subir archivos. Se aceptan extensiones PDF, PNG y JPG/JPEG; el nombre original se sanea y el archivo se guarda con un UUID para evitar traversal y sobrescrituras. El limite de peticion predeterminado es 5 MiB. La validacion comprueba la extension, no inspecciona el contenido real; para una aplicacion expuesta se recomienda analizar los archivos y almacenarlos fuera del servidor web.

## Frontend organizado por funcionalidades

Las vistas usan una estructura feature-based: cada carpeta agrupa las páginas y flujos de una funcionalidad, mientras el diseño común vive en layouts y componentes compartidos.

```text
templates/
  layouts/base.html              # navegación, cuenta, mensajes y pie
  components/flash_messages.html # avisos compartidos
  features/
    auth/login.html
    home/index.html
    students/search.html
    students/profile.html
    students/edit_biography.html
    grades/edit.html
    uploads/upload.html
static/style.css                 # estilos responsive y componentes visuales
```

El layout compartido adapta el menu y los accesos rapidos al rol. Las restricciones del servidor descritas arriba se aplican aunque se intente abrir una URL directamente. El diseño funciona en escritorio y movil y utiliza fuentes del sistema, sin depender de servicios externos.

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

   Las contrasenas nuevas deben tener al menos 12 caracteres. `create_user(username, password, role)` acepta los roles `admin`, `docente` y `estudiante`; cualquier otro rol se rechaza. Si ya existe el usuario, SQLite rechazara el nombre duplicado. Para asociar una cuenta estudiante con su perfil, utiliza el nombre completo del perfil como username. Ejemplo para crear la cuenta de Ana:

   ```powershell
   python -c "from getpass import getpass; from database import create_user; create_user('Ana Torres', getpass('Contrasena: '), 'estudiante')"
   ```

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

- Se parametrizaron las consultas de autenticacion, busqueda y acceso a perfiles para separar los datos del SQL.
- Se centralizo la autenticacion de las rutas y se agregaron verificaciones de rol y propiedad del perfil en el servidor.
- Se anadio proteccion CSRF a los formularios POST y el cierre de sesion se cambio a POST.
- Se conservaron el autoescape de Jinja y la validacion de biografias, notas y archivos.
- Se centralizo la configuracion, se desactivo debug y se hizo no destructiva la inicializacion de la base de datos.

## Limites conocidos

La lista de extensiones valida el nombre, no inspecciona el contenido real del archivo. Para una aplicacion expuesta se recomienda analizar los archivos con una herramienta antimalware, almacenar cargas fuera del servidor web, registrar eventos de seguridad y usar HTTPS. La conversion de hashes se hace al iniciar la aplicacion; realiza una copia de seguridad antes de desplegar esta version sobre una base de datos importante.
