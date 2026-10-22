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

Cada municipalidad declara el **polígono de su límite** —una lista de pares
`[latitud, longitud]` en `Municipality.boundary`— y un reporte nuevo se asocia
al municipio que lo contiene. Es lo que evita que la capital de Córdoba reciba
los reportes de Villa María.

Esto **reemplaza la decisión original de US-034**, que asociaba todo reporte a
"la municipalidad activa del sistema" y difería la resolución geográfica.

También reemplaza al círculo —centro y radio— con el que se resolvió primero.
El círculo no sobrevivió al caso de Villa María y Villa Nueva: están pegadas y
las separa el río Ctalamochita, así que cualquier radio lo bastante grande para
cubrir una entera se comía parte de la otra. Un círculo no puede representar un
límite; un polígono sí. La migración `municipalities/0003` convierte cada
círculo existente en el polígono de 32 lados que lo aproxima, para que ningún
municipio se quede sin cobertura al aplicarla.

**Sin PostGIS.** La pertenencia se calcula en Python con lanzamiento de rayo
(`reports/geo.py::point_in_polygon`). A la escala de este sistema —decenas de
municipios por reporte creado— el costo es despreciable, y adoptar GeoDjango
por esto habría sido un cambio de infraestructura mucho mayor que el problema.

Reglas, todas en `urbancheck/municipalities/services.py`, el único lugar que
decide la jurisdicción de un reporte:

- Con coordenadas manda la cobertura. Con límites bien trazados no puede haber
  más de un municipio conteniendo un punto; si los hay, alguien trazó mal un
  polígono y se desempata por centro más cercano para que el resultado sea
  determinista.
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
el reporte pertenece a ese municipio **y** cae dentro de su área. Pertenecer
solo no alcanza, porque hay reportes que apuntan a un municipio y están a
decenas de kilómetros: los cargados antes de que existiera la cobertura y los
que cayeron en el respaldo de `ACTIVE_MUNICIPALITY_ID` por no tener coordenadas
al crearse. Un reporte creado hoy cumple las dos por construcción —la creación
rechaza lo que queda fuera—, así que la segunda solo saca lo que nunca debió
estar ahí. Los reportes **sin coordenadas** se quedan: no hay dónde ubicarlos, y
su único vínculo con un municipio es el que ya tienen.

Ese filtro usa el **recuadro** del polígono y no el polígono exacto: sin PostGIS
no hay forma de expresar punto-en-polígono en SQL, y traerlo a Python rompería
la pereza del queryset, que después se pagina. Alcanza de sobra para lo que
hace —descartar reportes a decenas de kilómetros—, y el único caso que se cuela
es un dato viejo dentro del recuadro pero fuera del límite.

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

`Notification.kind` y `NotificationPreference.kind` miden 50 (C-12): con 30,
`apelacion_moderacion_rechazada` ya ocupaba todo el campo.

`nuevo_like` estaba en el catálogo pero nada lo creaba (C-09). Ahora lo crea
`notify_new_like` al dar me gusta: al autor, nunca por el propio, y uno solo
por persona y reporte aunque se quite y se vuelva a dar. Sigue la misma regla
de preferencias que los demás.

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

Crea dos municipalidades, un área operativa por municipio, un usuario de cada
rol y reportes en los seis estados. Es idempotente. La segunda municipalidad
existe para que una fuga de jurisdicción se vea durante el desarrollo y no
recién en los tests; con más de una cargada,
`DJANGO_ACTIVE_MUNICIPALITY_ID` deja de ser opcional.

El área existe por el invariante de US-028: desde ese sprint un reporte *En
proceso* sin área responsable no puede existir, así que el seed tampoco puede
fabricar uno.

## Decisiones del Sprint 4

### Asignar el área **es** procesar el reporte (US-028)

`/reports/{id}/process/` pasó a exigir `area_id`. No es un camino nuevo hacia
*En proceso*: es el mismo de US-013, con el área como parámetro obligatorio.

La exigencia vive en la tabla de transiciones —`Transition.requires_area`— y no
en la vista, y eso es lo que la vuelve una garantía: `apply_transition()` la
verifica antes de tocar nada, así que ningún camino —ni el panel, ni el shell,
ni un endpoint futuro— puede dejar un reporte en gestión sin responsable
operativo. El test `test_no_declared_transition_reaches_in_progress_without_an_area`
lo comprueba recorriendo la tabla, no un endpoint.

El cambio de estado y la asignación se escriben en la misma transacción, de
modo que el estado intermedio ni siquiera existe un instante.

**La reasignación va por otro lado.** `/reports/{id}/assign-area/` cambia el
área de un reporte que ya está *En proceso* y **no** dispara ninguna
transición: el reporte no se mueve de estado. Por eso tampoco puede usarse para
desasignar —el área es obligatoria— ni para hacer entrar un reporte en gestión.

`ReportStatusHistory` no servía para registrar una reasignación, justamente
porque el estado no cambia. Se agregó `ReportAreaAssignment` —reporte, área
anterior, área nueva, responsable y fecha— y es lo que alimenta el bloque de
asignaciones del detalle del panel.

### El área operativa se desactiva, no se borra (US-039)

`OperationalArea` tiene unicidad **compuesta** sobre `(Lower(name),
municipality)`: "Obras Públicas" existe en todos los municipios del país y dos
municipalidades distintas tienen que poder registrarla, pero cargarla dos veces
en la misma es duplicar la dependencia.

No hay endpoint de borrado físico. `DELETE` existe solo para explicar por qué
responde `405`: borrar un área con reportes asignados perdería la constancia de
qué dependencia se hizo cargo de cada reclamo. Lo mismo en el admin de Django,
que declara `has_delete_permission = False` — dejarlo abierto ahí sería abrir
por atrás lo que la API cierra.

El desplegable de asignación consume `?state=active`; el listado de gestión
muestra las dos.

### El operario es un rol nuevo con acceso mínimo (US-044 y US-045)

`User.Role.OPERARIO` se suma a los roles existentes: no hay un modelo de usuario
separado. La municipalidad **se deriva del área** y nunca se acepta del cliente,
y `User.clean()` sostiene las tres reglas —un operario tiene área, ningún otro
rol la tiene, y el área es de su propia municipalidad— para que ningún alta por
shell o por admin pueda saltearlas.

El circuito de invitación es el de US-035 sin cambios: contraseña temporal
definida por quien da el alta y `must_change_password` hasta el primer ingreso.

`User.can_work_as_operator` es la única verificación de acceso a la bandeja, y
es espejo de `can_operate_panel` con una condición más: el área tiene que seguir
activa. La contraseña temporal **no** entra ahí, por lo mismo que en el panel:
el operario tiene que poder entrar justamente para cambiarla.

**El alcance del rol se cierra también en el backend.** `ExcludesOperator`
responde `403` en toda la superficie ciudadana —feed, mapa, detalle,
comentarios, me gusta—: esconderlo solo en la navegación de la app dejaría los
endpoints abiertos. La bandeja vive en `/api/operator/reports/` y resuelve el
área desde el usuario autenticado; el área y la municipalidad nunca viajan como
parámetro.

Esa vista **no** hereda de `JurisdictionScopedMixin`: el recorte por área es más
estrecho que el recorte por municipalidad y ya lo implica, así que aplicar los
dos sería escribir la misma restricción dos veces.

### El panel llega al operario por su nombre, como al vecino (US-046)

`?closed_by=` en el listado del panel devuelve lo que ese operario cerró, y es
la tercera pieza de una familia: `author` para el vecino, `validated_by` para el
validador, `closed_by` para el operario. Los tres se aplican sobre el queryset
que **ya** acotó `JurisdictionScopedMixin`, así que ningún perfil puede ser una
puerta lateral a los reportes de otro municipio: preguntar por un operario de
otra jurisdicción devuelve lista vacía, no su trabajo.

Se filtra por la **evidencia** y no por el historial de estados. Quién cerró es
un dato propio del parte de trabajo, y deducirlo de la forma de la transición es
exactamente el error que US-040 destapó en la validación colectiva.

Dos diferencias con `validated_by`, las dos deliberadas:

- Va por **subconsulta** y no por `filter()` sobre la relación inversa: un
  reporte reabierto por apelación y vuelto a cerrar tiene dos evidencias del
  mismo operario, y el `JOIN` devolvería la fila duplicada haciendo mentir al
  contador del paginado.
- Anota el cierre **más reciente**, mientras que `validated_by` toma la decisión
  más vieja. La del validador es la primera porque un reporte reactivado vuelve
  a pasar por _Reportado_; de un cierre interesa el último, que es el vigente.

El campo `closure` de la fila viaja solo cuando se pidió el filtro, con el mismo
criterio que `validation`: sin operario por el que preguntar no hay cierre del
que hablar, y va nulo.

### El historial del operario se recorta por autoría, no por área (US-046)

`/api/operator/reports/history/` devuelve los trabajos que **esta persona**
cerró: es el equivalente de «Mis reportes» del vecino para una cuenta de
trabajo. Va como acción propia y no como un filtro del listado para que la
bandeja pueda seguir siendo exactamente el trabajo pendiente, sin un parámetro
del cliente que la convierta en otra cosa.

Es la **única** acción de esa vista que no se acota por el área actual, y es
deliberado: `ResolutionEvidence.operational_area` guarda el área del momento del
cierre justamente para que un traslado posterior no reescriba quién se hizo
cargo (US-044, escenario 5), así que filtrar por el área de hoy le borraría del
historial el trabajo que sí hizo. El recorte por autoría del cierre es más
estrecho que el del área, no más ancho.

El detalle acepta además lo que el operario cerró alguna vez, para que toda fila
del historial se pueda abrir; **el cierre no**, que sigue acotado al área actual:
haber cerrado un reporte una vez no habilita a volver a operarlo desde otra área.

La pertenencia se resuelve con una **subconsulta** y no con un `filter()` sobre
la relación inversa: un reporte reabierto por apelación y vuelto a cerrar tiene
dos evidencias del mismo operario, y el `JOIN` lo devolvería duplicado con el
contador del paginado mintiendo. El estado que se serializa es el **actual**: un
cierre objetado volvió a *En proceso* (US-048) y tiene que verse así también en
el historial de quien lo cerró.

### La respuesta oficial es un hilo inmutable (US-024)

`OfficialResponse` es una relación 1-N con el reporte, en orden cronológico
ascendente. **No hay endpoints de actualización ni de borrado**, y esa ausencia
es la garantía: una validación que impida editar es algo que después alguien
puede relajar. Una corrección se publica como una respuesta nueva.

Qué estados la habilitan lo declara `OFFICIAL_RESPONSE_STATUSES`, junto a la
tabla de transiciones y no dentro de la vista: es una regla sobre el estado del
reporte, y las reglas sobre el estado viven en un solo archivo.

