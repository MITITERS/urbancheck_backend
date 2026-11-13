# Guía de contribución

Este proyecto utiliza Git Flow y Conventional Commits.

## Ramas principales

- `main`: código estable. Representa la línea base oficial del producto.
- `develop`: integración de funcionalidades del sprint.
- `feature/US-<nro>-<descripcion>`: desarrollo de historias de usuario o tareas técnicas.
- `release/<version>`: preparación de entregas.
- `hotfix/<descripcion>`: correcciones urgentes.

## Flujo de trabajo

Antes de comenzar una tarea:

```bash
git checkout develop
git pull origin develop
```

Crear una rama nueva:

```bash
git checkout -b feature/US-001-descripcion
```

Subir la rama:

```bash
git push -u origin feature/US-001-descripcion
```

Luego abrir un Pull Request hacia `develop`.

## Convención de ramas

Formato obligatorio para historias:

```text
feature/US-<nro>-<descripcion-en-kebab-case>
```

Ejemplos:

```text
feature/US-001-registro-usuario
feature/US-002-login
feature/US-003-crear-reporte
```

Si la tarea no tiene historia de usuario asociada, usar:

```text
feature/US-000-tarea-tecnica
```

## Convención de commits

Usar Conventional Commits:

```text
feat(scope): descripción
fix(scope): descripción
docs(scope): descripción
refactor(scope): descripción
test(scope): descripción
style(scope): descripción
build(scope): descripción
ci(scope): descripción
chore(scope): descripción
```

Ejemplos:

```text
feat(auth): agregar registro de usuario
fix(reports): corregir validación de imagen
docs(readme): actualizar instrucciones
test(auth): agregar tests de login
```

No usar commits genéricos como:

```text
cambios
fix
update
prueba
commit final
```

## Pull Requests

Toda PR debe:

- Apuntar a `develop`.
- Referenciar la historia de usuario asociada.
- Explicar brevemente los cambios realizados.
- Tener al menos una aprobación de otro integrante.
- Incluir tests cuando corresponda.
- Actualizar documentación si corresponde.

No se permiten commits directos a `main` ni a `develop`.

## Releases

Al cierre de cada sprint se debe crear una rama de release:

```text
release/v1.0
```

La rama `release/*` se mergea primero a `main` y luego a `develop`.

Cada merge a `main` debe generar un tag de versión.

Ejemplos:

```text
v1.0
v1.1
v2.0
```

## Hotfixes

Para correcciones urgentes:

```text
hotfix/descripcion-del-error
```

La rama `hotfix/*` se mergea a `main` y luego a `develop`.

## Comandos útiles

Levantar entorno local:

```bash
docker compose -f docker-compose.local.yml up
```

Correr tests:

```bash
uv run pytest
```

Correr coverage:

```bash
uv run coverage run -m pytest
uv run coverage html
```

Correr chequeos de tipos:

```bash
uv run mypy urbancheck
```

## Reglas de seguridad

No commitear:

- Archivos `.env`
- Tokens
- Passwords
- Claves secretas
- Credenciales de base de datos
- Datos reales de usuarios

## Definition of Done

Una tarea se considera terminada cuando:

- Cumple los criterios de aceptación.
- Fue desarrollada en una rama `feature/*`.
- Tiene Pull Request hacia `develop`.
- Fue revisada por otro integrante.
- Fue testeada.
- No contiene credenciales ni archivos sensibles.
- La documentación fue actualizada si correspondía.
