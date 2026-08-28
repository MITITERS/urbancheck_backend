# UrbanCheck

Plataforma de gestión colaborativa de problemáticas urbanas

[![Built with Cookiecutter Django](https://img.shields.io/badge/built%20with-Cookiecutter%20Django-ff69b4.svg?logo=cookiecutter)](https://github.com/cookiecutter/cookiecutter-django/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

## Settings

Moved to [settings](https://cookiecutter-django.readthedocs.io/en/latest/1-getting-started/settings.html).

## Basic Commands

### Levantar el entorno local

```bash
docker compose -f docker-compose.local.yml up
```

| Servicio | URL local |
| --- | --- |
| Django | http://localhost:8000 |
| Mailpit (mails de prueba) | http://localhost:8025 |
| Flower (cola de Celery) | http://localhost:8555 |

Flower se publica en **8555** a propósito. En 5555 —su puerto de siempre, que
sigue siendo el de adentro del contenedor— rompe el desarrollo de la app móvil:
`adb` escanea los puertos 5555-5585 buscando emuladores de Android, encuentra a
flower escuchando y registra un `emulator-5554` fantasma que nunca responde.
`expo start` intenta hablarle y aborta con `could not connect to TCP port 5554`.

### Setting Up Your Users

- To create a **normal user account**, just go to Sign Up and fill out the form. Once you submit it, you'll see a "Verify Your E-mail Address" page. Go to your console to see a simulated email verification message. Copy the link into your browser. Now the user's email should be verified and ready to go.

- To create a **superuser account**, use this command:

      uv run python manage.py createsuperuser

For convenience, you can keep your normal user logged in on Chrome and your superuser logged in on Firefox (or similar), so that you can see how the site behaves for both kinds of users.

### Type checks

Running type checks with mypy:

    uv run mypy urbancheck

### Test coverage

To run the tests, check your test coverage, and generate an HTML coverage report:

    uv run coverage run -m pytest
    uv run coverage html
    uv run open htmlcov/index.html

#### Running tests with pytest

    uv run pytest

### Celery

This app comes with Celery.

To run a celery worker:

```bash
cd urbancheck
uv run celery -A config.celery_app worker -l info
```

Please note: For Celery's import magic to work, it is important _where_ the celery commands are run. If you are in the same folder with _manage.py_, you should be right.

To run [periodic tasks](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html), you'll need to start the celery beat scheduler service. You can start it as a standalone process:

```bash
cd urbancheck
uv run celery -A config.celery_app beat
```

or you can embed the beat service inside a worker with the `-B` option (not recommended for production use):

```bash
cd urbancheck
uv run celery -A config.celery_app worker -B -l info
```

### Email Server

In development, it is often nice to be able to see emails that are being sent from your application. For that reason local SMTP server [Mailpit](https://github.com/axllent/mailpit) with a web interface is available as docker container.

Container mailpit will start automatically when you will run all docker containers.
Please check [cookiecutter-django Docker documentation](https://cookiecutter-django.readthedocs.io/en/latest/2-local-development/developing-locally-docker.html) for more details how to start all containers.

With Mailpit running, to view messages that are sent by your application, open your browser and go to `http://127.0.0.1:8025`

## Jurisdicción: regla transversal del panel (US-034)

Cada usuario municipal opera **únicamente** sobre los datos de su propia
municipalidad. La restricción no se implementa vista por vista: vive en la capa
de acceso a datos, en dos piezas.

- `Report.objects.for_user(user)` (`urbancheck/reports/models.py`) filtra por la
  municipalidad del usuario. Un usuario sin municipalidad —un ciudadano, o el
  administrador de la plataforma, que no está acotado a ningún municipio— recibe
  un queryset vacío. Es un default seguro deliberado.
- `JurisdictionScopedMixin` (`urbancheck/reports/api/mixins.py`) aplica ese
  filtro sobre `super().get_queryset()`.

**Toda vista nueva del panel tiene que heredar de `JurisdictionScopedMixin`.**
Es lo único que evita el bug clásico de esta regla: una consulta escrita en
paralelo a la capa restringida que termina filtrando datos entre municipios.

Consecuencias buscadas:

- Pedir por `id` un recurso de otra jurisdicción devuelve **404, no 403**: el
  objeto no existe para ese usuario. Un `403` confirmaría que el reporte existe.
- El cliente **nunca** envía el identificador de municipio. La jurisdicción se
  deriva siempre del usuario autenticado; cualquier parámetro de municipio que
  llegue en la request se ignora.
- La municipalidad de un reporte y la de un usuario son inmodificables después
  del alta. Ningún serializer las expone como editables.

El municipio de un reporte nuevo lo resuelve `get_active_municipality()`
(`urbancheck/municipalities/services.py`), que es el único punto del código que
toma esa decisión: hoy devuelve la municipalidad configurada en
`DJANGO_ACTIVE_MUNICIPALITY_ID` o la única registrada. La resolución geográfica
por polígono de límites queda diferida a una iteración futura y solo cambia el
cuerpo de esa función.

El test de fuga vive en `urbancheck/reports/tests/test_jurisdiction.py`: dos
municipalidades pobladas y la verificación, endpoint por endpoint, de que un
agente no ve ni un registro de la otra.

### Validadores: los gestionan los dos roles del panel

`/api/validators/` lo usan el agente municipal (US-035) y el administrador de la
plataforma. Hacen lo mismo; lo único que cambia es el alcance y de dónde sale la
municipalidad:

- El **agente** pasa por la jurisdicción de US-034: ve, activa y desactiva solo
  validadores de su municipalidad, y las altas caen ahí sin que pueda elegir. Si
  manda `municipality_id` en el body, se ignora.
- El **admin** no está acotado a ningún municipio: ve todos, filtra con
  `?municipality=<id>`, y **elige** la municipalidad en cada alta, donde
  `municipality_id` es obligatorio. Sin jurisdicción propia no hay default
  posible, así que faltarla es un `400` y no un alta en el municipio equivocado.

El permiso pasó de `IsMunicipalAgent` a `IsPanelUser`. Un ciudadano o un
validador autenticado sigue recibiendo `403`.

### La baja lógica es de la cuenta de trabajo, no del validador

`User.is_work_account_active` es **una sola bandera para los dos roles de
trabajo**: la pregunta que responde —"¿esta cuenta sigue habilitada?"— es la
misma para un validador y para un agente municipal, y dos campos habrían
divergido. Se llamaba `is_validator_active` hasta que el agente también pudo
darse de baja; la migración `users/0007` la renombra sin perder las bajas ya
registradas.

Lo que cambia por rol es **quién puede darla de baja y qué se pierde**:

| | Lo gestiona | Al desactivarse pierde |
| --- | --- | --- |
| Validador (US-035) | Los dos roles del panel, cada uno en su jurisdicción | Validar en terreno |
| Agente municipal (US-017) | Solo el administrador de la plataforma | Operar el panel |

Cada rol tiene su verificación centralizada, y son espejo una de la otra:
`can_validate` y `can_operate_panel`. La segunda la consumen los tres permisos
de `users/api/permissions.py` a través de `_operates_panel()`, así que la baja
corta el acceso a **todo** el panel y no endpoint por endpoint.

Una diferencia deliberada entre las dos: `can_operate_panel` **no** mira
`must_change_password`. El agente recién dado de alta tiene que poder entrar
justamente para cambiar la contraseña temporal; ese redirect lo resuelve el
panel.

Los dos listados aceptan **`?municipality=<id>`** y **`?state=active|inactive`**.
El primero es para el admin, que no está acotado a ninguna jurisdicción y elige
mirar de a un municipio; un valor que no sea un id se ignora, en lugar de
reventar con un `500` como hacía el de validadores. El segundo es lo que sostiene
las dos pestañas del panel. El corte vive en el servidor y no en la pantalla: si
las cuentas archivadas viajaran igual, con veinte filas por página terminarían
ocupando el lugar de las que sí trabajan. Sin el parámetro se devuelven las dos
—es lo que hacía antes de existir—, y un valor desconocido no filtra ni rompe.

El filtro se aplica **solo en `list`**. `activate` y `deactivate` alcanzan a la
cuenta esté del lado que esté, o reactivar desde el archivado respondería `404`.
En validadores se aplica después de la jurisdicción, nunca en lugar de ella: el
archivado no es una puerta trasera al personal de otro municipio.

La baja no toca `is_active` de Django: la cuenta existe, puede iniciar sesión y
el panel le explica qué pasó. Todo lo que gestionó sigue en el historial de cada
reporte con su nombre, y por eso la tabla del panel muestra `management_count`
—los cambios de estado que hizo—, el equivalente de `validation_count` del
validador.

De dónde sale la municipalidad se resuelve eligiendo serializer por rol en
`get_serializer_class()`, no con ramas dentro de un serializer. La parte «el
admin elige el municipio» vive en `AdminCreatesPanelUserSerializer`, que
comparten el alta de agentes (US-017) y la de validadores: si cada una lo
resolviera por su cuenta, terminarían con validaciones distintas para el mismo
campo.

`ValidatorSerializer` devuelve `municipality` siempre, aunque para el agente sea
constante: es lo que el admin necesita para distinguir filas de municipios
distintos, y una sola forma de respuesta es más fácil de sostener que dos.

### `?author=` en el listado del panel

Existe para el perfil que el panel abre desde el nombre de un vecino. Como el
resto de los filtros del panel, se aplica **sobre** el queryset que ya devolvió
`JurisdictionScopedMixin`, nunca en lugar de él: un agente ve lo que esa persona
reportó en su municipio, y pedir su actividad en otro devuelve vacío. El test de
esa garantía vive en `test_panel_list.py::TestFilterByAuthor`.

### El reporte se numera por municipio

`Report.number` es el identificador **de cara al usuario**: «el reporte 12 de
Villa María». Cada municipio arranca en 1 y lleva su propia serie, así que el
mismo número existe en varios municipios a la vez. El `id` de la base sigue
siendo la clave técnica y es lo único que viaja en las URLs.

La asignación vive en `Report.save()` y no en la vista, para que la tengan todos
los caminos de alta —la API, el seed de demo, las factories de los tests—: uno
que se olvidara dejaría un reporte sin número y la pantalla con un hueco. Va
bajo `select_for_update()` sobre la fila del municipio, que se usa solo como
candado: sin él dos altas simultáneas leen el mismo máximo y la segunda choca
contra `unique_report_number_per_municipality`.

**Consecuencia asumida**: la serie sale del máximo entregado, así que borrar el
reporte más reciente hace que el próximo reciba ese número. Solo alcanza al
último, y solo su autor puede borrarlo mientras el municipio no lo tomó. Está
probado en `test_report_number.py`, para que el día que se decida cambiarlo el
test diga qué se está cambiando.

Se evaluó un contador persistente en `Municipality` —que no reutilizaría nunca—
y se descartó: cualquier `save()` sobre una instancia del municipio leída antes
del alta lo rebobina, y el número se repite en silencio hasta chocar contra la
restricción. Un identificador que se reasigna por una escritura no relacionada
es peor que uno que se reasigna al borrar el último.

El backfill (`reports.0006`) numera lo existente por antigüedad dentro de cada
municipio, desempatando por `id`: el mismo criterio que los nuevos, así el
histórico y lo que viene son una sola secuencia.

### El admin de la plataforma cruza jurisdicciones, y es el único

`JurisdictionScopedMixin` acota toda vista del panel a la municipalidad del
usuario. Tiene **una sola excepción**: el administrador de la plataforma, que la
opera entera y no tendría a qué municipio acotarse. Ve y gestiona los reportes
de todos los municipios, y puede acotarlos con `?municipality=<id>`.

Quién cruza lo decide `User.sees_every_municipality` y no una condición escrita
en cada vista: si la excepción se repartiera, cada vista podría ampliarla por su
cuenta. Hay un test que verifica que hoy es solo el admin.

Cuidado al tocar esa condición: el default de `for_user()` es no devolver nada,
así que un error en la capa de jurisdicción normalmente se ve como una lista
vacía —ruidoso, pero inofensivo—. Este camino es la excepción: invertido, filtra.

El filtro `municipality` del listado **no es un agujero**. Se aplica sobre el
queryset que ya devolvió el mixin, así que para el agente solo puede achicar: si
pide un municipio ajeno recibe una lista vacía, nunca la del otro. Está cubierto
en `test_jurisdiction.py`, por los dos lados.

Las transiciones de estado también quedan disponibles para el admin. Se
registran con `Actor.MUNICIPAL_AGENT` igual que las del agente: el actor nombra
la operación del panel, no quién la ejecutó — eso queda en `changed_by`.

**El panel web no usa todo esto igual que la API.** El admin no tiene ahí un
listado global de reportes: los mira por municipalidad, desde la ficha de cada
una (`/api/municipalities/{id}/reports/`). El listado transversal de
`/api/panel/reports/` y su filtro `?municipality=` siguen disponibles para quien
consuma la API, y el panel sí los usa para el **detalle** de un reporte, que es a
donde lleva la tabla de una municipalidad.

### El personal municipal está acotado, en toda la app

Las cuentas de **validador** y de **agente municipal** son cuentas de trabajo:
no ven nada de otros municipios, ni siquiera en el feed y el mapa ciudadanos.
Pedir por id un reporte de otra jurisdicción devuelve `404`, igual que en el
panel. Quien además quiera usar UrbanCheck como vecino se crea una cuenta
personal.

La regla vive en `User.sees_only_own_municipality` —los roles de
`MUNICIPALITY_BOUND_ROLES`— y se aplica en `ReportViewSet.get_queryset()`, así
que alcanza a todas las acciones del viewset —detalle, comentarios, likes— y no
solo al listado.

El administrador de la plataforma queda afuera a propósito: también es cuenta de
trabajo, pero no está acotado a ningún municipio, así que ve todo.

**Esto cambia lo que dicen dos historias del Sprint 3**, y conviene actualizar
sus documentos:

- US-035 describe al validador como alguien que «usa la aplicación móvil en las
  mismas condiciones que un ciudadano común». Ya no: su vista está acotada.
- El escenario 6 de US-036 —ver un reporte de otra municipalidad como ciudadano
  común, sin opción de validar— dejó de ser alcanzable navegando la app.

### Un comentario lo borra su autor, o el dueño del reporte

`CanDeleteComment` cubre los dos, porque son dos derechos distintos y los dos
son razonables: uno se arrepiente de lo que escribió, y quien publicó el reporte
modera lo que queda colgado de él. `CommentSerializer.can_delete` es su espejo,
para que el cliente muestre el botón sin replicar la regla —igual que `can_edit`
con la edición del reporte—.

El personal municipal queda afuera a propósito: no participa como vecino (ver la
sección siguiente), y darle la tijera sobre lo que dicen los vecinos en un
reclamo que va a resolver lo pone de los dos lados del mismo caso.

### Solo el vecino participa: reportar, comentar y dar me gusta

Las cuentas de trabajo operan el circuito en vez de usarlo: el validador
verifica en terreno lo que reportan los vecinos, el agente lo gestiona desde el
panel y el administrador opera la plataforma. Un aporte propio las pondría de
los dos lados del mismo caso, y sobre un reporte que además van a resolver, un
comentario del municipio no se distingue del de un vecino: el municipio responde
por el estado del reporte, no comentando.

**Leer no está alcanzado**, y es la mitad importante del contrato: el personal
municipal sigue viendo el feed, el mapa, el detalle y los comentarios de los
vecinos de su jurisdicción.

La regla vive en `User.participates_as_citizen` (`role not in User.WORK_ROLES`)
y se aplica con el permiso `ParticipatesAsCitizen` en
`ReportViewSet.get_permissions()`. Las tres acciones comparten una sola
verificación a propósito: son la misma pregunta, y separarlas era garantizar que
se fueran divergiendo. Es una regla **del rol, no del estado de la cuenta**: a
diferencia de `can_validate`, la baja lógica (`is_validator_active`) no la
habilita de vuelta, porque la cuenta sigue siendo de trabajo.

`like` y `comments` atienden más de un método bajo la misma acción, así que no
alcanza con mirar `self.action`; lo resuelve `_is_citizen_participation()`. Solo
se restringe el alta:

- `GET /comments/` es lectura.
- `DELETE /like/` deshace: bloquearlo dejaría trabado un me gusta anterior a
  esta regla, sin forma de sacarlo.

**Esto cambia un código de respuesta.** Antes, una cuenta de trabajo que
intentaba comentar un reporte de otra jurisdicción recibía `404` por la capa de
ocultación. Ahora el permiso corta antes de que la vista busque el reporte, así
que recibe `403`. No se filtra nada: la respuesta es idéntica exista o no el
reporte, y hay un test que lo verifica. El `404` de jurisdicción sigue valiendo
para todo lo que sí puede pedir.

`WORK_ROLES` se declara por extensión y no como «todo lo que no sea ciudadano»
a propósito: un rol nuevo obliga a decidir de qué lado cae, en vez de heredar un
default silencioso. Hay un test que verifica que hoy son complementarios.

Esto vuelve a corregir US-035 en el mismo sentido que la sección anterior: el
validador no usa la app «en las mismas condiciones que un ciudadano común», ni
mirando ni reportando. También deja sin efecto la consecuencia que estaba
anotada acá antes —qué pasaba con un reporte creado por el validador fuera de su
jurisdicción—: ya no puede crear ninguno.

El test vive en `urbancheck/reports/tests/test_citizen_participation.py`, e
incluye el contorno de la regla: que el vecino siga aportando y que al personal
municipal no se le haya sacado nada de lo que sí tiene que poder leer.

## Decisiones del Sprint 3

### Área de cobertura: qué reportes le llegan a cada municipio

Cada municipalidad declara un **centro geográfico y un radio en kilómetros**, y
un reporte nuevo se asocia al municipio que lo cubre. Es lo que evita que la
capital de Córdoba reciba los reportes de Villa María.

Esto **reemplaza la decisión original de US-034**, que asociaba todo reporte a
"la municipalidad activa del sistema" y difería la resolución geográfica. Sigue
siendo una aproximación circular: los polígonos de límites reales continúan
fuera de alcance.

Reglas, todas en `urbancheck/municipalities/services.py`, el único lugar que
decide la jurisdicción de un reporte:

- Con coordenadas manda la cobertura. Si varias áreas se superponen, gana la de
  centro más cercano.
- **Si ninguna cubre el punto, el reporte se rechaza** con `400` y un mensaje de
  fuera de cobertura, en lugar de asignarlo a cualquiera.
- Sin coordenadas —el vecino escribió una dirección y la geocodificación
  falló— no hay cobertura que evaluar y se cae al respaldo de
  `ACTIVE_MUNICIPALITY_ID`.
- Una municipalidad dada de baja deja de recibir reportes.

El campo de texto de la municipalidad es `city` + `province`; los nombres
`name`/`locality` de la primera versión se renombraron en la migración
`municipalities/0002`.

#### La cobertura también acota la lectura

El feed y el mapa del vecino usan la misma resolución: `GET /api/reports/` y
`GET /api/reports/map/` aceptan `latitude` y `longitude` y devuelven
**únicamente los reportes del municipio que cubre ese punto**. Leer y escribir
tienen que coincidir sobre qué municipio cubre un lugar, o el vecino reportaría
un bache que después no ve.

Son **dos condiciones**, y las dos hacen falta (`ReportQuerySet.covered_by()`):
el reporte pertenece a ese municipio **y** cae dentro de su radio. Pertenecer
solo no alcanza, porque hay reportes que apuntan a un municipio y están a
decenas de kilómetros: los cargados antes de que existiera la cobertura y los
que cayeron en el respaldo de `ACTIVE_MUNICIPALITY_ID` por no tener coordenadas
al crearse. Un reporte creado hoy cumple las dos por construcción —la creación
rechaza lo que queda fuera—, así que la segunda solo saca lo que nunca debió
estar ahí. Los reportes **sin coordenadas** se quedan: no hay dónde ubicarlos, y
su único vínculo con un municipio es el que ya tienen.

Esto acota **lo que ve el vecino**, no a quién le pertenece el reporte: el panel
municipal los sigue viendo por jurisdicción, que es la FK y nada más.

Las dos respuestas suman entonces una clave `coverage`:

```json
{"in_coverage": true, "municipality": {"id": 4, "city": "Villa María", ...}}
```

Existe para que el cliente distinga dos respuestas igual de vacías: que no haya
reportes todavía en su municipio (`in_coverage: true`) o que esté fuera del área
de todas (`false`, y `municipality` nula). Son dos pantallas distintas en la app.
La arma un solo lugar, `ReportViewSet._coverage_payload()`, para que el feed y
el mapa no expliquen lo mismo de dos formas.

Lo que **no** se acota: `?mine=true` —los reportes propios son del autor, no del
lugar donde abre la app— y el detalle de un reporte. Sin coordenadas no se acota
nada, así que un cliente viejo sigue viendo lo de siempre.

### Coordenadas: se redondean, no se rechazan

El GPS de un teléfono y los centroides de Georef vienen con trece decimales; los
campos del modelo guardan seis (~11 cm, de sobra para ubicar un bache). Un
`DecimalField` común rechaza esa entrada con «no puede haber más de 9 dígitos en
total» — un error incomprensible sobre un dato que el usuario no escribió, y que
rompía tanto el alta de municipalidades como **la creación de reportes desde la
app móvil**.

`urbancheck/common/fields.py` define `LatitudeField` y `LongitudeField`, que
redondean: más precisión de la que guardamos es un dato de sobra, no una entrada
inválida. Lo que sí se rechaza es una coordenada fuera del rango terrestre, que
es un error de verdad.

### La baja de una municipalidad arrastra a su personal

`deactivate_municipality()` (`municipalities/services.py`) es el único lugar que
da de baja un municipio, y hace las dos cosas en una transacción: lo desactiva y
desactiva sus agentes y validadores. Un municipio dado de baja no opera, así que
dejar habilitadas sus cuentas sería dejar gente trabajando sobre una
jurisdicción que la plataforma considera cerrada.

**No tiene inverso automático.** Volver a dar de alta el municipio recupera sus
reportes y sus usuarios, pero no rehabilita a nadie: quién vuelve a trabajar se
decide cuenta por cuenta, desde el archivado de cada pantalla. Reactivar en
bloque le devolvería el acceso a personal que quizás ya no está.

La cascada tiene un complemento sin el cual no serviría de nada:
`User.can_be_reactivated` —municipalidad asignada **y** activa—, que verifican
las dos acciones `activate`. Poder reactivar de a uno al personal de un
municipio dado de baja dejaría exactamente el estado que la cascada existe para
evitar. Responde `400` y no `403`: a quien la ejecuta no le falta permiso, falta
una condición del dato. Desactivar nunca queda trabado.

La respuesta del `DELETE` incluye `deactivated_users`, cuántas cuentas cayeron.
No es decorativo: la consecuencia ocurre en otras dos pantallas, y sin ese dato
el panel no podría decirla.

### Baja de municipalidades: lógica, y reversible

Eliminar una municipalidad la desactiva: deja de recibir reportes y de aparecer
en el listado, pero sus reportes y usuarios quedan intactos. Como la constraint
de unicidad `(city, province)` vale también para las inactivas, **volver a dar
de alta la misma ciudad la reactiva** con los datos nuevos en vez de fallar.

### "Zona" es un filtro de texto sobre la dirección (US-012)

El modelo de reporte no tiene campo de zona ni de barrio, y nadie definió esa
entidad. El filtro `zone` del panel resuelve como búsqueda de texto sobre
`address` en lugar de inventar una entidad Zona. **No hay filtrado por
polígonos.** Si en un sprint futuro aparece la definición, el cambio queda
acotado a `urbancheck/reports/api/panel_filters.py`.

### La máquina de estados se declara una sola vez (US-013)

`urbancheck/reports/state_machine.py` es la única fuente de verdad de qué
transiciones existen, quién puede ejecutarlas y cuáles exigen motivo. La
consultan tanto el panel municipal como la validación en terreno de la app
móvil.

`services.apply_transition()` es el único ejecutor: valida contra esa tabla,
bloquea la fila con `select_for_update`, escribe el historial en la misma
transacción y emite el evento. Una transición inválida es imposible incluso
llamando al modelo directamente desde el shell.

**Toda transición nueva se agrega a esa tabla, no a una vista.**

### Evento único de cambio de estado (US-013 → US-011)

`reports.signals.report_status_changed` se emite en cada transición, **fuera**
de la transacción. Las notificaciones lo consumen desde
`notifications/signals.py`: no están enganchadas endpoint por endpoint, así que
una transición nueva genera su aviso sola.

El push se envía después de persistir y sin propagar errores: un push caído no
puede revertir ni bloquear un cambio de estado.

### El push todavía no tiene proveedor (US-011)

`notifications/push.py` define el punto de envío y lo aísla, pero **no hay
integración de push en el proyecto**: US-033 implementó la bandeja in-app, no
Firebase, y el usuario no guarda token de dispositivo. Cuando se agregue el
proveedor se implementa ahí y nada más cambia.

### Preferencias: desactivan el push, no la bandeja (US-025)

Un tipo desactivado deja de enviarse como push, pero la notificación **igual
queda en la bandeja**. Es el comportamiento menos sorpresivo y el que menos
riesgo tiene de que el ciudadano se pierda información de su propio reclamo.

El filtrado se aplica en un único punto, `push.deliver_push()`, inmediatamente
antes del envío: ninguna llamada al servicio de notificaciones puede saltearlo
porque no hay otra ruta que llegue al envío.

El default es **todo activado**: la ausencia de fila en
`NotificationPreference` significa habilitado, así que un usuario que nunca tocó
la configuración recibe todo.

### Radio de validación (US-036)

`VALIDATION_RADIUS_METERS` (env `DJANGO_VALIDATION_RADIUS_METERS`, default 50)
es el único parámetro. La distancia se calcula **siempre en el servidor** con
Haversine (`urbancheck/reports/geo.py`): el proyecto no usa PostGIS y las
coordenadas son decimales. Nunca se confía en un cálculo hecho en el
dispositivo.

Ver también la limitación conocida sobre ubicación simulada, documentada en el
README del repositorio móvil.

### Datos de demostración

```bash
docker compose -f docker-compose.local.yml exec django /entrypoint \
    python manage.py seed_demo
```

Crea dos municipalidades, un usuario de cada rol y reportes en los seis estados.
Es idempotente. La segunda municipalidad existe para que una fuga de
jurisdicción se vea durante el desarrollo y no recién en los tests; con más de
una cargada, `DJANGO_ACTIVE_MUNICIPALITY_ID` deja de ser opcional.

## Deployment

The following details how to deploy this application.

### Docker

See detailed [cookiecutter-django Docker documentation](https://cookiecutter-django.readthedocs.io/en/latest/3-deployment/deployment-with-docker.html).

## Flujo de trabajo

El proyecto utiliza Git Flow:

- `main`: código estable.
- `develop`: integración de funcionalidades.
- `feature/US-<nro>-<descripcion>`: desarrollo de historias.
- `release/<version>`: preparación de entregas.
- `hotfix/<descripcion>`: correcciones urgentes.

Toda funcionalidad debe desarrollarse desde `develop` y mergearse mediante Pull Request.