Hay **dos serializers** y no un campo condicional. Ante el ciudadano responde la
municipalidad —nombre del municipio y fecha—; la identidad del agente se ve
únicamente en el panel, con el mismo criterio de protección del personal que
US-038 aplica al validador. Cuál se usa lo decide el endpoint, no una bandera
que alguien puede olvidar.

La notificación al autor cuelga del mismo mecanismo que el resto y no nombra al
agente: pone al municipio como emisor y deja `actor` nulo.

### Archivado por inactividad: la política vive en un módulo (US-031)

`reports/archival.py` declara el plazo, qué cuenta como interacción (el máximo
entre la creación, el último comentario y el último me gusta) y cuándo se avisa
(7 días antes). El comando `archive_stale_reports` y la tarea de Celery son dos
formas de dispararlo, no dos copias de la regla.

**El plazo es configurable**: `DJANGO_ARCHIVAL_INACTIVITY_DAYS`, default **90**
días, declarado en `.envs/.local/.django`. Se lee en cada evaluación —no es una
constante capturada al importar—, así que cambiarlo alcanza con editar el
entorno y reiniciar el contenedor. La ventana del aviso lo sigue: son siete días
antes del plazo vigente, no de un número fijo.

Va en **días** y no en minutos, a diferencia de la ventana de objeción (US-047)
y de la retención del mapa: esas se demuestran esperando, y esta se demuestra
fechando un reporte en el pasado. El plazo corto no aporta nada.

**Cuenta desde la última señal de vida, no desde el alta.** Es la distinción que
más se presta a confusión: un reporte creado hace un año pero con un me gusta de
la semana pasada **no** se archiva, porque no está abandonado. "Antigüedad" y
"tiempo sin interacción" coinciden solo cuando nadie lo tocó nunca.

**Alcanza únicamente a los pendientes de validación.** Un reporte validado ya
entró en la cola del municipio, y archivarlo es una decisión de gestión
(US-013), no una consecuencia del desinterés. La tabla de transiciones lo
sostiene: `archivar_por_inactividad` sale solo de *Pendiente de validación*.

```bash
docker compose -f docker-compose.local.yml exec django /entrypoint \
    python manage.py archive_stale_reports
```

Tres decisiones que valen la pena:

- **El archivado es una transición como las demás.** Se agregó
  `Actor.SYSTEM` y la operación `archivar_por_inactividad` a la tabla, así que
  deja asiento en el historial —con `changed_by` nulo, que es como el historial
  dice "esto lo hizo el sistema"— y dispara el mismo evento del que cuelgan las
  notificaciones.
- **`Like` ganó `created_at`.** Sin fecha no hay forma de medir "sin likes ni
  comentarios". Los me gusta anteriores se fecharon en la migración con la
  creación de su reporte, que es la única fecha que se sabe cierta y la más
  conservadora: nunca adelanta el reloj.
- **La verificación corre cada quince minutos, no de madrugada.** Corría a las
  3:30 para no mover reportes en horario de uso del municipio. Con el plazo ya
  configurable, esa corrida diaria dejaba el archivado automático **sin poder
  demostrarse**: había que fechar un reporte en el pasado y después esperar a la
  madrugada. Es el mismo motivo por el que la confirmación de US-047 corre cada
  quince minutos. La razón original tampoco se sostenía para esta tarea: solo
  alcanza reportes *pendientes de validación* que nadie tocó en meses, o sea que
  no están en la cola de trabajo de nadie, y el aviso al autor se lee mejor a
  las diez de la mañana que a las tres.
- **Primero los avisos, después los archivados.** Si la verificación no corre
  por unos días, un reporte que cruza las dos ventanas en la misma corrida se
  archiva en lugar de recibir un aviso que ya no sirve. `archival_warning_sent_at`
  hace idempotente el aviso: la corrida diaria no lo repite siete veces.

`Report.archived_at` va como campo y no se deduce del historial porque el
listado de "mis reportes" lo muestra y ese listado no trae el historial:
deducirlo ahí costaría una consulta por fila.

## Decisiones del Sprint 5

### Un estado nuevo, y `resolver` deja de existir (US-046)

Se agregó **Resuelto pendiente de confirmación** entre *En proceso* y
*Resuelto*, y la transición `resolver` del agente municipal **se eliminó de la
tabla**: todo camino hacia *Resuelto* pasa ahora por el estado intermedio.

El motivo es que quien ejecuta el trabajo pasó a ser quien lo declara terminado.
Sin contraparte, el producto reproduciría adentro el mismo circuito sin
rendición de cuentas que existe para combatir: la parte responsable del trabajo
certificando su propio trabajo. La contraparte son los siete días de US-047 y la
apelación de US-048.

El agente sigue pudiendo cerrar el circuito, pero **confirmando** el cierre del
operario y no en lugar de él: `confirmar_resolucion_municipal`, desde el estado
intermedio y con su usuario en el historial.

**Cambio incompatible:** `POST /panel/reports/{id}/resolve/` ya no existe. Lo
reemplaza `POST /panel/reports/{id}/confirm-resolution/`, que sale de *Resuelto
pendiente de confirmación*.

### El origen de la transición es un campo, no una deducción (US-038)

`ReportStatusHistory.origin` guarda **de dónde salió** cada transición, más allá
de a qué estado llegó. Lo escribe `apply_transition` desde la tabla: quien
invoca no lo elige, así que ninguna operación puede quedar asentada con un
origen que no le corresponde.

Existe porque la forma de una transición dejó de alcanzar para saber qué
significa. Un reporte llega a *Reportado* porque un validador fue al lugar
(US-036) o porque diez vecinos lo confirmaron (US-040); llega a *Resuelto* por
silencio del autor o por decisión del agente. **El panel deducía la validación
en terreno mirando el par de estados, y con US-040 empezó a reportar como
validador a alguien que no existía** — el test que lo destapó está en
`test_collective_validation.py::test_it_is_not_reported_as_a_field_validation`.

La migración rellena el origen de los asientos anteriores a partir de las
transiciones que existían hasta entonces; sin eso, el panel habría perdido la
atribución de todo lo decidido hasta acá.

### Las guardas viven en la tabla, no en la vista

`Transition.guard` es una condición sobre el **reporte**, más allá de su estado.
Hoy la usa una sola transición: `apelar` la tiene para el tope de una apelación
por reporte.

Va ahí y no en el endpoint porque un segundo endpoint que llamara a la misma
transición se la saltearía. Se evalúa sobre la fila ya bloqueada, dentro de la
transacción: entre la lectura y la evaluación puede entrar otra apelación.

`closing_operation(report)` es la contracara: decide si el cierre del operario
abre ventana de objeción o es definitivo. El segundo cierre —el que sigue a una
apelación— va derecho a *Resuelto*, porque el autor ya gastó la única apelación
que tiene y no habría a quién darle una ventana nueva.

### Validación colectiva: dos conteos que no son el mismo (US-040)

`Report.confirmation_count()` **no** es el contador público de me gusta de
US-008. Descuenta dos grupos, por motivos distintos: al **autor**, que ya afirmó
que el problema existe al reportarlo, y a las **cuentas de trabajo**, cuya
confirmación se ejecuta yendo al lugar (US-036) y no por interacción social.

Está en el modelo y no en la vista que evalúa el umbral porque el filtro tiene
que ser uno solo: repetido en dos lugares, uno de los dos se olvidaría de
excluir a alguien y el umbral se alcanzaría antes de lo debido.

La evaluación es **sincrónica al persistir el me gusta**, con `select_for_update`
sobre la fila del reporte: dos me gusta que cruzan el umbral a la vez producen
una sola transición. Retirar me gusta después **no** revierte nada.

**Riesgo asumido y documentado.** El mecanismo es falseable con cuentas creadas
al efecto. Los controles son de *mitigación*, no de prevención: un me gusta por
usuario, exclusión del autor, exclusión de las cuentas de trabajo y umbral
parametrizable (`DJANGO_COLLECTIVE_VALIDATION_THRESHOLD`, default 10). La
detección de cuentas fraudulentas queda fuera del alcance del proyecto.

**Cómo se cambia el umbral.** La variable está declarada en
`.envs/.local/.django`: se edita el número y se reinicia el contenedor
(`docker compose -f docker-compose.local.yml up -d django`). No hace falta tocar
código, porque `collective_validation.threshold()` lee la configuración en cada
evaluación en lugar de capturarla al importar el módulo.

Está declarada en el archivo **aunque su valor sea el default**, a propósito:
una variable que solo existe en `settings/base.py` es configurable en teoría y
no en la práctica, porque para cambiarla hay que saber que existe. Para la demo
conviene bajarla a 2 o 3 — juntar diez cuentas distintas en vivo no es
demostrable.

### El aviso al autor también se elegía por la forma (US-040)

El mapa de `templates_status.py` estaba indexado por `(estado anterior, estado
nuevo)`, y desde US-040 ese par tiene **dos** significados: a *Reportado* desde
*Pendiente de validación* se llega por un validador que fue al lugar o por las
confirmaciones de los vecinos. El aviso decía siempre «un validador confirmó tu
reporte en el lugar», o sea le atribuía al vecino un validador que no existió.

Es exactamente la misma trampa que `get_validation()` ya había resuelto en el
panel, un nivel más abajo y descubierta después. **El discriminador es el
origen, no la forma de la transición**, y ahora el origen viaja en
`report_status_changed` como argumento propio en lugar de tener que sacarse del
`history`.

`ORIGIN_CHANGE_MESSAGES` tiene prioridad sobre el mapa por par y se indexa por
`(anterior, nuevo, origen)`. El mapa por par sigue siendo el caso general: una
transición nueva no obliga a tocar nada mientras su par sea inequívoco.

El panel recibió el complemento. `validation` seguía —correctamente— en nulo
para una validación colectiva, pero no había nada que ocupara su lugar: el
encabezado del detalle no mostraba **nada** y un reporte validado por la
comunidad se leía como uno que nadie validó. `collective_validation` lleva
cuándo se validó y con cuántas confirmaciones. Va como campo aparte y no como
una variante de `validation` porque ahí no hay persona de la que hablar, y
meterlos juntos obligaría al panel a preguntar cuál de los dos casos es —justo
la ambigüedad que el origen vino a resolver—. Quiénes confirmaron no se expone
(US-038); solo cuántos.

### Un problema ya reportado no se vuelve a crear (US-026 y US-032)

`POST /api/reports/` rechaza el alta si ya hay un reclamo **activo**
(*Pendiente de validación*, *Reportado*, *En proceso* o *Resuelto pendiente de
confirmación*) de la **misma categoría**, en la **misma municipalidad** y a no
más de `DJANGO_DUPLICATE_REPORT_RADIUS_METERS` (default 30) del punto. Si hay
varios, cuenta el más cercano. *Resuelto*, *Cancelado* y *Archivado* no
bloquean: un problema que reaparece después del cierre es un reclamo nuevo.

