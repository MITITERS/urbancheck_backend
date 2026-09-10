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

### Pendiente conocido: la anonimización de imágenes

US-046 y US-048 dicen que la foto de cierre y la de la apelación atraviesan el
circuito de difuminado de US-041 (`SCRUM-68`). **Ese circuito no está
implementado**: US-041 y US-042 siguen en *To do*. Las dos fotos se cargan y se
publican directo, igual que la foto del reporte de US-004. Cuando se implemente
la anonimización, los tres puntos de carga tienen que engancharse a ella.

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