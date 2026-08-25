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

### El validador también está acotado, en toda la app

La cuenta de validador es una **cuenta de trabajo**: no ve nada de otros
municipios, ni siquiera en el feed y el mapa ciudadanos. Pedir por id un reporte
de otra jurisdicción devuelve `404`, igual que en el panel. Quien además quiera
usar UrbanCheck como vecino se crea una cuenta personal.

La regla vive en `User.sees_only_own_municipality` y se aplica en
`ReportViewSet.get_queryset()`, así que alcanza a todas las acciones del
viewset —detalle, comentarios, likes— y no solo al listado.

**Esto cambia lo que dicen dos historias del Sprint 3**, y conviene actualizar
sus documentos:

- US-035 describe al validador como alguien que «usa la aplicación móvil en las
  mismas condiciones que un ciudadano común». Ya no: su vista está acotada.
- El escenario 6 de US-036 —ver un reporte de otra municipalidad como ciudadano
  común, sin opción de validar— dejó de ser alcanzable navegando la app.

Consecuencia asumida: un reporte creado por el propio validador fuera de su
jurisdicción tampoco le aparece, ni en «mis reportes». Es el precio de que la
regla sea una sola y no admita excepciones.

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