La detección (US-026) es `find_duplicate` en `reports/duplicates.py`. Recibe
coordenadas, categoría y municipalidad y devuelve el reporte o `None`. Qué se
hace con eso (US-032) está en la vista. La categoría es indispensable: un bache
y una vereda rota en la misma esquina son dos problemas. Los 30 m absorben el
error del GPS de un teléfono en la calle (10 a 20 m) sin unificar dos baches de
la misma cuadra.

**Consulta indexada sin PostGIS.** El proyecto no usa PostGIS, así que la
búsqueda es una caja delimitadora en el `WHERE` seguida de Haversine sobre las
pocas filas que quedan. Todas las condiciones van en la base, ninguna se
filtra en Python. Las cubre el índice parcial `report_duplicate_lookup` sobre
`(municipality, category, latitude, longitude)`, restringido a los estados
activos. La condición del índice repite `ACTIVE_STATUSES`: si esa lista cambia,
hace falta una migración, y un test falla si se desincronizan. Otro test
verifica con `EXPLAIN` que el plan usa el índice.

La respuesta es un **`409`** y no un `400`, para que el cliente la distinga de
un campo mal cargado. Trae el reclamo serializado, así la app puede ofrecer
sumarse sin hacer otra llamada:

```json
{
  "code": "report_already_exists",
  "detail": "Este problema ya fue reportado. Podés sumar tu apoyo al reclamo existente.",
  "existing_report": { "...": "lo del feed", "distance_meters": 12, "is_author": false }
}
```

- **Sumarse** es el `POST /like/` de siempre, que cuenta para la validación
  colectiva (US-040). No hay un endpoint ni un tipo de apoyo aparte.
- **El intento bloqueado no se registra** en ningún lado.
- **Ningún flag del cliente saltea la verificación.**

**La verificación corre antes de validar la foto, y el orden importa.** Con la
verificación en `validate()` o en `perform_create`, la foto de un reporte que
nunca se crea ya habría entrado al circuito de difuminado: hasta US-041 eso
significaba haberla anonimizado dentro del request; desde US-042, haberla
escrito en el storage privado y encolado una tarea. En los dos casos es trabajo
—y un archivo— sobre algo que no va a existir. Por eso `ReportViewSet.create`
hace esto:

1. Valida solo la ubicación y la categoría, con `ReportLocationSerializer`.
2. Resuelve la ubicación: geocoding y municipalidad.
3. Busca el reclamo existente.
4. Recién entonces pasa al serializer completo. `perform_create` reutiliza la
   ubicación ya resuelta para no geocodificar dos veces.

Si la ubicación o la categoría son inválidas, no se decide nada ahí y el `400`
sale como siempre, con todos los errores juntos.

`resuelto_pendiente_confirmacion` **sí** bloquea desde US-026. US-032 lo había
dejado afuera de forma provisoria. Mientras el cierre no está confirmado, el
problema sigue abierto y el lugar para decirlo es el reclamo existente.

**Carrera aceptada:** dos envíos simultáneos del mismo problema pueden crearse
los dos. Evitarlo pediría un bloqueo por zona.

### El mapa deja de dibujar los resueltos a los 15 días

El mapa responde «¿qué pasa hoy en mi barrio?». Con los resueltos de todos los
meses encima termina respondiendo «¿qué pasó alguna vez?»: una nube de puntos
verdes donde ya no hay nada que mirar.

**Sale del mapa y de ningún otro lado.** Sigue en el feed, en su detalle, en el
perfil de su autor y en el listado del panel. No se archiva, no cambia de estado
y no se borra. Por eso la política vive en `reports/map_retention.py` y no en la
máquina de estados: es una regla de *qué se dibuja*, no de qué existe, y ahí
está la diferencia con el archivado por inactividad de US-031, que sí mueve el
reporte.

Alcanza **solo** a *Resuelto*. *Resuelto, a confirmar* se queda: mientras corre
la ventana de objeción el caso está abierto, y esconderlo justo cuando el vecino
puede querer revisarlo sería esconderle lo que tiene que decidir.

La fecha sale del **historial de estados**, no de `Report.closed_at`. Ese campo
guarda cuándo el operario cerró el trabajo, que es hasta una semana antes de que
el reporte quede efectivamente *Resuelto* —en el medio corre la ventana de
objeción—, así que contar desde ahí adelantaría la desaparición de todos los
reportes en esa diferencia.

**El `isnull=False` de la condición no es decorativo.** SQL tiene tres valores:
`NULL < fecha` no da falso sino `NULL`, `NOT (NULL AND verdadero)` vuelve a dar
`NULL`, y un `WHERE` que no da verdadero descarta la fila. Sin esa cláusula, un
reporte resuelto sin asiento en el historial —que no debería existir, pero— se
borraba del mapa en lugar de quedarse, que es lo contrario del default seguro.
Lo destapó el test escrito para ese caso.

El plazo es `DJANGO_MAP_RESOLVED_RETENTION_MINUTES` (default `21600`, o sea 15
días), declarado en `.envs/.local/.django`. En minutos por lo mismo que la
ventana de objeción: una demostración necesita poder bajarlo a un par sin tocar
código.

### El plazo de objeción se configura en minutos (US-047)

`DJANGO_RESOLUTION_OBJECTION_MINUTES` (default `10080`, o sea siete días) y
`DJANGO_RESOLUTION_OBJECTION_WARNING_MINUTES` (default `1440`).

**En minutos y no en días** a propósito: la historia pide que la demostración en
la review pueda bajar el plazo a un par de minutos sin tocar código, y un
parámetro expresado en días no lo permite.

```bash
docker compose -f docker-compose.local.yml exec django /entrypoint \
    python manage.py confirm_resolved_reports
```

La tarea de Celery corre **cada quince minutos** y no una vez al día, por lo
mismo: con una corrida diaria la confirmación automática no se puede demostrar.

Primero los avisos y después las confirmaciones, para que un reporte que cruza
las dos ventanas en la misma corrida se confirme en lugar de recibir un aviso
que ya no sirve. Es idempotente: la segunda corrida no encuentra el reporte
porque ya no está en el estado de partida.

`Report.closed_at` es la fecha del cierre del operario, y es **la que toma el
indicador de tiempo de resolución** de US-023: los días de espera son un
mecanismo de control, no tiempo de trabajo municipal.

### La evidencia se acumula, no se pisa (US-046 y US-048)

`ResolutionEvidence` es una entidad propia y no campos sueltos sobre el reporte:
un reporte reabierto por apelación acumula más de una, y la gracia es poder
compararlas. El segundo cierre crea una nueva; la primera queda, junto con la
apelación que la objetó.

Guarda el área **al momento del cierre** y no la que el operario tenga hoy: un
traslado posterior no puede reescribir quién se hizo cargo de este trabajo.

`with_closed_count` pasó a contar evidencias en lugar de asientos del historial
con estado *Resuelto*: desde US-047 ese estado lo produce la confirmación
automática o el agente, no el operario.

La reapertura por apelación **conserva el área operativa** y no vuelve a
*Reportado*: el trabajo mal ejecutado le corresponde a quien lo ejecutó.

### Anonimización de rostros y patentes (US-041)

Toda foto que entra por la API se guarda con los rostros y las patentes
difuminados (RN-11, Ley 25.326). Son **cuatro** puntos de carga: alta del
reporte, reemplazo de su foto, cierre del operario (US-046) y apelación
(US-048). Los cuatro declaran `PendingPhotoField`
(`urbancheck/common/fields.py`), que valida la imagen y la encamina al
difuminado. El campo `photo` del modelo nunca recibe la original. Un test
recorre los serializers de entrada —los de la app y los del panel— y falla si
aparece una foto que no pase por ese campo.

> El campo se llamaba `AnonymizedImageField` y difuminaba ahí mismo, dentro de
> `is_valid()`. US-042 movió el difuminado a una tarea y lo renombró, porque el
> nombre viejo pasó a mentir.

**Decisión técnica: no se usa OpenAI Vision.** El documento de Alcance supone la
API de visión de OpenAI para las funciones de IA. Para esta se descarta porque
un modelo de lenguaje visual no devuelve cajas con la precisión necesaria para
tapar una cara y no puede transformar la imagen. Además, el despliegue es
on-premise y una obligación legal no puede depender de un servicio externo.
**Esta contradicción tiene que reflejarse en la próxima versión del Alcance.**
En su lugar se usan detectores preentrenados que corren localmente en CPU. No
hay entrenamiento, dataset propio, fine-tuning ni GPU:

| Pieza | Modelo | Licencia |
|---|---|---|
| Rostros | YuNet 2023mar (OpenCV Zoo), vía `cv2.FaceDetectorYN` | MIT |
| Patentes | YOLOv9-s 608 *end2end* de [open-image-models](https://github.com/ankandrew/open-image-models) | MIT |
| Difuminado | Gaussiano de OpenCV | Apache 2.0 |

Los pesos están versionados en `urbancheck/anonymization/weights/` y nunca se
bajan en tiempo de ejecución. El detector de patentes se corre directamente con
`onnxruntime`, no a través del paquete `open-image-models`: ese paquete, ante un
error de inferencia, lo registra y devuelve «sin detecciones», y acá eso
significaría publicar una patente sin difuminar.

Cómo funciona `anonymize()` (`urbancheck/anonymization/service.py`):

- Aplica la orientación EXIF a los píxeles y después **descarta el EXIF**, que
  trae el GPS y el modelo del teléfono.
- Corre los dos detectores sobre la misma imagen. En fotos de 1200 px o más, las
  patentes se buscan además por cuadrantes, porque una patente lejana
  desaparece al reducir la foto a 608 px.
- Expande cada caja con un margen: 25 % para los rostros y 15 % para las
  patentes.
- Difumina todas las cajas en una sola pasada con un gaussiano de sigma igual a
  ¼ del lado de la caja. **No usa pixelado**, que se revierte en parte con
  superresolución. Para las cajas grandes, el gaussiano se aplica sobre la
  región reducida y se reescala en bilineal. Sin eso, una patente de cerca
  tardaba 30 s.
- Conserva formato (JPEG, PNG y WebP; cualquier otro sale como JPEG),
  resolución y transparencia.
- El log registra cantidades y tiempo, **nunca** el nombre ni la ruta del
  archivo.

**La original no pasa por un temporal.** Django escribe en `/tmp` todo archivo
de más de 2,5 MB, y de ahí no la borra nadie. `FILE_UPLOAD_HANDLERS` lo
reemplaza por un handler solo de memoria, que rechaza con 400 lo que supere
`DJANGO_PHOTO_MAX_UPLOAD_MB` (15 por defecto) antes de leerlo. En el admin, la
foto del reporte es de solo lectura.

> **Actualizado por US-042.** Cuando se escribió esto la original no tocaba el
> disco en ningún momento, porque el difuminado corría dentro del request. Con
> la publicación diferida sí se escribe, en un storage privado fuera de
> `MEDIA_ROOT` y sin URL, hasta que la tarea la procesa y la borra. Ver
> «Publicación diferida hasta completar el difuminado (US-042)».

**Ante un fallo, la foto no se publica.** Si el detector falla, no se guarda
nada. Desde US-042 el fallo es asíncrono: el alta devuelve 201, el reporte
queda sin publicar y su autor recibe el aviso.

#### Línea base medida (escenario 9)

`python manage.py benchmark_anonymization [CARPETA] [--report FILE]
[--annotate DIR] [--output DIR]` corre el servicio sobre 37 fotos urbanas de
Wikimedia Commons con licencia libre. **Desde el 15/10/2026 las fotos no se
versionan** (son personas y patentes): viven en `benchmark_data/anonymization/`,
ignorada por git y por Docker, o donde diga `DJANGO_ANONYMIZATION_REFERENCE_SET`.
El formato y el criterio de etiquetado están en
`urbancheck/anonymization/benchmark/README.md`. El set incluye peatonales
con multitudes, calles con autos y colectivos, patentes de cerca, escenas
nocturnas y baches sin nadie. Los rostros reconocibles y las patentes legibles
de cada foto se contaron a mano; `manifest.json` trae la fuente, la licencia y
una nota por imagen.

| | Detectados | Tasa |
|---|---|---|
| Rostros | 175 / 189 | **92,6 %** |
| Patentes | 28 / 30 | **93,3 %** |
| Total | 203 / 219 | **92,7 %** |

Tiempo por imagen (1600 px, CPU del contenedor de desarrollo): mediana de
0,8 a 1 s y máximo de 1,3 s, según la carga. Una foto de 12 MP tarda menos de
2 s. El límite de la historia es 10 s. Casi todo el tiempo se va en las cinco
pasadas del detector de patentes (imagen entera y cuadrantes).

Falsos negativos (son los que justifican el reclamo de US-043):

- **Rostros de perfil o mirando hacia abajo** en peatonales: 7 casos, en
  `people_03`, `05`, `07` (2), `08` y `09` (2). YuNet se entrenó sobre todo con
  caras frontales.
- **Personas chicas al fondo**: 4 casos. Son un caminante en `people_04`, un
  hombre y la agente de tránsito en `people_06`, y el chofer del colectivo de
  `street_cars_05`, detrás del parabrisas.
- **Caras parcialmente tapadas**, por un gorro o por el borde de la foto: 2
  casos (`people_10` y `people_01`).
- **Una mujer detrás de otra**, en `street_cars_01`.
- **Patentes cortadas o tapadas**: la de una moto cortada por el borde inferior
  (`people_09`) y una trasera tapada por otro auto (`street_cars_14`).

Falsos positivos: dos llantas y dos carteles detectados como rostro, la
calcomanía «TAXI PREMIUM» y dos carteles detectados como patente, y siluetas
nocturnas. Difuminan de más, pero no exponen nada. Las caras de tapas de
revistas y de carteles publicitarios se cuentan como rostros.

El avatar de usuario **no** se anonimiza: es la foto que la propia persona elige
para su perfil, no un dato de terceros.

### Comparación automática del cierre: informa, no decide (US-015)

Cada cierre de un operario dispara una comparación entre la foto original del
reporte y la foto del cierre. La hace un modelo de visión generalista, que
recibe además la categoría y el parte de trabajo. El veredicto sale de un
conjunto cerrado: `consistente`, `problema_persistente`, `lugar_distinto` o
`trabajo_incoherente`. Los tres últimos marcan el reporte como **cierre a
revisar** en el listado del panel mientras dura la ventana de objeción. El
listado acepta `?closure_review=true` para filtrarlos.

**El veredicto no tiene ninguna consecuencia sobre el reporte.** No cambia el
estado, no toca el plazo de US-047 y no habilita ni impide transiciones.
`ResolutionComparison` no tiene ninguna FK ni escritura hacia `Report`. El
control efectivo sobre un cierre mal hecho sigue siendo la apelación del vecino
(US-048): alguien responde por ella, mientras que un modelo que se equivoca lo
hace en silencio.

- **Cuelga de la evidencia, no del reporte**: un segundo cierre tras una
  apelación trae su propia comparación y la del primero se conserva. Siempre se
  compara contra la foto original del reporte.
- **Asíncrona**: `register_comparison` deja la fila dentro de la transacción
  del cierre, y si el cierre se revierte no queda nada. El operario no espera a
  un servicio externo. **El disparo se movió con US-042**: lo hace
  `enqueue_comparison` cuando el difuminado de la foto del cierre termina,
  porque recién ahí hay una imagen publicable, y es la difuminada —que es la
  única que se le puede mandar a un servicio externo—. Encolarla al cerrar
  dejaría toda comparación en `sin material`, en silencio.
- **Un fallo nunca bloquea un cierre**:
  - Timeout, 429 y 5xx se reintentan con espera exponencial, hasta
    `DJANGO_RESOLUTION_COMPARISON_MAX_RETRIES` veces.
  - Un 4xx, una respuesta fuera de esquema, un broker caído o un error
    inesperado dejan la comparación como `no_disponible`, con un código corto
    en `failure_reason`. Nunca se guarda el cuerpo de la respuesta.
  - La respuesta se valida con un serializer y **no se interpreta a mano**: un
    JSON envuelto en un bloque de código también se descarta.
- **Sin material** (`sin_material`): si falta alguna de las dos imágenes, no se
  llama al servicio. Se verifica al cerrar y otra vez al ejecutar, por si la
  imagen se borró entre medio (US-043).
- **Visibilidad**: solo la ve el panel municipal, dentro de
  `PanelResolutionEvidenceSerializer`. Es el mismo patrón de dos serializers de
  US-038: ningún serializer del ciudadano, del validador ni del operario la
  referencia.
- **Trazabilidad**: la fila guarda fecha, veredicto, explicación, modelo que
  respondió e intentos. En el admin se ve en solo lectura.
- **El parte del operario viaja como dato**: va delimitado en el prompt, que
  instruye ignorar cualquier pedido que aparezca dentro de él. Aun así, es
  texto que controla quien cierra, y por eso tampoco conviene que el veredicto
  decida nada.

**Por qué acá sí un modelo generalista y en US-041 no.** El difuminado necesita
cajas precisas, transformar la imagen, y es una obligación legal que no puede
depender de un servicio externo. Esto es una comparación cualitativa,
degradable y sin valor legal: si el servicio no está, el circuito funciona
igual.

**Solo salen imágenes difuminadas.** El cliente (`reports/vision.py`) recibe
bytes que `comparison.py` lee del storage, donde solo existe la versión
procesada de US-041. Un test sube una foto con rostros y patentes y verifica
que lo que llega al cliente es exactamente lo almacenado.

**Proveedor gratuito: Gemini, y una advertencia.** El cliente habla el dialecto
de chat completions de OpenAI, así que Gemini, Groq, OpenRouter u Ollama se
usan cambiando `DJANGO_RESOLUTION_COMPARISON_BASE_URL` y `_MODEL`. El default es
`gemini-3.6-flash` sobre el free tier de Google AI Studio. **En el plan gratuito
Google puede usar el contenido para mejorar sus productos**: las fotos van
difuminadas, pero en producción corresponde el plan pago o un proveedor sin
retención. El documento de Alcance supone OpenAI Vision, y este desvío tiene
que reflejarse en su próxima versión, igual que el de US-041.

| Variable | Default | |
|---|---|---|
| `DJANGO_VISION_PROVIDER` | vacío | Proveedor nulo: no se compara nada. `openai_compatible` activa el adaptador de chat completions (Sprint 5) |
| `DJANGO_RESOLUTION_COMPARISON_API_KEY` | vacía | Con `openai_compatible` y sin clave, la función queda apagada: todo cierre figura "no disponible" |
| `DJANGO_RESOLUTION_COMPARISON_BASE_URL` | endpoint OpenAI de Gemini | |
| `DJANGO_RESOLUTION_COMPARISON_MODEL` | `gemini-3.6-flash` | Los modelos rotan: verificar en la página de precios de la API |
| `DJANGO_RESOLUTION_COMPARISON_MAX_RETRIES` | 3 | Solo fallos transitorios |
| `DJANGO_RESOLUTION_COMPARISON_TIMEOUT_SECONDS` | 30 | Por debajo del soft time limit de Celery (60 s) |
| `DJANGO_RESOLUTION_COMPARISON_MAX_SIDE_PX` | 1024 | Lado mayor con el que viajan las fotos |

Una comparación que quedó `no_disponible`, por ejemplo por falta de clave o por
una caída larga del proveedor, **no se reintenta sola**. Para volver a correrla:
`python manage.py retry_resolution_comparisons [--report ID]`. Ejecuta en el
momento, sin pasar por Celery, e informa el veredicto de cada cierre. Las que
quedaron `sin_material` no se tocan.

En los tests, `conftest.py` bloquea el cliente y reemplaza `delay`: ningún test
sale a la red ni encola en el Redis real.

### Denuncia por dato personal visible: oculta primero, revisa después (US-043)

Un vecino denuncia una foto publicada en la que el difuminado de US-041 no
detectó un rostro o una patente: `POST /api/reports/{id}/privacy-request/`,
con `{"evidence": <id>}` si la foto es la de un cierre del operario. Lo resuelve
el **administrador de la plataforma** desde
`/api/platform/privacy-requests/`, eliminando la imagen (`remove-image/`) o
desestimando (`dismiss/`).

**La entidad es la denuncia de US-021, que todavía no existía.** US-043 pedía
sumar un motivo a su catálogo. Como no había catálogo, se creó
`ReportComplaint` con un solo motivo, `dato_personal`. US-021 le suma los suyos
sin modelo nuevo: entre motivos cambian el responsable y el efecto, no la
entidad. El reparto está declarado en dos constantes del modelo:

- `PLATFORM_REASONS`: los motivos que resuelve el administrador.
  `ReportComplaint.objects.for_municipal_review()` los excluye, y es lo que
  tiene que usar la bandeja municipal de US-049 (escenario 10). Desde US-021
  se deriva del catálogo `REASON_RECIPIENTS`.
- `HIDING_REASONS`: los motivos que ocultan el reporte. Es la única excepción al
  principio de que una denuncia no altera la visibilidad por sí sola.

#### Agregado del 15/10/2026

- **La foto de una apelación también se denuncia** (escenario 1 nombra tres
  imágenes: la del reporte, la de un cierre y la de una apelación). La
  solicitud lleva `appeal` en lugar de `evidence`; eliminarla conserva el
  reporte y el motivo de la objeción, como con la foto de un cierre.
- **El panel no muestra la imagen en revisión.** El agente sigue viendo el
  reporte retenido y el aviso `under_privacy_review`, pero el detalle trae
  `photo: null` para la imagen denunciada (y solo para esa).
- **La bandeja también está en el admin de Django**, con filtro de fuera de
  plazo y las acciones "Eliminar la imagen denunciada" y "Desestimar", que
  llaman a los mismos servicios que el panel. Solo las ve el administrador de
  la plataforma.
- **La visibilidad pública se declara una sola vez** en
  `publicly_visible_condition()` y `publishable_condition()` (modelo de
  reportes). La bandeja de validación dejó de repetir sus filtros. Un tercero
  ya no abre por id un reporte cancelado o archivado, y un reporte retenido por
  dato personal ya no acepta denuncias de contenido.

### Denunciar un reporte (US-021)

El botón *Denunciar* de la app: `POST /api/reports/{id}/complaints/` con
`{"reason": ..., "comment": ...}`. El motivo es obligatorio y el comentario,
opcional (hasta 500 caracteres). Responde `201` con el acuse, que incluye
`recipient` y un `detail` listo para mostrar: la revisión del municipio para las
de contenido, el plazo de la RN-12 para las de dato personal.

`GET /api/reports/complaint-reasons/` sirve el catálogo —valor, etiqueta y
destinatario— para que la app no tenga una copia.

| Motivo | Destinatario | Efecto inmediato |
| --- | --- | --- |
| `contenido_inapropiado` | agente municipal de la jurisdicción (US-049) | ninguno |
| `reporte_falso` | agente municipal de la jurisdicción (US-049) | ninguno |
| `dato_personal` | administrador de la plataforma (US-043) | oculta el reporte |

**El catálogo se declara una sola vez**, en `ReportComplaint.REASON_RECIPIENTS`.
De ahí se derivan `PLATFORM_REASONS`, los dos querysets de revisión y el acuse.
Sumar un motivo es sumar una fila a esa tabla; un test falla si alguno queda sin
destinatario.

**Esta historia solo registra.** `complaints.py` no ejecuta ninguna transición
ni toca la visibilidad: no hay umbral de denuncias (escenario 5). La versión
anterior ocultaba con tres, y se descartó porque tres cuentas nuevas alcanzaban
para tumbar cualquier reclamo incómodo. El motivo `dato_personal` delega en
`request_personal_data_review` y hereda el circuito de US-043 completo. La
bandeja municipal y la resolución son de US-049, que tiene que partir de
`for_municipal_review()`.

Rechazos:

| Caso | Respuesta |
| --- | --- |
| Sin motivo, o motivo fuera del catálogo | `400` en `reason` |
| El reporte es propio | `403` |
| Cancelado, Archivado o retirado por protección de datos | `409` `report_not_public` |
| Ya lo denunció por ese motivo | `409` `complaint_already_filed` |
| Cuenta de trabajo (validador, agente, operario) | `403` |

**Dos reglas de duplicado, una por circuito.** Las de contenido son únicas por
denunciante, reporte y motivo **para siempre**
(`unique_content_complaint_per_reason`): que el municipio desestime una no
habilita a presentarla otra vez. Las de dato personal siguen contándose por
imagen y solo mientras están en curso, como las dejó US-043, porque la foto
puede cambiar.

**El autor y `privacy-request`.** El escenario 7 prohíbe denunciar el reporte
propio, y `complaints/` lo rechaza para los tres motivos. El endpoint de US-043,
`privacy-request/`, se conserva sin cambios —es el único que denuncia la foto de
un cierre del operario— y sigue dejando que el autor pida la revisión de su
propia foto, que fue una decisión explícita de aquella historia.

**Anonimato.** El denunciante, el comentario y la cantidad de denuncias no
viajan en ningún serializer del reporte; un test recorre detalle, feed, "mis
reportes", mapa y comentarios, como autor y como tercero.

**Avisos (pedido posterior a la historia).** Denunciar genera dos:

- `denuncia_recibida`, a quien denunció: el mismo texto del acuse, que queda en
  sus avisos.
- `reporte_denunciado`, al autor: "otro vecino denunció tu reporte", sin
  `actor`, sin motivo y sin comentario. Se manda **una sola vez mientras haya
  denuncias de contenido pendientes**: uno por denuncia le diría cuántas
  recibió, que es lo que el escenario 9 reserva. Vuelve a avisarse recién cuando
  las anteriores se resolvieron.

Con el motivo `dato_personal` el autor no recibe `reporte_denunciado` sino el
`reporte_en_revision` de US-043, que además le explica por qué dejó de verse.
Migración `notifications/0009`.

**Visibilidad pública: una sola función.** `ReportQuerySet.publicly_visible()`
(feed, mapa, perfil público) y `visible_to(user)` (detalle y todo lo que cuelga
de él) son las únicas definiciones de qué ve un tercero. Antes eran tres
filtros sueltos en la vista. US-042 sumó ahí su condición —`photo_ready()`, la
imagen todavía en procesamiento— y con eso quedaron cubiertos el feed, el mapa,
la búsqueda de US-020 y el perfil público sin tocar una vista.

- Basta **una** solicitud pendiente, sin umbral.
- La retención **se deduce** de que haya una solicitud pendiente (`on_privacy_hold()`)
  y no se guarda como marca en el reporte. Una marca habría que apagarla en
  cada camino que resuelve, y si queda prendida esconde el reporte para
  siempre.
- El **autor sigue viendo** su reporte, con `under_privacy_review: true`.
  Ocultárselo a él no protege a nadie.
- Para un tercero, detalle, comentarios, me gusta y apelación responden `404`.
  La excepción es la propia denuncia: quien ya denunció recibe `409` y no un
  `404` que parece un borrado (escenario 9).
- El panel no es una vista pública: el agente sigue viendo el reporte, con
  `under_privacy_review` para saber por qué el vecino no lo ve.

**Se resuelve por imagen, no por solicitud.** Eliminar o desestimar cierra todas
las solicitudes pendientes sobre el mismo archivo. Si no, el reporte seguiría
oculto por las solicitudes de otros vecinos sobre algo ya decidido. El
duplicado es por persona, imagen y motivo, mientras la solicitud está
pendiente: otro vecino puede sumar la suya, y el mismo vecino puede volver a
denunciar después de una desestimación.

**Borrado físico dentro de la transacción, al final.** No se usa `on_commit`.
Si el borrado falla, todo se revierte y la solicitud queda pendiente, con el
reporte todavía oculto. Con `on_commit`, un borrado caído dejaría la base
diciendo "eliminada" con el archivo todavía servido. Lo que se borra es
`image_name`, el archivo tal como era al recibir la solicitud: si el autor
reemplazó la foto mientras tanto, se borra la denunciada y la nueva queda.

- **Eliminar la foto del reporte retira el reporte entero, para siempre.** Se
  aparta del escenario 5, que pedía republicarlo sin imagen: por decisión de
  producto, **ningún reporte sin foto se vuelve a publicar**. La marca es
  `Report.photo_removed_at`, y `publicly_visible`/`visible_to` lo excluyen como
  a uno retenido. La fila no se borra: de ella cuelga el registro de la RN-12.
  - Lo sigue viendo el autor (detalle y "mis reportes", marcado como retirado)
    y el municipio en el panel.
  - Sale de la bandeja del validador y no se puede editar (`is_editable`): una
    foto nueva no lo volvería a publicar.
  - **No bloquea duplicados** (`find_duplicate`): si el problema sigue, el
    vecino tiene que poder reportarlo de nuevo, y el aviso se lo dice.
  - El panel y la bandeja del operario lo siguen mostrando: el problema físico
    puede existir igual y la gestión municipal no se corta.
- **La foto de un cierre** (escenario 11) sí se retira sola: el reporte
  conserva la suya, su estado y el parte de trabajo.
- `Report.photo` y `ResolutionEvidence.photo` admiten vacío; el alta sigue
  exigiendo foto porque el serializer la declara obligatoria.
- **Avisos**, todos sin `actor`: ante el vecino responde la plataforma, y
  quien denunció no se expone.
  - `reporte_en_revision`, al autor, cuando se oculta su reporte. Uno solo
    aunque denuncien varios, y ninguno si lo denunció él mismo.
  - `imagen_retirada` o `reporte_restituido`, al autor, según la decisión. Si
    se eliminó la foto del reporte, el aviso dice que se retiró el reporte y
    que puede volver a reportar el problema. `reporte_restituido` solo va si
    el reporte de verdad volvió a verse: otra imagen suya puede seguir en
    revisión.
  - `denuncia_resuelta`, a cada vecino que denunció esa imagen, con el
    resultado. El autor no lo recibe: ya tiene el suyo.

**Plazo.** `DJANGO_PERSONAL_DATA_REVIEW_MINUTES` (default 1440) se cuenta desde
la **recepción** (`created_at`). El modelo no tiene `updated_at` justamente
para que nada pueda contarse desde ahí. Con un plazo único, ordenar por
antigüedad ya pone primero las vencidas (escenario 7). La bandeja devuelve
`remaining_seconds` (negativo si venció) e `is_overdue`. Las resueltas
(`?state=resolved`) traen `resolved_within_deadline`, que es la evidencia de
cumplimiento de la RN-12.

**Quién puede denunciar**: cualquier cuenta de vecino, sea o no el autor y
aparezca o no en la foto (escenario 3). Las cuentas de trabajo reciben `403`,
igual que para reportar o comentar. Quien trabaja en un municipio y ve un
rostro lo denuncia desde su cuenta personal.

**Límites conocidos:**

- `/media/` se sirve sin autenticación. Ocultar el reporte no invalida la URL
  de la foto que un cliente ya tenga guardada; solo el borrado físico la corta.
- Las fotos de las **apelaciones** (US-048) también se publican y no son
  denunciables todavía: la historia nombra la foto del reporte y la del cierre.
- Nada avisa al administrador cuando entra una solicitud: la bandeja se
  consulta.
- Un vecino puede volver a denunciar una imagen ya desestimada y ocultarla otra
  vez. Queda para la moderación de US-021.

### Publicación diferida hasta completar el difuminado (US-042)

**Un reporte existe desde que el vecino lo envía, pero no es público hasta que
su imagen está difuminada.** US-041 difuminaba dentro del request: el POST se
bloqueaba varios segundos y un fallo del detector devolvía `400` y perdía el
reporte en el acto, sin ningún reintento. Ahora el endpoint responde enseguida,
la foto entra a una cola y el reporte aparece cuando el difuminado termina.

**El estado es de la imagen, no del reporte.** La máquina de estados de US-013
no se tocó. `PendingPhotoMixin` (`urbancheck/anonymization/models.py`) suma
`photo_status`, `photo_pending`, `photo_attempts`, `photo_failed_at` y
`photo_queued_at` a los tres modelos que reciben fotos —reporte, evidencia de
cierre y apelación— y la visibilidad se resuelve con una condición más en el
queryset.

**La contrapartida, dicha en voz alta: la original ahora sí toca el disco.**
US-041 garantizaba que no pasara nunca, ni por un temporal. Procesar en
diferido obliga a guardarla hasta que la tarea la tome. Se mitiga, no se
disimula:

- Vive en `PENDING_PHOTO_ROOT`, **fuera de `MEDIA_ROOT`**, así que la ruta
  `/media/` no la alcanza.
- `PendingPhotoStorage` no tiene `base_url`, así que `photo_pending.url`
  levanta `ValueError`. Pasar `base_url=None` por configuración no alcanza:
  `FileSystemStorage` lo interpreta como "no configurado" y cae en `MEDIA_URL`.
- Permisos `0600`, y el archivo se borra apenas termina el procesamiento, salga
  bien o mal. Una foto sin difuminar no se conserva "por las dudas".
- En producción ese destino **no puede** tener lectura pública ni CDN, y el
  worker necesita poder leerlo o toda foto termina en `fallida`.

**Transitorio y permanente no son lo mismo.** `AnonymizationError` se abrió en
dos: `TransientAnonymizationError` (falló el detector ONNX) se reintenta
`DJANGO_ANONYMIZATION_MAX_RETRIES` veces con espera creciente desde
`DJANGO_ANONYMIZATION_RETRY_BASE_SECONDS`; `PermanentAnonymizationError` (el
archivo no se puede abrir) **no se reintenta ni una vez**, porque el resultado
sería el mismo y el vecino se entera una hora más tarde de lo necesario.

**Toda rama termina en `procesada` o en `fallida`.** Una foto que se queda en
`pendiente` para siempre es un reporte invisible para siempre, que es la forma
silenciosa de perder un reclamo. Por eso además hay una verificación periódica
—`requeue_stale_pending_photos`, cada 15 minutos— que reencola lo que lleva más
de `DJANGO_ANONYMIZATION_STALE_MINUTES` en cola: cubre el mensaje que el broker
nunca entregó, que no falla y por lo tanto no avisa a nadie. Mide desde
`photo_queued_at` y no desde el alta de la fila, o una foto reemplazada hoy
sobre un reporte viejo parecería vencida al instante.

**Ante el fallo definitivo se pierde el reporte, no la privacidad de un
tercero.** No hay vía degradada. El reporte queda sin publicar, su autor recibe
el aviso `imagen_no_procesada` con la invitación a volver a cargarlo —sigue en
*pendiente de validación*, así que `is_editable` ya lo permite— y el caso queda
en el log con su `code`, en `photo_attempts` y en el admin.

**El escenario 6 es una afirmación de la base, no una promesa del código.** Un
`CheckConstraint` por modelo (`photo = '' OR photo_status = 'procesada'`)
alcanza también a `update()` y `bulk_update()`, que no pasan por `save()`.
Encima hay tres capas más: la guarda de `PendingPhotoMixin.save()`, el admin
con los campos en solo lectura, y `apply_transition`, que rechaza gestionar un
reporte sin publicar. El panel no dibuja esas acciones porque
`available_transitions` ya las descuenta: dejar el botón listado sería ofrecer
algo que el servidor contesta con `409`.

**La excepción de `PHOTO_EXEMPT_TARGETS` no es un descuido.** *Cancelado* y
*archivado* se permiten sobre un reporte sin publicar. Los dos lo sacan de la
vista pública en lugar de acercarlo a ella, y sin la excepción el archivado por
inactividad (US-031) —que transiciona reportes *pendientes de validación*, que
es justo donde queda uno cuyo difuminado falló— lo dejaría varado para siempre.

**La comparación de US-015 se encadena al difuminado.** `register_comparison`
crea la fila al cerrar, para que el panel muestre "pendiente" desde ese
momento, pero el envío lo dispara `run_anonymization` al terminar. Encolarla al
cerrar dejaría **toda** comparación en `NO_MATERIAL` en silencio, porque en ese
instante `evidence.photo` está vacía; y además lo que hay que mandar a un
servicio externo es la difuminada, no la original.

**Quién ve un reporte sin publicar**: su autor y el panel municipal, nadie más.
No aparece en feed, mapa, detalle de terceros, búsqueda (US-020), perfil
público (US-027) ni bandeja de validación (US-040), y **no puede recibir me
gusta ni de su propio autor**: si pudiera, el umbral colectivo se alcanzaría
sobre algo invisible. El panel sí lo ve, con `photo_status`, para saber por qué
el vecino no lo encuentra.

**Cambio de comportamiento visible**: reemplazar la foto de un reporte lo
**despublica** hasta que la nueva se difumine. Es la misma regla de siempre —no
se publica una imagen sin procesar— y el móvil lo avisa, porque sin aviso se
lee como un bug.

**De paso se cerró un hueco de US-043**: el `report_count` del perfil público
contaba todos los reportes del autor, así que delataba los cancelados, los
archivados y los retenidos. Ahora pasa por `publicly_visible()`.

**Límites conocidos:**

- **Las imágenes preexistentes quedaron marcadas como `procesada` sin haber
  pasado por el difuminado** (migración `reports/0012`). Desde el 15/10/2026
  existe el comando retroactivo: `python manage.py anonymize_existing_photos`
  cuenta las que nunca pasaron por el servicio (`photo_attempts = 0`) y con
  `--apply` las difumina; la que no se puede procesar se retira y se avisa al
  autor. Es idempotente. **No se ejecutó sobre ningún entorno**: toca archivos
  publicados y lo tiene que autorizar el equipo.
- Un reporte en procesamiento **sigue bloqueando** un alta duplicada (US-032).
  Excluirlo produciría dos reclamos del mismo bache publicados a la vez, que es
  peor y permanente. El costo es que durante esos segundos la tarjeta del `409`
  no se puede abrir ni apoyar, y el móvil lo dice en vez de ofrecerlo.
- Si el difuminado de la foto de un **cierre** falla, el cierre queda en pie:
  el reporte ya pasó a *resuelto pendiente de confirmación* y el vecino ya fue
  avisado. Queda un parte de trabajo con descripción y sin imagen, la
  comparación en `no disponible` y el operario notificado. Revertir la
  transición abriría un caso que la historia no plantea.
- Un archivo pendiente puede quedar huérfano si el borrado falla o si el autor
  elimina el reporte mientras se procesa. No afecta lo publicado: es limpieza.

## Decisiones del Sprint 6

### Tutorial de bienvenida: la marca vive en la cuenta (US-051)

- `User.onboarding_completed_at` es una fecha nula por defecto, no un booleano:
  dice cuándo se vio el tutorial y no cuesta más. La app decide con este campo
  si muestra el recorrido; vive en la cuenta y no en el dispositivo, así que
  reinstalar la app o cambiar de teléfono no lo vuelve a mostrar.
- **La migración `users/0010` marca a todas las cuentas existentes** con la
  fecha del despliegue. Así los vecinos que ya usaban la app no reciben el
  tutorial (escenario 9) sin ninguna condición extra en el código: para la app,
  una cuenta preexistente es una que ya lo vio.
- El campo viaja en `/api/users/me/` y en la respuesta del login de allauth
  headless (`HeadlessAdapter.serialize_user`), igual que `must_change_password`.
  Se agrega **después** del `super()`, porque el adapter base descarta los
  nulos y acá el nulo es justamente la señal de "mostrar".
- `POST /api/users/me/onboarding/` lo marca. Es idempotente: el `UPDATE` va
  condicionado a `onboarding_completed_at IS NULL`, así el reintento de la app
  tras un error de red no pisa la fecha original. Terminar y omitir llaman a lo
  mismo. Solo el vecino (`IsCitizen`, que delega en `participates_as_citizen`):
  las cuentas de trabajo reciben `403`. El `PATCH` de `/me` no lo escribe.

### Moderación de contenido: del agente, con cuatro contrapesos (US-049)

- **No existe un rol moderador.** El agente municipal resuelve las denuncias
  por contenido (`contenido_inapropiado`, `reporte_falso`) de su jurisdicción,
  desde `/api/panel/moderation/`, que hereda `JurisdictionScopedMixin`: otra
  municipalidad responde `404`. La bandeja parte de
  `ReportComplaint.objects.for_municipal_review()`, así que las de dato
  personal nunca entran (las resuelve el admin, US-043).
- **Una decisión por reporte, no por denuncia** (`ModerationDecision`). Descartar
  (`discard`) o desestimar (`dismiss`) cierra todas las denuncias pendientes de
  contenido y las enlaza a la decisión. El motivo es obligatorio en los dos
  sentidos. Toda la operación es una sola transacción
  (`reports/moderation.py`).
- **El descarte es una transición de la máquina única**: `descartar_por_moderacion`,
  con origen `moderacion_municipal`, a *Cancelado* (no a *Archivado*: cancelado
  es "no era real", archivado es "caducó"). Es **una operación con una fila por
  estado de origen** —los cinco estados publicados—; `apply_transition` elige la
  fila sobre el reporte bloqueado. Su guarda exige denuncias de contenido
  pendientes: sin eso, el descarte sería una cancelación libre desde cualquier
  estado. No se ofrece como botón del panel (`MODERATION_ORIGINS`), solo desde
  la bandeja.
- **Contrapeso 1, el motivo es público.** La visibilidad no cambia: un reporte
  descartado sale del feed y del mapa por su estado, como cualquier cancelado.
  Pero `retrieve` de `/api/reports/{id}/`, si el reporte no es visible y tiene un
  descarte vigente (`Report.objects.moderation_notices()`), responde a un tercero
  el aviso reducido (`ModerationNoticeSerializer`: número, categoría, estado,
  fecha y motivo; sin foto, descripción, autor ni denunciantes). **Decisión del
  usuario (20/10)**. Nada que cuelgue del detalle se habilita: comentarios, me
  gusta y denuncias siguen en `visible_to` y responden `404`.
- **Contrapeso 2, la apelación.** **Decisión del usuario (20/10), contraria a
  la historia**: la resuelven el administrador —todas— y el agente —solo las de
  su municipalidad—, desde `/api/panel/moderation-appeals/` (`IsPanelUser`,
  acotada con `Report.objects.for_user`; otra municipalidad responde `404`). La
  historia la dejaba solo en manos de la plataforma, para que no la decidiera el
  mismo municipio que descartó: con este cambio, ese control depende de que el
  administrador también mire las apelaciones. Reutiliza `ResolutionAppeal` con
  `kind="moderacion"` (sin foto, con `status`, `resolved_by`,
  `resolution_reason`). Una por descarte (restricción única). El reporte sigue
  Cancelado mientras se revisa. `Report.closure_appeals` filtra las de cierre
  para que el hilo de resolución de US-048 no cambie: los serializers exponen
  `resolution_appeals` desde ahí.
- **Contrapeso 3, la reversión**: por apelación
  (`/api/panel/moderation-appeals/{id}/accept|reject/`, admin o agente) o de
  oficio (`/api/platform/reports/{id}/revert-moderation/`, **solo** el admin).
  Es `restituir_a_<estado>`, una operación por destino con actor
  `admin_plataforma`, `extra_actors` con el agente y origen
  `reversion_moderacion`; su guarda exige que el
  destino sea el `previous_status` guardado al descartar, y que haya área si
  vuelve a *En proceso* (ningún camino a En proceso sin área, US-028).
- **Contrapeso 4**: el origen `moderacion_municipal` es lo que US-050 va a contar
  aparte de las demás cancelaciones.
- Avisos: al autor, el cambio de estado con texto propio por origen
  (`ORIGIN_CHANGE_MESSAGES`); a quienes denunciaron, `denuncia_resuelta` con
  textos de contenido; al autor, `apelacion_moderacion_rechazada` si la
  plataforma mantiene el descarte (migración `notifications/0010`).
- El listado del panel trae `pending_complaint_count` (subconsulta, no join) y
  el detalle, `complaints` y `moderation`.

### El rechazo del validador vuelve a ser una decisión en terreno

`rechazar` estaba declarada con el origen por defecto (`manual`). La migración
0008 le había puesto `validacion_terreno` a los rechazos viejos, pero cada rechazo
posterior quedó como `manual` y el panel —que reconoce al validador por el
origen— dejó de mostrarlo como decisión suya. Se encontró al preparar US-050.
`rechazar` ahora lleva `validacion_terreno`, y la migración `reports/0015`
corrige los asientos que quedaron mal (solo `pendiente_validacion → cancelado`
con responsable, que nada más pudo producir).

### Estadísticas: un endpoint para toda la sección (US-023)

- `GET /api/panel/statistics/` (agente, `IsMunicipalAgent`, sobre
  `Report.objects.for_user`) y `GET /api/municipalities/{id}/statistics/`
  (admin, desde la ficha). Una sola respuesta con el período aplicado, el total y
  las dos distribuciones; US-050 suma sus indicadores a la misma.
- **El período**: `?period=7d|30d|12m|custom` (default `30d`), y con `custom`,
  `start` y `end` en `aaaa-mm-dd`. Se valida en el backend (`reports/statistics.py`,
  `resolve_window`): inicio posterior al fin o fin en el futuro dan `400` con el
  motivo en el campo. Las fechas son días calendario de `TIME_ZONE`, ambos
  incluidos, y se traducen a `[inicio 00:00, fin + 1 00:00)` hora local: un
  reporte de las 23 del último día cuenta.
- Cuenta los reportes **creados** en el período, agrupados por categoría y por
  su **estado actual**, con los siete estados. Tres consultas agregadas, sin
  traer filas (hay un test con `django_assert_num_queries`). Lo que no tiene
  reportes vuelve en cero; sin total, el porcentaje es `null` y no `0`.
- Índice `report_muni_created` (`municipality`, `created_at`), migración `0016`.
- **Datos para la demo**: `python manage.py seed_statistics` (después de
  `seed_demo`) agrega 90 reportes por municipio repartidos en 12 meses, con
  cadenas de historial fechadas y sus orígenes. Es idempotente y determinista.
  Las transiciones se escriben directo en el historial porque hay que fecharlas
  en el pasado; un test verifica que cada una sea una de las de la tabla.
- `seed_demo` estaba roto desde US-042: creaba fotos sin `photo_status`
  procesado y el modelo las rechaza. Corregido.

### Indicadores de gestión: todo sale del historial (US-050)

- Viajan en `indicators`, dentro de la misma respuesta de estadísticas y sobre
  el mismo período. Se calculan en `reports/statistics.py` (`indicators`) **sobre
  `ReportStatusHistory`**, con subconsultas por reporte, restas
  `ExpressionWrapper(..., DurationField())` y `Avg` en la base: seis consultas en
  total, tenga los reportes que tenga.
- Los cortes de cada reloj:

  | Indicador | Desde | Hasta | Sobre |
  |---|---|---|---|
  | Validación | creación | primer paso a Reportado | validados en el período, por origen (`validacion_terreno` / `validacion_colectiva`) |
  | Asignación | primer Reportado | primer En proceso | pasados a En proceso en el período |
  | Resolución | primer En proceso | **último** cierre `cierre_operario` | con último cierre en el período |

  La resolución termina en el cierre del operario, no en la confirmación: la
  ventana de objeción es un control, no trabajo municipal. Y toma primer inicio y
  último cierre, así un reporte reabierto por apelación cuenta lo que esperó el
  vecino de verdad. Sin casos, el promedio es `null` (no cero).
- **Abiertos**: foto del presente, sin período: cantidad por estado
  (pendiente, reportado, en proceso) y desde cuándo espera el más viejo, medido
  desde que entró en ese estado. No entran en ningún promedio.
- **Cierres apelados**: se cuentan cierres (no reportes) del período, y cuántos
  tuvieron una objeción después. El umbral para destacarlo es
  `DJANGO_STATS_APPEAL_ALERT_PERCENT` (default 20) y viaja en la respuesta.
- **Cancelaciones por origen**: `validacion_terreno` (rechazo del validador),
  `moderacion_municipal` (US-049) y `manual` (el agente cancela la intervención).
  **Archivados por inactividad** (`archivado_inactividad`) van aparte.
- El origen se lee del campo de la transición, nunca del rol de quien la hizo: la
  confirmación automática no tiene usuario.
- Índice `history_report_status_at` (`report`, `status`, `created_at`), migración
  `0017`.

### Compartir un reporte: un token, una página pública (US-030)

- `Report.share_token` es un UUID v4 aleatorio y único. El enlace se arma con
  `DJANGO_PUBLIC_REPORT_URL` (default `https://urbancheck.com.ar/r/{token}`) y
  viaja como `share_url` en el detalle **solo si el reporte es público**. Nunca
  se usa el id, que es correlativo y permitiría recorrer los reportes.
- La migración `0018` crea el campo en tres pasos (nulo, un token por fila,
  único): un `default` en `AddField` se evalúa una vez y les daría a todas las
  filas el mismo token.
- `GET /api/public/reports/<token>/` es el **único endpoint sin sesión**
  (`AllowAny`, límite `public_reports`, 120/hora por IP). Decide con la función
  única de visibilidad: lo que no es público responde `404` con
  `code: report_unavailable`, salvo el descarte por moderación (US-049), que
  además trae el motivo. El serializer público no lleva autor, comentarios ni
  quién intervino: responde el municipio.
- AASA suma `/r/*`, para que iOS abra el enlace en la app si está instalada.
- **Vista previa en redes** (`reports/share_preview.py`): `/r/<token>` lo
  responde Django, no el panel. WhatsApp, Facebook y X arman la tarjeta con las
  etiquetas Open Graph del HTML del servidor y no ejecutan JavaScript, así que a
  una SPA le verían siempre el mismo `index.html`. La vista devuelve un HTML
  mínimo con `og:title`, `og:description`, `og:image` (la foto **difuminada**,
  URL absoluta) y `twitter:card`, y una redirección por JavaScript a
  `DJANGO_PUBLIC_REPORT_PAGE_URL` (default `/reporte/{token}`, la página del
  panel). El bot se queda con las etiquetas; la persona sigue de largo. Un
  reporte que ya no es público da una tarjeta genérica, sin foto ni texto.
- WhatsApp recomienda imágenes de menos de 300 KB para la vista previa; una foto
  más pesada puede salir sin miniatura. Si pasa, el paso siguiente es servir una
  miniatura reducida en `og:image`.
- En producción el nginx del panel manda `/r/` y `/.well-known/` a Django, en el
  mismo dominio; en desarrollo lo hace el proxy de Vite (`^/r/`).

### El admin lee la bandeja de denuncias (21/10)

Con el selector de municipalidad del panel, el admin de la plataforma ve la
bandeja de denuncias de la ciudad elegida: `GET /api/panel/moderation/` y
`count/` aceptan al admin (`IsPanelUser`) con `?municipality=<id>`. Descartar y
desestimar siguen siendo solo del agente (`IsMunicipalAgent`): el admin recibe
`403`.

### El agente ve y resuelve las solicitudes por dato personal de su municipio (21/10)

Pedido del usuario, contrario al escenario 10 de US-043: `GET
/api/platform/privacy-requests/` (lista y detalle) acepta al agente municipal
(`IsPanelUser`), acotado a su municipalidad con `Report.objects.for_user` —otra
municipalidad responde `404`—. **También las resuelve** (`remove-image` y
`dismiss`, pedido del 21/10): el admin las resuelve en todas las
municipalidades y el agente en la suya. El agente y el admin reciben
la `image.url` también mientras la solicitud está pendiente (pedido del 21/10):
sin la foto no se puede juzgar la denuncia.

El panel juntó esta bandeja con la de contenido en una sola pantalla de
Denuncias, con un filtro por tipo. Para eso `GET /api/panel/moderation/` y su
`count/` aceptan `?reason=contenido_inapropiado|reporte_falso`: acota los
reportes a los que tienen denuncias pendientes de ese motivo, y
`pending_complaint_count` cuenta solo esas. Un motivo que no es de contenido se
ignora. `GET /api/panel/moderation/resolved/` es el registro de lo resuelto por
contenido (una fila por `ModerationDecision`, la más reciente primero, mismo
alcance y mismo `?reason=`), para la pestaña «Resueltas».

El panel ya no retiene la imagen denunciada por dato personal (pedido del
21/10): el detalle del panel y la bandeja la mandan siempre, porque el agente y
el admin la necesitan para resolver. Las vistas públicas siguen sin mostrarla.

### El historial guarda con qué rol se actuó (C-15)

El administrador de la plataforma ejecuta las acciones del panel con las mismas
reglas que el agente (`Actor.MUNICIPAL_AGENT`). Por decisión del equipo se
mantiene así, pero cada asiento de `ReportStatusHistory` guarda en
`changed_by_role` el rol de `changed_by` en ese momento, y el panel marca los
cambios del admin. Los asientos anteriores al campo lo tienen vacío.

## Seguridad (Sprint 5, deuda del Sprint 4)

Todo lo de esta sección se configura por variables de entorno; la lista
completa, con sus defaults, está en `.env.example`.

- **Límites de intentos (allauth).** 5 logins fallidos por cuenta cada 15
  minutos (ventana deslizante) más un tope por IP; 3 recuperaciones y 3
  reenvíos de confirmación por cuenta y por hora; registro con tope por IP.
  allauth headless responde el bloqueo de login con `400` y el reenvío limitado
  con `403`: `HeadlessLockoutMiddleware` los convierte en `429`.
- **Límites de tasa (DRF).** Por usuario: 20 reportes por hora, 60 comentarios
  por hora, 10 denuncias por día y 5 solicitudes por dato personal por día.
  Una denuncia por dato personal consume los dos últimos cupos, venga por
  `complaints/` o por `privacy-request/`. El `429` lleva `code: "throttled"`,
  `detail` en castellano y `retry_after`.
- **Proxies.** `DJANGO_NUM_PROXIES` (default 0) alimenta a DRF, allauth y el
  registro. Detrás del nginx del panel y de Traefik hay que contarlos, o todo
  límite por IP cuenta la IP del proxy. Con 0 se ignora `X-Forwarded-For`.
- **Cache compartido en Redis** (`RedisCache` de Django) en local y producción;
  sin él cada worker llevaría su propia cuenta.
- **Registro de seguridad**: logger `security`, archivo con rotación
  (`DJANGO_SECURITY_LOG_FILE`, default `logs/security.log`). Registra logins,
  bloqueos, cambios y restablecimientos de contraseña, altas de municipalidades
  y cuentas de trabajo, denuncias, solicitudes por dato personal y sus
  resoluciones, y toda respuesta 401, 403 y 429, con usuario, IP y ruta.
  Nunca contraseñas, tokens ni cuerpos. Un login fallido guarda una huella de
  la cuenta, no lo que se escribió.
- **Metadatos.** Toda foto que entra por el circuito de US-041/US-042 se
  reencodea sin EXIF, XMP ni IPTC. La de perfil no se difumina pero pasa por
  `MetadataFreeImageField`, que la sanea en cualquier carga (API, admin,
  shell). `python manage.py strip_image_metadata [--apply]` sanea las de perfil
  ya guardadas. HEIC no llega al backend: la app reencodea a JPEG antes de
  subir, y Pillow sin `pillow-heif` rechaza un HEIC con `400`.
- **Sin listado de usuarios (C-01).** `GET /api/users/` no existe: exponía el
  correo, el rol y la municipalidad de todas las cuentas a cualquier sesión.
  Quedan `me/`, `me/onboarding/` y el detalle de otro usuario, que usa
  `PublicUserSerializer` (sin correo). Las cuentas de trabajo se listan en
  `municipal-agents/`, `validators/` y `operators/`, acotados por rol.
- **Política de contenido (C-05).** `SECURE_CSP` de Django 6.0, aplicada por
  `AdminAndDocsCSPMiddleware` solo al admin y a `/api/docs/`: sin scripts
  inline ni `eval`; Swagger UI llega de jsDelivr y arranca desde un script
  aparte (`SpectacularSwaggerSplitView`). La API y la vista previa de un
  reporte compartido no la llevan. El panel tiene la suya en su nginx.
- **Verificación de correo opcional (C-08).** `ACCOUNT_EMAIL_VERIFICATION`
  sigue en `"optional"` por decisión del equipo: con `"mandatory"`, una falla
  del SMTP de producción dejaría a todos sin poder registrarse. Hacerla
  obligatoria pide la pantalla "Revisá tu correo" en la app y que las cuentas
  de trabajo nazcan verificadas; es deuda técnica.
- **Producción**: HSTS de un año, CORS cerrado (el panel va por el mismo
  origen), admin en `DJANGO_ADMIN_URL` (rechaza `admin/`).
  `check --deploy` sin advertencias: `docs/sprint-5/check-deploy.txt`.
  El SMTP sale de `EMAIL_HOST` (obligatoria), `EMAIL_PORT` (587),
  `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` y `EMAIL_USE_TLS` (True) (C-02).
- **CI** (`.github/workflows/ci.yml`): ruff, Bandit (falla desde severidad
  media), pip-audit, gitleaks (binario con checksum fijo; excepciones
  revisadas en `.gitleaksignore`), pytest y `makemigrations --check`. Dependabot
  semanal para uv, Docker, Docker Compose y GitHub Actions, con los PR contra
  `develop` (C-16).

## Despliegue

Producción corre con `docker-compose.production.yml`: Traefik (TLS con Let's
Encrypt), Django con gunicorn, PostgreSQL, Redis, el worker y el beat de
Celery, Flower, el nginx que sirve `/media/` y el panel. Base de cookiecutter:
[documentación de despliegue con Docker](https://cookiecutter-django.readthedocs.io/en/latest/3-deployment/deployment-with-docker.html).

### Pasos

1. **DNS y puertos.** `<dominio>` y `panel.<dominio>` apuntan al servidor. Se
   abren solo el 80 (lo usa el desafío de Let's Encrypt y redirige a 443) y el
   443. El 5555 no: Flower no se publica (C-06).
2. **Código.** Clonar `urbancheck_backend` y `urbanchech_frontend` uno al lado
   del otro y dejar los dos en la misma versión (la etiqueta del release). El
   servicio `panel` se construye desde `../urbanchech_frontend`, target
   `runtime` (C-04): no hay una imagen publicada en un registro.
3. **Entorno.** Crear `.envs/.production/.django` y `.envs/.production/.postgres`
   (no se versionan) con las variables de `.env.example`. Las que no tienen
   default en producción:
   - `DJANGO_SECRET_KEY`, `DJANGO_ADMIN_URL` (no `admin/`) y `EMAIL_HOST`, más
     `EMAIL_HOST_USER` y `EMAIL_HOST_PASSWORD` del proveedor (C-02).
   - `DJANGO_ALLOWED_HOSTS=<dominio>,panel.<dominio>` y
     `DJANGO_PUBLIC_REPORT_PAGE_URL=https://panel.<dominio>/reporte/{token}`
     (C-04); `DJANGO_PUBLIC_REPORT_URL=https://<dominio>/r/{token}`.
   - `CELERY_FLOWER_USER` y `CELERY_FLOWER_PASSWORD`, que pide Flower, y
     `CELERY_WORKER_CONCURRENCY` si 2 procesos no entran en la memoria (C-07).
   - `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER` y
     `POSTGRES_PASSWORD` en `.postgres`.
   - Para el primer despliegue, `DJANGO_SECURE_HSTS_SECONDS=60` hasta verificar
     que todo anda por HTTPS: un HSTS largo no se deshace en el navegador. El
     middleware `panel-hsts` de Traefik tiene el año fijo (C-05).
4. **Dominio.** `export URBANCHECK_DOMAIN=<dominio>` en la sesión que corre
   Compose (o en un `.env` junto al archivo). Sin ella Compose no arranca: la
   usa Traefik para el ruteo y los certificados.
5. **Levantar.**

   ```bash
   docker compose -f docker-compose.production.yml build
   docker compose -f docker-compose.production.yml up -d
   ```

   El servicio `django` aplica las migraciones al arrancar (`migrate
   --noinput`, antes de `collectstatic`); worker, beat y flower no migran
   (C-03).
6. **Primer usuario y verificación.**

   ```bash
   docker compose -f docker-compose.production.yml run --rm django python manage.py createsuperuser
   docker compose -f docker-compose.production.yml run --rm django python manage.py check --deploy
   ```

### Ruteo (Traefik)

| Pedido                    | Servicio                                           |
| ------------------------- | -------------------------------------------------- |
| `panel.<dominio>`         | `panel` (su nginx hace de proxy de la API)         |
| `<dominio>/r/<token>`     | `panel`, que se lo pasa a Django (US-030)          |
| `<dominio>/media/`        | `nginx`                                            |
| `<dominio>`, todo lo demás | `django`: API, admin, `/.well-known/` incluido    |

Traefik agrega HSTS de un año a las respuestas del panel (middleware
`panel-hsts`, C-05); las de Django ya lo traen. El nginx del panel le reenvía a
Django el `X-Forwarded-Proto` que recibió de Traefik.

### Flower

Escucha solo en el `127.0.0.1:5555` del servidor (C-06). Se entra por túnel
SSH, con su usuario y contraseña de siempre:

```bash
ssh -N -L 5555:127.0.0.1:5555 <usuario>@<servidor>
# y en el navegador: http://localhost:5555
```

### Celery

El worker corre con `--concurrency` de `CELERY_WORKER_CONCURRENCY` (2),
`--prefetch-multiplier=1` y `--max-tasks-per-child=20`: difuminar una foto de
12 MP llega a 847 MB (C-07). Los límites por tarea son 60 s blando y 90 s duro
(`config/settings/base.py`).

### Pendiente

- Los identificadores de la app para Universal Links y App Links
  (`IOS_UNIVERSAL_LINK_APP_ID`, `ANDROID_APP_PACKAGE`) siguen siendo los de la
  plantilla de Expo hasta tener el bundle ID y el Team ID (C-13).
- `DJANGO_NUM_PROXIES` cuenta los proxies delante de Django, y no son los mismos
  en los dos caminos: Traefik solo (la app) o Traefik y el nginx del panel. Con
  un único valor, los límites por IP de uno de los dos caminos cuentan la IP de
  un proxy.

## Flujo de trabajo

Git Flow por sprint, igual en los tres repositorios (C-20). Es lo que se hace
desde el Sprint 1, no una rama por historia:

- Cada sprint se trabaja en `feature/sprint-N`, que sale de `develop`.
  Correcciones puntuales sobre un sprint en curso pueden ir en ramas
  `fix/<id>` que salen de esa rama y vuelven a ella con merge.
- Al cerrar el sprint, PR de `feature/sprint-N` a `develop`, que se fusiona con
  merge commit (sin squash ni rebase) con el CI en verde.
- El merge a `develop` se etiqueta con una etiqueta anotada `sprint-N`. Las
  etiquetas se suben de a una (`git push origin sprint-N`), nunca con `--tags`.
- `main` solo recibe releases: `release/x.y.z` sale de `develop`, se fusiona en
  `main`, se etiqueta `vx.y.z` y vuelve a `develop`. Un `hotfix/<descripcion>`
  sale de `main` y vuelve a `main` y a `develop`.
- No se reescribe historia publicada: nada de force push, rebase de ramas
  remotas ni amend de commits ya subidos.

## Licencia

Propietaria, todos los derechos reservados: ver [`LICENSE`](LICENSE). Es la
misma en los tres repositorios de UrbanCheck (C-14).
